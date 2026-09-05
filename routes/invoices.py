import os
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, session
from werkzeug.utils import secure_filename
from sqlalchemy.orm import selectinload
from models import db, Invoice, InvoiceLineItem, CatalogItem, Order, PurchaseOrder, ClientDocSequence, PriceHistory, Quotation
from utils import get_order_folder
from pdf_templates.invoice_template import generate_invoice_pdf
from audit import log_action
from numbering import build_invoice_number
from permissions import permission_required
from socket_events import emit_company, emit_dashboard_update

invoices_bp = Blueprint("invoices", __name__, url_prefix="/invoices")


def get_or_create_catalog_item(description):
    description = description.strip()
    item = CatalogItem.query.filter(db.func.lower(CatalogItem.description) == description.lower()).first()
    if not item:
        item = CatalogItem(description=description)
        db.session.add(item)
        db.session.commit()
    return item


def _parse_invoice_form(order):
    part_nos = request.form.getlist("item_part_no")
    descriptions = request.form.getlist("item_description")
    units = request.form.getlist("item_unit")
    qtys = request.form.getlist("item_qty")
    prices = request.form.getlist("item_price")
    taxes = request.form.getlist("item_tax")

    invoice_number = request.form.get("invoice_number", "").strip()
    invoice_date_str = request.form.get("invoice_date", "")
    invoice_date_val = datetime.strptime(invoice_date_str, "%Y-%m-%d").date() if invoice_date_str else date.today()
    skip_letterhead = request.form.get("skip_letterhead") == "on"
    recipient = request.form.get("recipient", "").strip() or None
    discount_amount = float(request.form.get("discount_amount", "0") or 0)
    installation_charges = float(request.form.get("installation_charges", "0") or 0)
    transportation_charges = float(request.form.get("transportation_charges", "0") or 0)
    tax_amount = float(request.form.get("tax_amount", "0") or 0)
    purchase_order_id = request.form.get("purchase_order_id")

    return {
        "part_nos": part_nos, "descriptions": descriptions, "units": units,
        "qtys": qtys, "prices": prices, "taxes": taxes,
        "invoice_number": invoice_number, "invoice_date": invoice_date_val,
        "skip_letterhead": skip_letterhead, "recipient": recipient,
        "discount_amount": discount_amount, "installation_charges": installation_charges,
        "transportation_charges": transportation_charges, "tax_amount": tax_amount,
        "purchase_order_id": purchase_order_id,
    }


def _build_invoice_line_items(invoice, data, order):
    line_items = []
    for part_no, desc, unit, qty, price, tax in zip(
            data["part_nos"], data["descriptions"], data["units"],
            data["qtys"], data["prices"], data["taxes"]):
        if not desc.strip():
            continue
        catalog_item = get_or_create_catalog_item(desc)
        unit_price = float(price or 0)

        li = InvoiceLineItem(
            invoice_id=invoice.id,
            catalog_item_id=catalog_item.id,
            part_no=part_no.strip() if part_no else "",
            description=desc.strip(),
            unit=unit.strip() if unit else "Nos",
            qty=float(qty or 0),
            unit_price=unit_price,
            tax_percent=float(tax or 0),
        )
        db.session.add(li)
        line_items.append(li)

        db.session.add(PriceHistory(
            catalog_item_id=catalog_item.id,
            client_id=order.client_id,
            company_id=order.company_id,
            price=unit_price,
            quoted_date=data["invoice_date"],
            source_doc="invoice",
        ))
    return line_items


def _write_invoice_pdf(order, invoice, line_items):
    version_suffix = f"_v{invoice.pdf_version}" if (invoice.pdf_version or 1) > 1 else ""
    folder = get_order_folder(current_app, order)
    filename = f"Invoice_{invoice.invoice_number.replace('/', '-')}{version_suffix}.pdf"
    output_path = os.path.join(folder, filename)

    total = generate_invoice_pdf(order.company, order.client, invoice, line_items, output_path,
                                 skip_letterhead=bool(invoice.skip_letterhead))

    safe_title = secure_filename(order.title) if order.title else "untitled"
    folder_name = f"{order.id}_{safe_title}"
    invoice.pdf_path = f"documents/company_{order.company_id}/{folder_name}/{filename}"
    invoice.total_amount = total
    db.session.commit()


@invoices_bp.route("/")
def list_invoices():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    page = request.args.get("page", 1, type=int)
    pagination = (
        Invoice.query.join(Order)
        .filter(Order.company_id == company_id)
        .options(db.contains_eager(Invoice.order).joinedload(Order.client))
        .order_by(Invoice.id.desc())
        .paginate(page=page, per_page=25, error_out=False)
    )
    return render_template("invoices/list.html", invoices=pagination.items, pagination=pagination)


@invoices_bp.route("/order/<int:order_id>/create", methods=["GET", "POST"])
def create_invoice(order_id):
    order = db.session.query(Order).options(
        selectinload(Order.purchase_orders).selectinload(PurchaseOrder.line_items),
        selectinload(Order.quotations),
    ).filter(Order.id == order_id).first()
    if not order:
        from flask import abort
        abort(404)
    seq = ClientDocSequence.get_or_create(order.company_id, order.client_id, "invoice")

    if request.method == "POST":
        data = _parse_invoice_form(order)
        invoice_number = data["invoice_number"]

        if invoice_number:
            if seq:
                seq.get_next_raw_number()
        else:
            raw = seq.get_next_raw_number() if seq else order.id
            invoice_number = build_invoice_number(order.company, order.client, raw)

        existing = Invoice.query.filter_by(order_id=order.id).all()
        for old_inv in existing:
            old_inv.is_current = False
        db.session.commit()

        invoice = Invoice(
            order_id=order.id, invoice_number=invoice_number, invoice_date=data["invoice_date"],
            discount_amount=data["discount_amount"], installation_charges=data["installation_charges"],
            transportation_charges=data["transportation_charges"], tax_amount=data["tax_amount"],
            skip_letterhead=data["skip_letterhead"],
            recipient=data["recipient"],
            purchase_order_id=int(data["purchase_order_id"]) if data.get("purchase_order_id") else None,
            is_current=True, pdf_version=1,
        )
        db.session.add(invoice)
        db.session.commit()

        line_items = _build_invoice_line_items(invoice, data, order)
        db.session.commit()

        from background import run_in_background
        run_in_background(_write_invoice_pdf, order, invoice, line_items,
                          _app=current_app._get_current_object())

        log_action("create_invoice", "Invoice", invoice.id, f"Created invoice {invoice_number} for {order.client.name}")

        emit_company("list_refresh", {"section": "invoices"}, order.company_id)
        emit_dashboard_update(order.company_id)
        return redirect(url_for("orders.view_order", order_id=order.id))

    order = Order.query.get_or_404(order_id)
    seq = ClientDocSequence.get_or_create(order.company_id, order.client_id, "invoice")

    if request.method == "POST":
        data = _parse_invoice_form(order)
        invoice_number = data["invoice_number"]

        if invoice_number:
            if seq:
                seq.get_next_raw_number()
        else:
            raw = seq.get_next_raw_number() if seq else order.id
            invoice_number = build_invoice_number(order.company, order.client, raw)

        existing = Invoice.query.filter_by(order_id=order.id).all()
        for old_inv in existing:
            old_inv.is_current = False
        db.session.commit()

        invoice = Invoice(
            order_id=order.id, invoice_number=invoice_number, invoice_date=data["invoice_date"],
            discount_amount=data["discount_amount"], installation_charges=data["installation_charges"],
            transportation_charges=data["transportation_charges"], tax_amount=data["tax_amount"],
            skip_letterhead=data["skip_letterhead"],
            recipient=data["recipient"],
            purchase_order_id=int(data["purchase_order_id"]) if data.get("purchase_order_id") else None,
            is_current=True, pdf_version=1,
        )
        db.session.add(invoice)
        db.session.commit()

        line_items = _build_invoice_line_items(invoice, data, order)
        db.session.commit()

        from background import run_in_background
        run_in_background(_write_invoice_pdf, order, invoice, line_items,
                          _app=current_app._get_current_object())

        log_action("create_invoice", "Invoice", invoice.id, f"Created invoice {invoice_number} for {order.client.name}")

        emit_company("list_refresh", {"section": "invoices"}, order.company_id)
        emit_dashboard_update(order.company_id)
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
    else:
        prefill_items = []
    prefill_discount = order.commercial_quotation.discount_amount if order.commercial_quotation else 0
    prefill_installation = order.commercial_quotation.installation_charges if order.commercial_quotation else 0
    prefill_transportation = order.commercial_quotation.transportation_charges if order.commercial_quotation else 0
    prefill_tax = order.commercial_quotation.tax_amount if order.commercial_quotation else 0
    prefill_recipient = getattr(order.commercial_quotation, "recipient", None) if order.commercial_quotation else None

    raw = seq.peek_next_raw_number() if seq else order.id
    suggested_number = build_invoice_number(order.company, order.client, raw)
    return render_template(
        "invoices/create.html", order=order, invoice=None,
        selected_po_id=selected_po_id,
        prefill_items=prefill_items,
        prefill_discount=prefill_discount, prefill_installation=prefill_installation,
        prefill_transportation=prefill_transportation, prefill_tax=prefill_tax,
        prefill_recipient=prefill_recipient,
        suggested_number=suggested_number, today=date.today().isoformat()
    )


@invoices_bp.route("/edit/<int:invoice_id>", methods=["GET", "POST"])
def edit_invoice(invoice_id):
    invoice = db.session.query(Invoice).options(
        selectinload(Invoice.line_items),
        selectinload(Invoice.order),
    ).filter(Invoice.id == invoice_id).first()
    if not invoice:
        from flask import abort
        abort(404)
    order = invoice.order

    if request.method == "POST":
        data = _parse_invoice_form(order)

        invoice.recipient = data["recipient"]
        invoice.discount_amount = data["discount_amount"]
        invoice.installation_charges = data["installation_charges"]
        invoice.transportation_charges = data["transportation_charges"]
        invoice.tax_amount = data["tax_amount"]
        invoice.purchase_order_id = int(data["purchase_order_id"]) if data.get("purchase_order_id") else None
        invoice.skip_letterhead = data["skip_letterhead"]
        invoice.pdf_version = (invoice.pdf_version or 1) + 1

        for li in list(invoice.line_items):
            db.session.delete(li)
        db.session.flush()

        line_items = _build_invoice_line_items(invoice, data, order)
        db.session.commit()

        from background import run_in_background
        run_in_background(_write_invoice_pdf, order, invoice, line_items,
                          _app=current_app._get_current_object())

        log_action("edit_invoice", "Invoice", invoice.id,
                   f"Edited invoice {invoice.invoice_number} for {order.client.name}")

        flash("Invoice updated.")
        emit_company("list_refresh", {"section": "invoices"}, order.company_id)
        emit_dashboard_update(order.company_id)
        return redirect(url_for("orders.view_order", order_id=order.id))

    return render_template(
        "invoices/create.html", order=order, invoice=invoice,
        prefill_items=invoice.line_items,
        prefill_discount=invoice.discount_amount,
        prefill_installation=invoice.installation_charges,
        prefill_transportation=invoice.transportation_charges,
        prefill_tax=invoice.tax_amount,
        prefill_recipient=invoice.recipient,
        suggested_number=invoice.invoice_number,
        today=invoice.invoice_date.isoformat()
    )


@invoices_bp.route("/delete/<int:invoice_id>", methods=["POST"])
@permission_required("delete_documents")
def delete_invoice(invoice_id):
    invoice = db.session.query(Invoice).options(
        selectinload(Invoice.payments),
    ).filter(Invoice.id == invoice_id).first()
    if not invoice:
        from flask import abort
        abort(404)
    order_id = invoice.order_id
    company_id = invoice.order.company_id

    if invoice.payments:
        flash("Cannot delete this invoice — it has payment(s) logged against it. Remove the payments first.")
        return redirect(url_for("orders.view_order", order_id=order_id))

    was_current = invoice.is_current
    invoice_number = invoice.invoice_number

    if invoice.pdf_path:
        full_path = os.path.join(current_app.root_path, "static", invoice.pdf_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    db.session.delete(invoice)
    db.session.commit()

    if was_current:
        remaining = Invoice.query.filter_by(order_id=order_id).order_by(Invoice.id.desc()).first()
        if remaining:
            remaining.is_current = True
            db.session.commit()

    log_action("delete_invoice", "Invoice", invoice_id, f"Deleted invoice {invoice_number}")

    flash("Invoice deleted.")
    emit_company("list_refresh", {"section": "invoices"}, company_id)
    emit_dashboard_update(company_id)
    return redirect(url_for("orders.view_order", order_id=order_id))


@invoices_bp.route("/regenerate/<int:invoice_id>", methods=["POST"])
def regenerate_invoice(invoice_id):
    invoice = db.session.query(Invoice).options(
        selectinload(Invoice.order),
        selectinload(Invoice.line_items),
    ).filter(Invoice.id == invoice_id).first()
    if not invoice:
        from flask import abort
        abort(404)
    order = invoice.order
    invoice_id = invoice.id

    def _generate():
        with current_app.app_context():
            inv = db.session.get(Invoice, invoice_id)
            if not inv:
                return
            o = inv.order
            inv.pdf_version = (inv.pdf_version or 1) + 1
            version_suffix = f"_v{inv.pdf_version}" if inv.pdf_version > 1 else ""
            folder = get_order_folder(current_app, o)
            filename = f"Invoice_{inv.invoice_number.replace('/', '-')}{version_suffix}.pdf"
            output_path = os.path.join(folder, filename)
            total = generate_invoice_pdf(o.company, o.client, inv, inv.line_items, output_path,
                                         skip_letterhead=bool(inv.skip_letterhead))
            safe_title = secure_filename(o.title) if o.title else "untitled"
            folder_name = f"{o.id}_{safe_title}"
            inv.pdf_path = f"documents/company_{o.company_id}/{folder_name}/{filename}"
            inv.total_amount = total
            db.session.commit()

    from background import run_in_background
    run_in_background(_generate, _app=current_app._get_current_object())

    flash("Invoice PDF generating in background. It will be ready shortly.")
    return redirect(url_for("orders.view_order", order_id=order.id))


from datetime import date as date_cls
from models import CreditNote


@invoices_bp.route("/cancel/<int:invoice_id>", methods=["POST"])
@permission_required("cancel_invoices")
def cancel_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "cancelled"
    db.session.commit()

    log_action("cancel_invoice", "Invoice", invoice.id, f"Cancelled invoice {invoice.invoice_number}")

    flash(f"Invoice {invoice.invoice_number} marked as cancelled.")
    return redirect(url_for("orders.view_order", order_id=invoice.order_id))


@invoices_bp.route("/reactivate/<int:invoice_id>", methods=["POST"])
@permission_required("cancel_invoices")
def reactivate_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "issued"
    db.session.commit()

    log_action("reactivate_invoice", "Invoice", invoice.id, f"Reactivated invoice {invoice.invoice_number}")

    flash(f"Invoice {invoice.invoice_number} reactivated.")
    return redirect(url_for("orders.view_order", order_id=invoice.order_id))


@invoices_bp.route("/<int:invoice_id>/credit-note/add", methods=["POST"])
@permission_required("issue_credit_notes")
def add_credit_note(invoice_id):
    invoice = db.session.query(Invoice).options(
        selectinload(Invoice.credit_notes),
    ).filter(Invoice.id == invoice_id).first()
    if not invoice:
        from flask import abort
        abort(404)

    amount = float(request.form.get("amount", 0))
    reason = request.form.get("reason", "").strip()
    credit_date_str = request.form.get("credit_date", "")
    credit_date_val = datetime.strptime(credit_date_str, "%Y-%m-%d").date() if credit_date_str else date_cls.today()

    if amount <= 0:
        flash("Credit amount must be greater than 0.")
        return redirect(url_for("orders.view_order", order_id=invoice.order_id))

    credit_number = f"CN-{invoice.invoice_number}-{len(invoice.credit_notes) + 1}"

    db.session.add(CreditNote(
        invoice_id=invoice.id, credit_number=credit_number, credit_date=credit_date_val,
        amount=amount, reason=reason
    ))
    db.session.commit()

    log_action("add_credit_note", "Invoice", invoice.id, f"Issued credit note of {amount:.2f} against invoice {invoice.invoice_number} — {reason}")

    flash(f"Credit note {credit_number} recorded.")
    return redirect(url_for("orders.view_order", order_id=invoice.order_id))