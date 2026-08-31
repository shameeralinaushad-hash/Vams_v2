import os
from datetime import date, datetime
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.utils import secure_filename
from models import db, DeliveryChallan, DeliveryChallanLineItem, CatalogItem, Order, ClientDocSequence
from utils import get_order_folder
from pdf_templates.challan_template import generate_challan_pdf
from audit import log_action
from numbering import build_challan_number
from socket_events import emit_company, emit_dashboard_update

api_challans_bp = Blueprint("api_challans", __name__)


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


def _serialize_challan_list(challan):
    order = challan.order
    client = order.client if order else None

    return {
        "id": challan.id,
        "challan_number": challan.challan_number,
        "dispatch_date": challan.dispatch_date.isoformat() if challan.dispatch_date else None,
        "transport_mode": challan.transport_mode,
        "vehicle_number": challan.vehicle_number,
        "place": challan.place,
        "is_current": challan.is_current,
        "pdf_path": challan.pdf_path,
        "order_id": challan.order_id,
        "order_number": order.order_number if order else None,
        "client": {
            "id": client.id if client else None,
            "name": client.name if client else None,
        } if client else None,
    }


def _serialize_challan_detail(challan):
    order = challan.order
    client = order.client if order else None
    company = order.company if order else None

    line_items = []
    for li in (challan.line_items or []):
        line_items.append({
            "id": li.id,
            "description": li.description,
            "unit": li.unit,
            "qty": li.qty,
        })

    return {
        "id": challan.id,
        "challan_number": challan.challan_number,
        "dispatch_date": challan.dispatch_date.isoformat() if challan.dispatch_date else None,
        "recipient": challan.recipient,
        "transport_mode": challan.transport_mode,
        "vehicle_number": challan.vehicle_number,
        "place": challan.place,
        "skip_letterhead": challan.skip_letterhead,
        "is_current": challan.is_current,
        "pdf_path": challan.pdf_path,
        "order_id": challan.order_id,
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


@api_challans_bp.route("/api/v1/challans", methods=["GET"])
@jwt_required()
def list_all_challans():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

    pagination = (
        DeliveryChallan.query.join(Order)
        .filter(Order.company_id == company_id)
        .order_by(DeliveryChallan.id.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    results = []
    for c in pagination.items:
        order = c.order
        client = order.client if order else None
        results.append({
            "id": c.id,
            "challan_number": c.challan_number,
            "dispatch_date": c.dispatch_date.isoformat() if c.dispatch_date else None,
            "transport_mode": c.transport_mode,
            "order_id": c.order_id,
            "order_number": order.order_number if order else None,
            "client_name": client.name if client else None,
        })

    return jsonify({
        "success": True,
        "challans": results,
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
    })


@api_challans_bp.route("/api/v1/orders/<int:order_id>/challans")
@jwt_required()
def list_challans(order_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    order = db.session.get(Order, order_id)
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    challans = (
        DeliveryChallan.query.filter_by(order_id=order_id)
        .order_by(DeliveryChallan.id.desc())
        .all()
    )

    return jsonify({
        "success": True,
        "challans": [_serialize_challan_list(c) for c in challans],
    })


@api_challans_bp.route("/api/v1/challans/<int:challan_id>")
@jwt_required()
def get_challan(challan_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    challan = db.session.get(DeliveryChallan, challan_id)
    if not challan:
        return jsonify({"success": False, "error": "not_found", "message": "Challan not found."}), 404

    order = challan.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Challan not found."}), 404

    return jsonify({"success": True, "challan": _serialize_challan_detail(challan)})


@api_challans_bp.route("/api/v1/orders/<int:order_id>/challans", methods=["POST"])
@jwt_required()
def create_challan(order_id):
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

    seq = ClientDocSequence.get_or_create(order.company_id, order.client_id, "challan")

    challan_number = data.get("challan_number", "").strip()
    if not challan_number:
        raw = seq.peek_next_raw_number() if seq else order.id
        challan_number = build_challan_number(order.company, order.client, raw)

    existing = DeliveryChallan.query.filter_by(order_id=order.id).all()
    for old_c in existing:
        old_c.is_current = False
    db.session.commit()

    dispatch_date_str = data.get("dispatch_date", "")
    dispatch_date_val = datetime.strptime(dispatch_date_str, "%Y-%m-%d").date() if dispatch_date_str else date.today()

    challan = DeliveryChallan(
        order_id=order.id,
        challan_number=challan_number,
        recipient=data.get("recipient", "").strip(),
        dispatch_date=dispatch_date_val,
        transport_mode=data.get("transport_mode", "").strip(),
        vehicle_number=data.get("vehicle_number", "").strip(),
        place=data.get("place", "").strip(),
        skip_letterhead=bool(data.get("skip_letterhead")),
        is_current=True,
        pdf_version=1,
    )
    db.session.add(challan)
    db.session.commit()

    if seq:
        seq.get_next_raw_number()

    line_items = []
    for item in items:
        desc = item.get("description", "").strip()
        if not desc:
            continue
        catalog_item = get_or_create_catalog_item(desc)
        li = DeliveryChallanLineItem(
            challan_id=challan.id,
            catalog_item_id=catalog_item.id,
            description=desc,
            unit=item.get("unit", "Nos").strip() if item.get("unit") else "Nos",
            qty=float(item.get("qty", 0) or 0),
        )
        db.session.add(li)
        line_items.append(li)
    db.session.commit()

    _write_challan_pdf(order, challan, line_items)

    log_action("create_challan", "DeliveryChallan", challan.id, f"Created delivery challan {challan_number} for {order.client.name}")

    emit_company("list_refresh", {"section": "challans"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({
        "success": True,
        "challan": _serialize_challan_detail(challan),
    }), 201


@api_challans_bp.route("/api/v1/challans/<int:challan_id>", methods=["PUT"])
@jwt_required()
def edit_challan(challan_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    challan = db.session.get(DeliveryChallan, challan_id)
    if not challan:
        return jsonify({"success": False, "error": "not_found", "message": "Challan not found."}), 404

    order = challan.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Challan not found."}), 404

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "No data provided."}), 400

    items = data.get("items")
    if not items or not isinstance(items, list) or len(items) == 0:
        return jsonify({"success": False, "error": "validation_error", "message": "At least one item is required."}), 400

    challan.challan_number = data.get("challan_number", "").strip() or challan.challan_number
    challan.recipient = data.get("recipient", "").strip() or challan.recipient
    challan.transport_mode = data.get("transport_mode", "").strip() or challan.transport_mode
    challan.vehicle_number = data.get("vehicle_number", "").strip() or challan.vehicle_number
    challan.place = data.get("place", "").strip() or challan.place
    challan.skip_letterhead = bool(data.get("skip_letterhead", False))
    challan.pdf_version = (challan.pdf_version or 1) + 1

    dispatch_date_str = data.get("dispatch_date", "")
    if dispatch_date_str:
        challan.dispatch_date = datetime.strptime(dispatch_date_str, "%Y-%m-%d").date()

    db.session.flush()

    for li in list(challan.line_items):
        db.session.delete(li)
    db.session.flush()

    line_items = []
    for item in items:
        desc = item.get("description", "").strip()
        if not desc:
            continue
        catalog_item = get_or_create_catalog_item(desc)
        li = DeliveryChallanLineItem(
            challan_id=challan.id,
            catalog_item_id=catalog_item.id,
            description=desc,
            unit=item.get("unit", "Nos").strip() if item.get("unit") else "Nos",
            qty=float(item.get("qty", 0) or 0),
        )
        db.session.add(li)
        line_items.append(li)
    db.session.commit()

    _write_challan_pdf(order, challan, line_items)

    log_action("edit_challan", "DeliveryChallan", challan.id, f"Edited challan {challan.challan_number} for {order.client.name}")

    emit_company("list_refresh", {"section": "challans"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({"success": True, "challan": _serialize_challan_detail(challan)})


@api_challans_bp.route("/api/v1/challans/<int:challan_id>", methods=["DELETE"])
@jwt_required()
def delete_challan(challan_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    challan = db.session.get(DeliveryChallan, challan_id)
    if not challan:
        return jsonify({"success": False, "error": "not_found", "message": "Challan not found."}), 404

    order = challan.order
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Challan not found."}), 404

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

    emit_company("list_refresh", {"section": "challans"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({"success": True, "message": "Challan deleted."})
