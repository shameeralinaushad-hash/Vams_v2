import os
import shutil
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from models import (
    db, Order, PurchaseOrder, PurchaseOrderLineItem, Client, ClientCompanyLink,
    Company, Quotation, QuotationLineItem, OrderDocument,
    Notification, User
)
from utils import get_order_folder, validate_upload, ALLOWED_DOC_EXTENSIONS
from audit import log_action
from permissions import permission_required
from pdf_templates.stamp_utility import stamp_last_page

orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


def require_active_company():
    company_id = session.get("active_company_id")
    if not company_id:
        return None
    company = db.session.get(Company, company_id)
    if not company:
        session.pop("active_company_id", None)
        session.pop("active_company_name", None)
        return None
    return company_id


@orders_bp.route("/")
def list_orders():
    company_id = require_active_company()
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    status_filter = request.args.get("status")
    client_filter = request.args.get("client_id")
    search = request.args.get("search", "").strip()
    sort_by = request.args.get("sort_by", "id")
    sort_dir = request.args.get("sort_dir", "desc")
    page = request.args.get("page", 1, type=int)

    # Base query joined with Quotation and Client
    query = (
        Order.query.filter_by(company_id=company_id)
        .outerjoin(Quotation)
        .join(Client)
        .options(
            db.contains_eager(Order.client),
            db.joinedload(Order.purchase_order),
            db.selectinload(Order.quotations),
        )
    )

    if status_filter:
        query = query.filter(Order.status == status_filter)

    if client_filter:
        query = query.filter(Order.client_id == client_filter)

    if search:
        search_like = f"%{search}%"
        query = query.filter(
            db.or_(
                Order.id.cast(db.String).like(search_like),
                Order.order_number.ilike(search_like),
                Order.title.ilike(search_like),
                Quotation.quote_number.ilike(search_like),
                Order.quotations.any(
                    Quotation.line_items.any(QuotationLineItem.description.ilike(search_like))
                )
            )
        )

    # Sorting logic
    if sort_by == "quote_number":
        sort_col = Quotation.quote_number
    elif sort_by == "client":
        sort_col = Client.name
    elif sort_by == "order_number":
        sort_col = Order.order_number
    else:
        sort_col = Order.id

    if sort_dir == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    pagination = query.paginate(page=page, per_page=25, error_out=False)
    orders = pagination.items

    # Fetch clients for dropdown
    clients = Client.query.join(ClientCompanyLink).filter(ClientCompanyLink.company_id == company_id).all()

    return render_template(
        "orders/list.html", orders=orders, status_filter=status_filter,
        client_filter=client_filter, clients=clients,
        search=search, sort_by=sort_by, sort_dir=sort_dir, pagination=pagination
    )


@orders_bp.route("/add", methods=["GET", "POST"])
def add_order():
    company_id = require_active_company()
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    clients = Client.query.all()

    if request.method == "POST":
        client_id = int(request.form["client_id"])
        subsidiary_id = request.form.get("subsidiary_id") or None
        notes = request.form.get("notes", "")
        title = request.form.get("title", "").strip()

        order = Order(
            company_id=company_id, client_id=client_id,
            subsidiary_id=int(subsidiary_id) if subsidiary_id else None,
            notes=notes, title=title, status="Pending"
        )
        db.session.add(order)
        db.session.commit()

        # Auto-increment from the highest numeric order_number for this company
        result = db.session.query(
            db.func.max(db.cast(Order.order_number, db.Integer))
        ).filter(
            Order.company_id == company_id,
            Order.order_number.isnot(None),
            Order.order_number != '',
        ).scalar()
        next_num = (result or 0) + 1
        order.order_number = str(next_num)
        db.session.commit()

        existing_link = ClientCompanyLink.query.filter_by(client_id=client_id, company_id=company_id).first()
        if not existing_link:
            db.session.add(ClientCompanyLink(client_id=client_id, company_id=company_id))
            db.session.commit()

        return redirect(url_for("orders.view_order", order_id=order.id))

    return render_template("orders/add.html", clients=clients)


@orders_bp.route("/<int:order_id>")
def view_order(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("orders/view.html", order=order)


@orders_bp.route("/<int:order_id>/edit", methods=["POST"])
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    company_id = require_active_company()

    # Target URL to redirect back to exact page (or fallback)
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=order.id)

    if not company_id or order.company_id != company_id:
        flash("Unauthorized action.")
        return redirect(redirect_target)

    new_title = request.form.get("title", "").strip()
    new_order_number = request.form.get("order_number", "").strip()
    notes = request.form.get("notes", "")

    # UNIQUE CHECK SCOPED TO THE SAME CLIENT ONLY
    if new_order_number and new_order_number != order.order_number:
        existing = Order.query.filter(
            Order.company_id == company_id,
            Order.client_id == order.client_id,  # <-- Scoped strictly to this client
            db.or_(
                Order.order_number == new_order_number,
                db.and_(
                    db.or_(Order.order_number == None, Order.order_number == ""),
                    Order.id.cast(db.String) == new_order_number
                )
            )
        ).first()

        if existing and existing.id != order.id:
            flash("This order number is already in use for this client. Please choose a unique number.")
            return redirect(redirect_target)

    # Handle folder renaming if title changes
    old_safe_title = secure_filename(order.title) if order.title else "untitled"
    old_folder_name = f"{order.id}_{old_safe_title}"
    old_folder_path = os.path.join(current_app.root_path, "static", "documents", f"company_{order.company_id}",
                                   old_folder_name)

    order.title = new_title
    order.order_number = new_order_number or str(order.id)
    order.notes = notes
    db.session.commit()

    new_safe_title = secure_filename(order.title) if order.title else "untitled"
    new_folder_name = f"{order.id}_{new_safe_title}"
    new_folder_path = os.path.join(current_app.root_path, "static", "documents", f"company_{order.company_id}",
                                   new_folder_name)

    # Rename physical folder if title changed and old folder exists
    if old_folder_path != new_folder_path and os.path.exists(old_folder_path):
        os.rename(old_folder_path, new_folder_path)

        # Update stored attachment and document paths in the database to reflect the new folder name
        if order.purchase_order and order.purchase_order.attachment_path:
            order.purchase_order.attachment_path = order.purchase_order.attachment_path.replace(old_folder_name,
                                                                                                new_folder_name)

        for doc in order.documents:
            if doc.filename:
                doc.filename = doc.filename.replace(old_folder_name, new_folder_name)
        db.session.commit()

    flash("Order details updated successfully.")
    return redirect(redirect_target)


@orders_bp.route("/<int:order_id>/mark/<path:new_status>", methods=["POST"])
def mark_status(order_id, new_status):
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=order_id)

    if new_status not in ["PO Received", "Not Received", "Pending", "Delivered", "Partially Delivered"]:
        flash("Invalid status.")
        return redirect(redirect_target)

    order = Order.query.get_or_404(order_id)
    old_status = order.status
    order.status = new_status
    db.session.commit()
    log_action("status_change", "Order", order.id,
               f"Status changed from '{old_status}' to '{new_status}' for {order.client.name}")

    # Notify admins about order status change
    admins = User.query.filter(User.role.in_(["admin", "hr"])).all()
    for u in admins:
        if u.id != getattr(current_user, 'id', None):
            Notification.send(u.id, f"Order #{order.order_number or order.id} status: {old_status} → {new_status}",
                              url_for("orders.view_order", order_id=order.id))

    return redirect(redirect_target)


@orders_bp.route("/<int:order_id>/upload_po", methods=["POST"])
def upload_po(order_id):
    order = Order.query.get_or_404(order_id)
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=order.id)

    po_number = request.form.get("po_number", "")
    po_date_str = request.form.get("po_date", "")
    po_date = datetime.strptime(po_date_str, "%Y-%m-%d").date() if po_date_str else None
    po_status = request.form.get("po_status", "Pending")
    file = request.files.get("po_file")
    attachment_path = None

    if file and file.filename:
        if not validate_upload(file, ALLOWED_DOC_EXTENSIONS):
            flash("PO attachment must be a PDF, JPG, or PNG file.")
            return redirect(redirect_target)

        folder = get_order_folder(current_app, order)
        safe_title = secure_filename(order.title) if order.title else "untitled"
        folder_name = f"{order.id}_{safe_title}"

        filename = secure_filename(f"PO_{file.filename}")
        file.save(os.path.join(folder, filename))
        attachment_path = f"documents/company_{order.company_id}/{folder_name}/{filename}"

    existing_po = order.purchase_order
    if existing_po:
        existing_po.po_number = po_number
        existing_po.po_date = po_date
        existing_po.status = po_status
        if attachment_path:
            existing_po.attachment_path = attachment_path
    else:
        existing_po = PurchaseOrder(
            order_id=order.id, po_number=po_number, po_date=po_date,
            attachment_path=attachment_path, status=po_status
        )
        db.session.add(existing_po)

    db.session.flush()

    # Handle line items
    existing_po.line_items.clear()
    total = 0
    idx = 0
    while True:
        desc = request.form.get(f"items-{idx}-description", "").strip()
        if not desc:
            break
        part_no = request.form.get(f"items-{idx}-part_no", "").strip()
        unit = request.form.get(f"items-{idx}-unit", "").strip()
        qty = float(request.form.get(f"items-{idx}-qty", 1) or 1)
        unit_price = float(request.form.get(f"items-{idx}-unit_price", 0) or 0)
        item = PurchaseOrderLineItem(
            purchase_order_id=existing_po.id,
            description=desc, part_no=part_no, unit=unit,
            qty=qty, unit_price=unit_price
        )
        db.session.add(item)
        total += qty * unit_price
        idx += 1

    existing_po.total_amount = total
    db.session.commit()
    flash("Purchase order saved successfully.")
    return redirect(redirect_target)


@orders_bp.route("/<int:order_id>/extract-po", methods=["POST"])
def extract_po(order_id):
    order = Order.query.get_or_404(order_id)
    file = request.files.get("po_file")

    if not file or not file.filename:
        return jsonify({"error": "No file uploaded"}), 400

    if not validate_upload(file, ALLOWED_DOC_EXTENSIONS):
        return jsonify({"error": "File type not supported. Use PDF, JPG, or PNG."}), 400

    try:
        from ml.tender_extractor import extract_items_from_file, _last_extraction_error
        items = extract_items_from_file(
            file.stream, file.filename,
            force_gemini=True, return_diagnostics=False
        )
        if isinstance(items, dict):
            items = items.get("items", [])
        if not items and _last_extraction_error:
            return jsonify({"error": _last_extraction_error}), 422
        return jsonify({"items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@orders_bp.route("/<int:order_id>/re-stamp-po", methods=["POST"])
def re_stamp_po(order_id):
    order = Order.query.get_or_404(order_id)
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=order_id)

    if not order.purchase_order or not order.purchase_order.attachment_path:
        flash("No PO file found to stamp.")
        return redirect(redirect_target)

    full_po_path = os.path.join(current_app.root_path, "static", order.purchase_order.attachment_path)
    company_obj = db.session.get(Company, order.company_id)
    success = stamp_last_page(full_po_path, full_po_path, company_obj)
    if success:
        flash("PO successfully re-stamped!")
    else:
        flash("Failed to stamp the PO. Check if the signature file exists.")
    return redirect(redirect_target)


@orders_bp.route("/<int:order_id>/delete-po", methods=["POST"])
def delete_po(order_id):
    order = Order.query.get_or_404(order_id)
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=order_id)

    if order.purchase_order:
        if order.purchase_order.attachment_path:
            full_path = os.path.join(current_app.root_path, "static", order.purchase_order.attachment_path)
            if os.path.exists(full_path):
                os.remove(full_path)
        db.session.delete(order.purchase_order)
        db.session.commit()
        flash("PO attachment and record deleted.")
    return redirect(redirect_target)


@orders_bp.route("/<int:order_id>/documents/upload", methods=["POST"])
def upload_document(order_id):
    order = Order.query.get_or_404(order_id)
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=order.id)

    doc_name = request.form.get("doc_name", "").strip()
    doc_date_str = request.form.get("doc_date", "")
    doc_notes = request.form.get("notes", "").strip()
    file = request.files.get("doc_file")

    if not doc_name:
        flash("Please provide a document name.")
        return redirect(redirect_target)

    if not file or not file.filename:
        flash("Please select a file to upload.")
        return redirect(redirect_target)

    if not validate_upload(file, ALLOWED_DOC_EXTENSIONS):
        flash("Invalid file format. Please upload a valid document or image.")
        return redirect(redirect_target)

    doc_date = datetime.strptime(doc_date_str, "%Y-%m-%d").date() if doc_date_str else None

    folder = get_order_folder(current_app, order)
    safe_title = secure_filename(order.title) if order.title else "untitled"
    folder_name = f"{order.id}_{safe_title}"

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    clean_filename = secure_filename(f"DOC_{timestamp}_{file.filename}")
    file.save(os.path.join(folder, clean_filename))

    rel_path = f"documents/company_{order.company_id}/{folder_name}/{clean_filename}"

    new_doc = OrderDocument(
        order_id=order.id,
        name=doc_name,
        doc_date=doc_date,
        filename=rel_path,
        notes=doc_notes,
    )
    db.session.add(new_doc)
    db.session.commit()

    log_action("upload_document", "OrderDocument", new_doc.id, f"Uploaded document '{doc_name}' for Order #{order.id}")
    flash("Document uploaded successfully.")

    return redirect(redirect_target)


@orders_bp.route("/<int:order_id>/documents/<int:doc_id>/delete", methods=["POST"])
def delete_document(order_id, doc_id):
    order = Order.query.get_or_404(order_id)
    doc = OrderDocument.query.get_or_404(doc_id)
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=order.id)

    if doc.order_id != order.id:
        flash("Document does not belong to this order.")
        return redirect(redirect_target)

    full_path = os.path.join(current_app.root_path, "static", doc.filename)
    if os.path.exists(full_path):
        os.remove(full_path)

    doc_name = doc.name
    db.session.delete(doc)
    db.session.commit()

    log_action("delete_document", "OrderDocument", doc_id, f"Deleted document '{doc_name}' from Order #{order.id}")
    flash("Document deleted successfully.")

    return redirect(redirect_target)


@orders_bp.route("/delete/<int:order_id>", methods=["POST"])
@permission_required("delete_orders")
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.list_orders")

    if order.invoice and order.invoice.payments:
        flash("Cannot delete this order — its invoice has payment(s) logged.")
        return redirect(redirect_target)

    safe_title = secure_filename(order.title) if order.title else "untitled"
    folder_name = f"{order.id}_{safe_title}"
    folder = os.path.join(current_app.root_path, "static", "documents", f"company_{order.company_id}", folder_name)

    if os.path.exists(folder):
        shutil.rmtree(folder)

    log_action("delete_order", "Order", order.id, f"Deleted order for {order.client.name}")
    db.session.delete(order)
    db.session.commit()
    flash("Order deleted.")
    return redirect(redirect_target)


@orders_bp.route("/search-preview")
def search_preview():
    company_id = require_active_company()
    if not company_id:
        return jsonify([])
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    search_like = f"%{q}%"
    matches = (
        Order.query.filter(Order.company_id == company_id)
        .filter(
            db.or_(
                Order.title.ilike(search_like),
                Order.order_number.ilike(search_like),
                Order.id.cast(db.String).ilike(search_like),
                Order.quotations.any(Quotation.line_items.any(QuotationLineItem.description.ilike(search_like)))
            )
        )
        .order_by(Order.id.desc())
        .limit(8)
        .all()
    )
    results = []
    for o in matches:
        results.append({
            "id": o.id,
            "order_number": o.order_number,
            "title": o.title or "(no title)",
            "client": o.client.name,
            "status": o.status,
            "quote_number": o.commercial_quotation.quote_number if o.commercial_quotation else None,
        })
    return jsonify(results)