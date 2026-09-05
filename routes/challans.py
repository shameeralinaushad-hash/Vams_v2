import os
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, session
from werkzeug.utils import secure_filename
from sqlalchemy.orm import selectinload
from models import db, DeliveryChallan, DeliveryChallanLineItem, CatalogItem, Order, PurchaseOrder, ClientDocSequence
from utils import get_order_folder
from pdf_templates.challan_template import generate_challan_pdf
from audit import log_action
from numbering import build_challan_number
from permissions import permission_required

challans_bp = Blueprint("challans", __name__, url_prefix="/challans")


def get_or_create_catalog_item(description):
    description = description.strip()
    item = CatalogItem.query.filter(db.func.lower(CatalogItem.description) == description.lower()).first()
    if not item:
        item = CatalogItem(description=description)
        db.session.add(item)
        db.session.commit()
    return item


def _parse_challan_form(order):
    descriptions = request.form.getlist("item_description")
    part_nos = request.form.getlist("item_part_no")
    qtys = request.form.getlist("item_qty")
    units = request.form.getlist("item_unit")

    challan_number = request.form.get("challan_number", "").strip()
    recipient = request.form.get("recipient", "").strip()
    dispatch_date_str = request.form.get("dispatch_date", "")
    dispatch_date_val = datetime.strptime(dispatch_date_str,
                                          "%Y-%m-%d").date() if dispatch_date_str else date.today()
    transport_mode = request.form.get("transport_mode", "").strip()
    vehicle_number = request.form.get("vehicle_number", "").strip()
    place = request.form.get("place", "").strip()
    skip_letterhead = request.form.get("skip_letterhead") == "on"

    return {
        "descriptions": descriptions, "part_nos": part_nos, "qtys": qtys, "units": units,
        "challan_number": challan_number, "recipient": recipient,
        "dispatch_date": dispatch_date_val, "transport_mode": transport_mode,
        "vehicle_number": vehicle_number, "place": place,
        "skip_letterhead": skip_letterhead,
    }


def _build_challan_line_items(challan, data):
    line_items = []
    for desc, part_no, qty, unit in zip(data["descriptions"], data["part_nos"], data["qtys"], data["units"]):
        if not desc.strip():
            continue
        catalog_item = get_or_create_catalog_item(desc)
        li = DeliveryChallanLineItem(
            challan_id=challan.id,
            catalog_item_id=catalog_item.id,
            description=desc.strip(),
            part_no=part_no.strip() if part_no else "",
            unit=unit.strip(),
            qty=float(qty or 0),
        )
        db.session.add(li)
        line_items.append(li)
    return line_items


def _write_challan_pdf(order, challan, line_items):
    version_suffix = f"_v{challan.pdf_version}" if (challan.pdf_version or 1) > 1 else ""
    folder = get_order_folder(current_app, order)
    filename = f"Challan_{challan.challan_number.replace('/', '-')}{version_suffix}.pdf"
    output_path = os.path.join(folder, filename)

    generate_challan_pdf(
        order.company, order.client, challan, line_items, output_path,
        skip_letterhead=bool(challan.skip_letterhead)
    )

    safe_title = secure_filename(order.title) if order.title else "untitled"
    folder_name = f"{order.id}_{safe_title}"
    challan.pdf_path = f"documents/company_{order.company_id}/{folder_name}/{filename}"
    db.session.commit()


@challans_bp.route("/")
def list_challans():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    page = request.args.get("page", 1, type=int)
    pagination = (
        DeliveryChallan.query.join(Order)
        .filter(Order.company_id == company_id)
        .options(db.contains_eager(DeliveryChallan.order).joinedload(Order.client))
        .order_by(DeliveryChallan.id.desc())
        .paginate(page=page, per_page=25, error_out=False)
    )
    return render_template("challans/list.html", challans=pagination.items, pagination=pagination)


@challans_bp.route("/order/<int:order_id>/create", methods=["GET", "POST"])
def create_challan(order_id):
    order = db.session.query(Order).options(
        selectinload(Order.company),
        selectinload(Order.client),
        selectinload(Order.purchase_orders),
    ).filter(Order.id == order_id).first()
    if not order:
        from flask import abort
        abort(404)
    seq = ClientDocSequence.get_or_create(order.company_id, order.client_id, "challan")

    if request.method == "POST":
        data = _parse_challan_form(order)
        challan_number = data["challan_number"]

        if not challan_number:
            raw = seq.peek_next_raw_number() if seq else order.id
            challan_number = build_challan_number(order.company, order.client, raw)

        existing = DeliveryChallan.query.filter_by(order_id=order.id).all()
        for old_c in existing:
            old_c.is_current = False
        db.session.commit()

        challan = DeliveryChallan(
            order_id=order.id,
            challan_number=challan_number,
            recipient=data["recipient"],
            dispatch_date=data["dispatch_date"],
            transport_mode=data["transport_mode"],
            vehicle_number=data["vehicle_number"],
            place=data["place"],
            skip_letterhead=data["skip_letterhead"],
            purchase_order_id=int(request.form.get("purchase_order_id")) if request.form.get("purchase_order_id") else None,
            is_current=True,
            pdf_version=1,
        )
        db.session.add(challan)
        db.session.commit()

        if seq:
            seq.get_next_raw_number()

        line_items = _build_challan_line_items(challan, data)
        db.session.commit()

        from background import run_in_background
        run_in_background(_write_challan_pdf, order, challan, line_items,
                          _app=current_app._get_current_object())

        log_action("create_challan", "DeliveryChallan", challan.id,
                   f"Created delivery challan {challan_number} for {order.client.name}")

        return redirect(url_for("orders.view_order", order_id=order.id))

    po = order.purchase_order
    selected_po_id = request.args.get("po_id", type=int)
    if selected_po_id:
        for p in order.purchase_orders:
            if p.id == selected_po_id:
                po = p
                break

    if po and po.line_items:
        prefill_items = po.line_items
    elif order.commercial_quotation:
        prefill_items = order.commercial_quotation.line_items
    elif order.commercial_quotation:
        prefill_items = order.commercial_quotation.line_items
    else:
        prefill_items = []
    raw = seq.peek_next_raw_number() if seq else order.id
    suggested_number = build_challan_number(order.company, order.client, raw)
    return render_template(
        "challans/create.html", order=order, selected_po_id=selected_po_id,
        prefill_items=prefill_items, suggested_number=suggested_number, today=date.today().isoformat()
    )


@challans_bp.route("/edit/<int:challan_id>", methods=["GET", "POST"])
def edit_challan(challan_id):
    challan = db.session.query(DeliveryChallan).options(
        selectinload(DeliveryChallan.order),
        selectinload(DeliveryChallan.line_items),
        selectinload(DeliveryChallan.purchase_order),
    ).filter(DeliveryChallan.id == challan_id).first()
    if not challan:
        from flask import abort
        abort(404)
    order = challan.order

    if request.method == "POST":
        data = _parse_challan_form(order)

        challan.challan_number = data["challan_number"] or challan.challan_number
        challan.recipient = data["recipient"]
        challan.dispatch_date = data["dispatch_date"]
        challan.transport_mode = data["transport_mode"]
        challan.vehicle_number = data["vehicle_number"]
        challan.place = data["place"]
        challan.skip_letterhead = data["skip_letterhead"]
        challan.purchase_order_id = int(request.form.get("purchase_order_id")) if request.form.get("purchase_order_id") else None
        challan.pdf_version = (challan.pdf_version or 1) + 1

        for li in list(challan.line_items):
            db.session.delete(li)
        db.session.flush()

        line_items = _build_challan_line_items(challan, data)
        db.session.commit()

        from background import run_in_background
        run_in_background(_write_challan_pdf, order, challan, line_items,
                          _app=current_app._get_current_object())

        log_action("edit_challan", "DeliveryChallan", challan.id,
                   f"Edited delivery challan {challan.challan_number} for {order.client.name}")

        flash("Delivery Challan updated.")
        return redirect(url_for("orders.view_order", order_id=order.id))

    return render_template(
        "challans/create.html", order=order, challan=challan,
        prefill_items=challan.line_items,
        suggested_number=challan.challan_number,
        today=challan.dispatch_date.isoformat()
    )


@challans_bp.route("/delete/<int:challan_id>", methods=["POST"])
@permission_required("delete_documents")
def delete_challan(challan_id):
    challan = db.session.query(DeliveryChallan).options(
        selectinload(DeliveryChallan.order),
    ).filter(DeliveryChallan.id == challan_id).first()
    if not challan:
        from flask import abort
        abort(404)
    order_id = challan.order_id
    was_current = challan.is_current
    challan_number = challan.challan_number

    if challan.pdf_path:
        full_path = os.path.join(current_app.root_path, "static", challan.pdf_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    db.session.delete(challan)
    db.session.commit()

    if was_current:
        remaining = DeliveryChallan.query.filter_by(order_id=order_id).order_by(DeliveryChallan.id.desc()).first()
        if remaining:
            remaining.is_current = True
            db.session.commit()

    log_action("delete_challan", "DeliveryChallan", challan_id, f"Deleted delivery challan {challan_number}")

    flash("Delivery Challan deleted.")
    return redirect(url_for("orders.view_order", order_id=order_id))


@challans_bp.route("/regenerate/<int:challan_id>", methods=["POST"])
def regenerate_challan(challan_id):
    challan = db.session.query(DeliveryChallan).options(
        selectinload(DeliveryChallan.order),
        selectinload(DeliveryChallan.line_items),
    ).filter(DeliveryChallan.id == challan_id).first()
    if not challan:
        from flask import abort
        abort(404)
    order = challan.order
    challan_id = challan.id

    def _generate():
        with current_app.app_context():
            c = db.session.get(DeliveryChallan, challan_id)
            if not c:
                return
            o = c.order
            c.pdf_version = (c.pdf_version or 1) + 1
            version_suffix = f"_v{c.pdf_version}" if c.pdf_version > 1 else ""
            folder = get_order_folder(current_app, o)
            filename = f"Challan_{c.challan_number.replace('/', '-')}{version_suffix}.pdf"
            output_path = os.path.join(folder, filename)
            generate_challan_pdf(
                o.company, o.client, c, c.line_items, output_path,
                skip_letterhead=bool(c.skip_letterhead)
            )
            safe_title = secure_filename(o.title) if o.title else "untitled"
            folder_name = f"{o.id}_{safe_title}"
            c.pdf_path = f"documents/company_{o.company_id}/{folder_name}/{filename}"
            db.session.commit()

    from background import run_in_background
    run_in_background(_generate, _app=current_app._get_current_object())

    flash("Delivery Challan PDF generating in background. It will be ready shortly.")
    return redirect(url_for("orders.view_order", order_id=order.id))