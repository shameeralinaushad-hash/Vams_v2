import os
from datetime import date, datetime
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.utils import secure_filename
from models import db, Quotation, QuotationLineItem, CatalogItem, Order, ClientDocSequence
from utils import get_order_folder
from pdf_templates.quotation_template import generate_quotation_pdf
from audit import log_action
from numbering import build_quotation_number, build_technical_offer_number
from socket_events import emit_company, emit_dashboard_update

api_quotations_bp = Blueprint("api_quotations", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def get_or_create_catalog_item(description):
    description = description.strip()
    item = CatalogItem.query.filter(db.func.lower(CatalogItem.description) == description.lower()).first()
    if not item:
        item = CatalogItem(description=description)
        db.session.add(item)
        db.session.commit()
    return item


def _serialize_quotation_list(quotation):
    order = quotation.order
    client = order.client if order else None

    return {
        "id": quotation.id,
        "quote_number": quotation.quote_number,
        "quote_date": quotation.quote_date.isoformat() if quotation.quote_date else None,
        "doc_type": quotation.doc_type,
        "subject": quotation.subject,
        "is_current": quotation.is_current,
        "pdf_path": quotation.pdf_path,
        "order_id": quotation.order_id,
        "order_number": order.order_number if order else None,
        "client": {
            "id": client.id if client else None,
            "name": client.name if client else None,
        } if client else None,
    }


def _serialize_quotation_detail(quotation):
    order = quotation.order
    client = order.client if order else None
    company = order.company if order else None

    line_items = []
    for li in (quotation.line_items or []):
        line_items.append({
            "id": li.id,
            "part_no": li.part_no,
            "description": li.description,
            "unit": li.unit,
            "qty": li.qty,
            "unit_price": li.unit_price,
            "tax_percent": li.tax_percent,
        })

    return {
        "id": quotation.id,
        "quote_number": quotation.quote_number,
        "quote_date": quotation.quote_date.isoformat() if quotation.quote_date else None,
        "doc_type": quotation.doc_type,
        "subject": quotation.subject,
        "client_ref_number": quotation.client_ref_number,
        "terms_conditions": quotation.terms_conditions,
        "recipient": quotation.recipient,
        "tax_amount": quotation.tax_amount,
        "discount_amount": quotation.discount_amount,
        "installation_charges": quotation.installation_charges,
        "transportation_charges": quotation.transportation_charges,
        "skip_letterhead": quotation.skip_letterhead,
        "show_totals": getattr(quotation, 'show_totals', True),
        "is_current": quotation.is_current,
        "pdf_path": quotation.pdf_path,
        "order_id": quotation.order_id,
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
    }


def _write_quotation_pdf(order, quotation, line_items):
    version_suffix = f"_v{quotation.pdf_version}" if (quotation.pdf_version or 1) > 1 else ""
    folder = get_order_folder(current_app, order)
    filename = f"Quotation_{quotation.quote_number.replace('/', '-')}{version_suffix}.pdf"
    output_path = os.path.join(folder, filename)

    generate_quotation_pdf(
        order.company, order.client, quotation, line_items, output_path,
        skip_letterhead=bool(quotation.skip_letterhead)
    )

    safe_title = secure_filename(order.title) if order.title else "untitled"
    folder_name = f"{order.id}_{safe_title}"
    quotation.pdf_path = f"documents/company_{order.company_id}/{folder_name}/{filename}"
    db.session.commit()


@api_quotations_bp.route("/api/v1/quotations", methods=["GET"])
@jwt_required()
def list_all_quotations():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

    pagination = (
        Quotation.query.join(Order)
        .filter(Order.company_id == company_id)
        .order_by(Quotation.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    results = []
    for q in pagination.items:
        order = q.order
        client = order.client if order else None
        results.append({
            "id": q.id,
            "quote_number": q.quote_number,
            "quote_date": q.quote_date.isoformat() if q.quote_date else None,
            "doc_type": q.doc_type,
            "subject": q.subject,
            "order_id": q.order_id,
            "order_number": order.order_number if order else None,
            "client_name": client.name if client else None,
        })

    return jsonify({
        "success": True,
        "quotations": results,
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
    })


@api_quotations_bp.route("/api/v1/orders/<int:order_id>/quotations")
@jwt_required()
def list_quotations(order_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    order = db.session.get(Order, order_id)
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    quotations = (
        Quotation.query.filter_by(order_id=order_id)
        .order_by(Quotation.id.desc())
        .all()
    )

    return jsonify({
        "success": True,
        "quotations": [_serialize_quotation_list(q) for q in quotations],
    })


@api_quotations_bp.route("/api/v1/quotations/<int:quotation_id>")
@jwt_required()
def get_quotation(quotation_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    quotation = db.session.get(Quotation, quotation_id)
    if not quotation:
        return jsonify({"success": False, "error": "not_found", "message": "Quotation not found."}), 404

    order = quotation.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Quotation not found."}), 404

    return jsonify({"success": True, "quotation": _serialize_quotation_detail(quotation)})


@api_quotations_bp.route("/api/v1/orders/<int:order_id>/quotations", methods=["POST"])
@jwt_required()
def create_quotation(order_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    order = db.session.get(Order, order_id)
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "No data provided."}), 400

    items = data.get("items")
    if not items or not isinstance(items, list) or len(items) == 0:
        return jsonify({"success": False, "error": "validation_error", "message": "At least one item is required."}), 400

    for i, item in enumerate(items):
        if not item.get("description", "").strip():
            return jsonify({"success": False, "error": "validation_error", "message": f"Item {i+1}: description is required."}), 400

    doc_type = data.get("doc_type", "commercial")
    if doc_type not in ("commercial", "technical"):
        doc_type = "commercial"

    seq_doc_type = "technical" if doc_type == "technical" else "quotation"
    seq = ClientDocSequence.get_or_create(order.company_id, order.client_id, seq_doc_type)

    quote_number = data.get("quote_number", "").strip()
    if quote_number:
        if seq:
            seq.get_next_raw_number()
    else:
        raw = seq.get_next_raw_number() if seq else order.id
        if doc_type == "technical":
            quote_number = build_technical_offer_number(order.company, order.client, raw)
        else:
            quote_number = build_quotation_number(order.company, order.client, raw)

    existing = Quotation.query.filter_by(order_id=order.id, doc_type=doc_type).all()
    for old_q in existing:
        old_q.is_current = False
    db.session.commit()

    quote_date_str = data.get("quote_date", "")
    quote_date_val = datetime.strptime(quote_date_str, "%Y-%m-%d").date() if quote_date_str else date.today()

    quotation = Quotation(
        order_id=order.id,
        quote_number=quote_number,
        quote_date=quote_date_val,
        recipient=data.get("recipient", "").strip(),
        subject=data.get("subject", "").strip(),
        client_ref_number=data.get("client_ref_number", "").strip(),
        terms_conditions=data.get("terms_conditions", "").strip(),
        is_current=True,
        pdf_version=1,
        doc_type=doc_type,
        tax_amount=float(data.get("tax_amount", 0) or 0),
        discount_amount=float(data.get("discount_amount", 0) or 0),
        installation_charges=float(data.get("installation_charges", 0) or 0),
        transportation_charges=float(data.get("transportation_charges", 0) or 0),
        skip_letterhead=bool(data.get("skip_letterhead")),
        show_totals=bool(data.get("show_totals", True)),
    )
    db.session.add(quotation)
    db.session.commit()

    line_items = []
    for item in items:
        desc = item.get("description", "").strip()
        if not desc:
            continue
        catalog_item = get_or_create_catalog_item(desc)
        li = QuotationLineItem(
            quotation_id=quotation.id,
            catalog_item_id=catalog_item.id,
            part_no=item.get("part_no", "").strip() if item.get("part_no") else "",
            description=desc,
            unit=item.get("unit", "Nos").strip() if item.get("unit") else "Nos",
            qty=float(item.get("qty", 0) or 0),
            unit_price=float(item.get("unit_price", 0) or 0),
            tax_percent=float(item.get("tax_percent", 0) or 0),
        )
        db.session.add(li)
        line_items.append(li)
    db.session.commit()

    _write_quotation_pdf(order, quotation, line_items)

    log_action("create_quotation", "Quotation", quotation.id, f"Created quotation {quote_number} for {order.client.name}")

    emit_company("list_refresh", {"section": "quotations"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({
        "success": True,
        "quotation": _serialize_quotation_detail(quotation),
    }), 201


@api_quotations_bp.route("/api/v1/quotations/<int:quotation_id>", methods=["DELETE"])
@jwt_required()
def delete_quotation(quotation_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    quotation = db.session.get(Quotation, quotation_id)
    if not quotation:
        return jsonify({"success": False, "error": "not_found", "message": "Quotation not found."}), 404

    order = quotation.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Quotation not found."}), 404

    order_id = quotation.order_id
    was_current = quotation.is_current
    quote_number = quotation.quote_number

    if quotation.pdf_path:
        full_path = os.path.join(current_app.root_path, "static", quotation.pdf_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    db.session.delete(quotation)
    db.session.commit()

    if was_current:
        remaining = Quotation.query.filter_by(order_id=order_id, doc_type=quotation.doc_type).order_by(Quotation.id.desc()).first()
        if remaining:
            remaining.is_current = True
            db.session.commit()

    log_action("delete_quotation", "Quotation", quotation_id, f"Deleted quotation {quote_number}")

    emit_company("list_refresh", {"section": "quotations"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({"success": True, "message": "Quotation deleted."})


@api_quotations_bp.route("/api/v1/quotations/<int:quotation_id>", methods=["PUT"])
@jwt_required()
def edit_quotation(quotation_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    quotation = db.session.get(Quotation, quotation_id)
    if not quotation:
        return jsonify({"success": False, "error": "not_found", "message": "Quotation not found."}), 404

    order = quotation.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Quotation not found."}), 404

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "No data provided."}), 400

    items = data.get("items")
    if not items or not isinstance(items, list) or len(items) == 0:
        return jsonify({"success": False, "error": "validation_error", "message": "At least one item is required."}), 400

    for i, item in enumerate(items):
        if not item.get("description", "").strip():
            return jsonify({"success": False, "error": "validation_error", "message": f"Item {i+1}: description is required."}), 400

    quotation.quote_number = data.get("quote_number", "").strip() or quotation.quote_number
    quotation.doc_type = data.get("doc_type", quotation.doc_type)
    quotation.recipient = data.get("recipient", "").strip() or quotation.recipient
    quotation.subject = data.get("subject", "").strip() or quotation.subject
    quotation.client_ref_number = data.get("client_ref_number", "").strip() or quotation.client_ref_number
    quotation.terms_conditions = data.get("terms_conditions", "").strip() or quotation.terms_conditions
    quotation.tax_amount = float(data.get("tax_amount", 0) or 0)
    quotation.discount_amount = float(data.get("discount_amount", 0) or 0)
    quotation.installation_charges = float(data.get("installation_charges", 0) or 0)
    quotation.transportation_charges = float(data.get("transportation_charges", 0) or 0)
    quotation.skip_letterhead = bool(data.get("skip_letterhead", False))
    quotation.show_totals = bool(data.get("show_totals", True))
    quotation.pdf_version = (quotation.pdf_version or 1) + 1

    quote_date_str = data.get("quote_date", "")
    if quote_date_str:
        quotation.quote_date = datetime.strptime(quote_date_str, "%Y-%m-%d").date()

    db.session.flush()

    for li in list(quotation.line_items):
        db.session.delete(li)
    db.session.flush()

    for ann in list(quotation.annexures):
        db.session.delete(ann)
    db.session.flush()

    line_items = []
    for item in items:
        desc = item.get("description", "").strip()
        if not desc:
            continue
        catalog_item = get_or_create_catalog_item(desc)
        li = QuotationLineItem(
            quotation_id=quotation.id,
            catalog_item_id=catalog_item.id,
            part_no=item.get("part_no", "").strip() if item.get("part_no") else "",
            description=desc,
            unit=item.get("unit", "Nos").strip() if item.get("unit") else "Nos",
            qty=float(item.get("qty", 0) or 0),
            unit_price=float(item.get("unit_price", 0) or 0),
            tax_percent=float(item.get("tax_percent", 0) or 0),
        )
        db.session.add(li)
        line_items.append(li)
    db.session.commit()

    _write_quotation_pdf(order, quotation, line_items)

    log_action("edit_quotation", "Quotation", quotation.id, f"Edited quotation {quotation.quote_number} for {order.client.name}")

    emit_company("list_refresh", {"section": "quotations"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({"success": True, "quotation": _serialize_quotation_detail(quotation)})
