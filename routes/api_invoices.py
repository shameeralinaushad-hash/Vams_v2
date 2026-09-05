from datetime import date, datetime
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.utils import secure_filename
from sqlalchemy.orm import selectinload
from models import db, Invoice, InvoiceLineItem, Payment, CreditNote, Order, Client, CatalogItem, ClientDocSequence, PriceHistory
from numbering import build_invoice_number
from utils import get_order_folder
from pdf_templates.invoice_template import generate_invoice_pdf
from socket_events import emit_company, emit_dashboard_update

api_invoices_bp = Blueprint("api_invoices", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _serialize_invoice_list(invoice):
    order = invoice.order
    client = order.client if order else None

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "total_amount": invoice.total_amount,
        "status": invoice.status,
        "balance_due": invoice.balance_due(),
        "total_paid": invoice.total_paid(),
        "is_fully_paid": invoice.is_fully_paid(),
        "order_id": invoice.order_id,
        "order_number": order.order_number if order else None,
        "client": {
            "id": client.id if client else None,
            "name": client.name if client else None,
        } if client else None,
    }


def _serialize_invoice_detail(invoice):
    order = invoice.order
    client = order.client if order else None
    company = order.company if order else None

    line_items = []
    for li in (invoice.line_items or []):
        line_items.append({
            "id": li.id,
            "part_no": li.part_no,
            "description": li.description,
            "unit": li.unit,
            "qty": li.qty,
            "unit_price": li.unit_price,
            "tax_percent": li.tax_percent,
        })

    payments = []
    for p in (invoice.payments or []):
        payments.append({
            "id": p.id,
            "amount": p.amount,
            "paid_date": p.paid_date.isoformat() if p.paid_date else None,
            "method": p.method,
            "notes": p.notes,
        })

    credit_notes = []
    for c in (invoice.credit_notes or []):
        credit_notes.append({
            "id": c.id,
            "credit_number": c.credit_number,
            "credit_date": c.credit_date.isoformat() if c.credit_date else None,
            "amount": c.amount,
            "reason": c.reason,
        })

    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        "total_amount": invoice.total_amount,
        "status": invoice.status,
        "balance_due": invoice.balance_due(),
        "total_paid": invoice.total_paid(),
        "is_fully_paid": invoice.is_fully_paid(),
        "discount_amount": invoice.discount_amount,
        "installation_charges": invoice.installation_charges,
        "transportation_charges": invoice.transportation_charges,
        "tax_amount": invoice.tax_amount,
        "pdf_path": invoice.pdf_path,
        "recipient": invoice.recipient,
        "order_id": invoice.order_id,
        "order": {
            "id": order.id if order else None,
            "order_number": order.order_number if order else None,
            "title": order.title if order else None,
        } if order else None,
        "client": {
            "id": client.id if client else None,
            "name": client.name if client else None,
            "email": client.email if client else None,
            "contact_info": client.contact_info if client else None,
        } if client else None,
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else None,
        } if company else None,
        "line_items": line_items,
        "payments": payments,
        "credit_notes": credit_notes,
    }


@api_invoices_bp.route("/api/v1/invoices")
@jwt_required()
def list_invoices():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(per_page, 100)

    status = request.args.get("status")
    client_id = request.args.get("client_id", type=int)
    search = request.args.get("search", "").strip()
    sort_by = request.args.get("sort_by", "id")
    sort_dir = request.args.get("sort_dir", "desc")

    query = (
        Invoice.query
        .join(Order, Invoice.order_id == Order.id)
        .join(Client, Order.client_id == Client.id)
        .filter(Order.company_id == company_id)
        .options(
            db.joinedload(Invoice.order).joinedload(Order.client),
        )
    )

    if status:
        query = query.filter(Invoice.status == status)
    if client_id:
        query = query.filter(Order.client_id == client_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Invoice.invoice_number.ilike(like),
                Client.name.ilike(like),
                Order.order_number.ilike(like),
            )
        )

    sort_map = {
        "id": Invoice.id,
        "invoice_number": Invoice.invoice_number,
        "invoice_date": Invoice.invoice_date,
        "total_amount": Invoice.total_amount,
        "client": Client.name,
    }
    sort_col = sort_map.get(sort_by, Invoice.id)
    query = query.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "success": True,
        "invoices": [_serialize_invoice_list(i) for i in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
        "per_page": per_page,
    })


@api_invoices_bp.route("/api/v1/invoices/<int:invoice_id>")
@jwt_required()
def get_invoice(invoice_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    invoice = db.session.query(Invoice).options(
        selectinload(Invoice.order),
        selectinload(Invoice.line_items),
        selectinload(Invoice.payments),
        selectinload(Invoice.credit_notes),
    ).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    order = invoice.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    return jsonify({"success": True, "invoice": _serialize_invoice_detail(invoice)})


@api_invoices_bp.route("/api/v1/invoices/search")
@jwt_required()
def search_invoices():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify({"success": True, "results": []})

    like = f"%{q}%"
    invoices = (
        Invoice.query
        .join(Order, Invoice.order_id == Order.id)
        .join(Client, Order.client_id == Client.id)
        .filter(Order.company_id == company_id)
        .filter(
            db.or_(
                Invoice.invoice_number.ilike(like),
                Client.name.ilike(like),
                Order.order_number.ilike(like),
            )
        )
        .order_by(Invoice.id.desc())
        .limit(10)
        .all()
    )

    results = []
    seen = set()
    for inv in invoices:
        if inv.id in seen:
            continue
        seen.add(inv.id)
        order = inv.order
        client = order.client if order else None
        results.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "client": client.name if client else None,
            "total_amount": inv.total_amount,
            "status": inv.status,
        })

    return jsonify({"success": True, "results": results})


@api_invoices_bp.route("/api/v1/payments", methods=["GET"])
@jwt_required()
def list_all_payments():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

    pagination = (
        Payment.query
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .join(Order, Invoice.order_id == Order.id)
        .filter(Order.company_id == company_id)
        .order_by(Payment.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    results = []
    for p in pagination.items:
        inv = p.invoice
        order = inv.order if inv else None
        client = order.client if order else None
        results.append({
            "id": p.id,
            "invoice_id": p.invoice_id,
            "amount": p.amount,
            "paid_date": p.paid_date.isoformat() if p.paid_date else None,
            "method": p.method,
            "notes": p.notes,
            "invoice_number": inv.invoice_number if inv else None,
            "client_name": client.name if client else None,
        })

    return jsonify({
        "success": True,
        "payments": results,
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
    })


@api_invoices_bp.route("/api/v1/invoices/<int:invoice_id>/payments", methods=["POST"])
@jwt_required()
def add_payment(invoice_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    order = invoice.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "No data provided."}), 400

    amount = data.get("amount")
    if not amount or float(amount) <= 0:
        return jsonify({"success": False, "error": "validation_error", "message": "Valid payment amount is required."}), 400

    payment = Payment(
        invoice_id=invoice.id,
        amount=float(amount),
        method=data.get("method", ""),
        notes=data.get("notes", ""),
    )
    db.session.add(payment)
    db.session.commit()

    return jsonify({
        "success": True,
        "payment": {
            "id": payment.id,
            "amount": payment.amount,
            "paid_date": payment.paid_date.isoformat() if payment.paid_date else None,
            "method": payment.method,
            "notes": payment.notes,
        },
        "invoice": {
            "balance_due": invoice.balance_due(),
            "total_paid": invoice.total_paid(),
            "is_fully_paid": invoice.is_fully_paid(),
        },
    }), 201


def _get_or_create_catalog_item(description):
    description = description.strip()
    item = CatalogItem.query.filter(db.func.lower(CatalogItem.description) == description.lower()).first()
    if not item:
        item = CatalogItem(description=description)
        db.session.add(item)
        db.session.commit()
    return item


def _build_invoice_line_items(invoice, items_data, order):
    line_items = []
    for item in items_data:
        desc = (item.get("description") or "").strip()
        if not desc:
            continue
        catalog_item = _get_or_create_catalog_item(desc)
        unit_price = float(item.get("unit_price", 0) or 0)
        li = InvoiceLineItem(
            invoice_id=invoice.id,
            catalog_item_id=catalog_item.id,
            part_no=(item.get("part_no") or "").strip(),
            description=desc,
            unit=(item.get("unit") or "Nos").strip(),
            qty=float(item.get("qty", 0) or 0),
            unit_price=unit_price,
            tax_percent=float(item.get("tax_percent", 0) or 0),
        )
        db.session.add(li)
        line_items.append(li)
        db.session.add(PriceHistory(
            catalog_item_id=catalog_item.id,
            client_id=order.client_id,
            company_id=order.company_id,
            price=unit_price,
            quoted_date=date.today(),
            source_doc="invoice",
        ))
    return line_items


def _write_invoice_pdf(order, invoice, line_items):
    version_suffix = f"_v{invoice.pdf_version}" if (invoice.pdf_version or 1) > 1 else ""
    folder = get_order_folder(current_app, order)
    filename = f"Invoice_{invoice.invoice_number.replace('/', '-')}{version_suffix}.pdf"
    output_path = __import__("os").path.join(folder, filename)
    total = generate_invoice_pdf(order.company, order.client, invoice, line_items, output_path,
                                 skip_letterhead=bool(invoice.skip_letterhead))
    safe_title = secure_filename(order.title) if order.title else "untitled"
    folder_name = f"{order.id}_{safe_title}"
    invoice.pdf_path = f"documents/company_{order.company_id}/{folder_name}/{filename}"
    invoice.total_amount = total
    db.session.commit()


@api_invoices_bp.route("/api/v1/orders/<int:order_id>/invoices", methods=["POST"])
@jwt_required()
def create_invoice(order_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    order = db.session.query(Order).options(
        selectinload(Order.company),
        selectinload(Order.client),
    ).filter(Order.id == order_id).first()
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    items = data.get("items", [])
    if not items:
        return jsonify({"success": False, "error": "validation_error", "message": "At least one line item is required."}), 400

    seq = ClientDocSequence.get_or_create(order.company_id, order.client_id, "invoice")
    invoice_number = (data.get("invoice_number") or "").strip()
    if invoice_number:
        if seq:
            seq.get_next_raw_number()
    else:
        raw = seq.get_next_raw_number() if seq else order.id
        invoice_number = build_invoice_number(order.company, order.client, raw)

    invoice_date_str = data.get("invoice_date", "")
    invoice_date_val = datetime.strptime(invoice_date_str, "%Y-%m-%d").date() if invoice_date_str else date.today()

    existing = Invoice.query.filter_by(order_id=order.id).all()
    for old_inv in existing:
        old_inv.is_current = False
    db.session.commit()

    invoice = Invoice(
        order_id=order.id,
        invoice_number=invoice_number,
        invoice_date=invoice_date_val,
        discount_amount=float(data.get("discount_amount", 0) or 0),
        installation_charges=float(data.get("installation_charges", 0) or 0),
        transportation_charges=float(data.get("transportation_charges", 0) or 0),
        tax_amount=float(data.get("tax_amount", 0) or 0),
        skip_letterhead=bool(data.get("skip_letterhead")),
        recipient=(data.get("recipient") or "").strip() or None,
        is_current=True,
        pdf_version=1,
    )
    db.session.add(invoice)
    db.session.commit()

    line_items = _build_invoice_line_items(invoice, items, order)
    db.session.commit()

    from background import run_in_background
    run_in_background(_write_invoice_pdf, order, invoice, line_items,
                      _app=current_app._get_current_object())

    emit_company("list_refresh", {"section": "invoices"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({
        "success": True,
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "total_amount": invoice.total_amount,
            "pdf_path": invoice.pdf_path,
        },
    }), 201


@api_invoices_bp.route("/api/v1/invoices/<int:invoice_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_invoice(invoice_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    order = invoice.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    invoice.status = "cancelled"
    db.session.commit()

    emit_company("list_refresh", {"section": "invoices"}, company_id)
    emit_dashboard_update(company_id)

    return jsonify({"success": True, "message": "Invoice cancelled."})


@api_invoices_bp.route("/api/v1/invoices/<int:invoice_id>", methods=["DELETE"])
@jwt_required()
def delete_invoice(invoice_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    invoice = db.session.query(Invoice).options(
        selectinload(Invoice.order),
        selectinload(Invoice.payments),
    ).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    order = invoice.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    if invoice.payments:
        return jsonify({"success": False, "error": "validation_error", "message": "Cannot delete invoice with payments."}), 400

    order_id = invoice.order_id
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

    emit_company("list_refresh", {"section": "invoices"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({"success": True, "message": "Invoice deleted."})


@api_invoices_bp.route("/api/v1/invoices/<int:invoice_id>", methods=["PUT"])
@jwt_required()
def edit_invoice(invoice_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    invoice = db.session.query(Invoice).options(
        selectinload(Invoice.order),
        selectinload(Invoice.line_items),
    ).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    order = invoice.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Invoice not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    items = data.get("items", [])
    if not items or not isinstance(items, list) or len(items) == 0:
        return jsonify({"success": False, "error": "validation_error", "message": "At least one line item is required."}), 400

    for i, item in enumerate(items):
        if not item.get("description", "").strip():
            return jsonify({"success": False, "error": "validation_error", "message": f"Item {i+1}: description is required."}), 400

    invoice.invoice_number = data.get("invoice_number", "").strip() or invoice.invoice_number
    invoice.recipient = data.get("recipient", "").strip() or invoice.recipient
    invoice.discount_amount = float(data.get("discount_amount", 0) or 0)
    invoice.installation_charges = float(data.get("installation_charges", 0) or 0)
    invoice.transportation_charges = float(data.get("transportation_charges", 0) or 0)
    invoice.tax_amount = float(data.get("tax_amount", 0) or 0)
    invoice.skip_letterhead = bool(data.get("skip_letterhead", False))
    invoice.pdf_version = (invoice.pdf_version or 1) + 1

    invoice_date_str = data.get("invoice_date", "")
    if invoice_date_str:
        invoice.invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d").date()

    db.session.flush()

    for li in list(invoice.line_items):
        db.session.delete(li)
    db.session.flush()

    line_items = _build_invoice_line_items(invoice, items, order)
    db.session.commit()

    from background import run_in_background
    run_in_background(_write_invoice_pdf, order, invoice, line_items,
                      _app=current_app._get_current_object())

    log_action("edit_invoice", "Invoice", invoice.id, f"Edited invoice {invoice.invoice_number} for {order.client.name}")

    emit_company("list_refresh", {"section": "invoices"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({
        "success": True,
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "total_amount": invoice.total_amount,
            "pdf_path": invoice.pdf_path,
        },
    })
