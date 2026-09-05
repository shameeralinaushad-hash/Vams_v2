from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt
from sqlalchemy import Integer, cast
from sqlalchemy.orm import selectinload
from models import db, Order, Client, Company, Quotation, QuotationLineItem, PurchaseOrder, Invoice, DeliveryChallan, Payment, ClientCompanyLink
from socket_events import emit_company, emit_dashboard_update

api_orders_bp = Blueprint("api_orders", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _serialize_order_list(order):
    pos = order.purchase_orders
    client = order.client
    first_quotation = order.quotations[0] if order.quotations else None

    purchase_orders = [
        {
            "id": po.id,
            "po_number": po.po_number,
            "po_date": po.po_date.isoformat() if po.po_date else None,
            "status": po.status,
            "total_amount": float(po.total_amount) if po.total_amount else 0,
        }
        for po in pos
    ]

    return {
        "id": order.id,
        "order_number": order.order_number,
        "title": order.title,
        "status": order.status,
        "inquiry_date": order.inquiry_date.isoformat() if order.inquiry_date else None,
        "client": {
            "id": client.id if client else None,
            "name": client.name if client else None,
        } if client else None,
        "purchase_orders": purchase_orders,
        "quotation_number": first_quotation.quote_number if first_quotation else None,
    }


def _serialize_order_detail(order):
    client = order.client
    company = order.company
    pos = order.purchase_orders

    quotations = []
    for q in order.quotations:
        items = []
        for li in (q.line_items or []):
            items.append({
                "id": li.id,
                "part_no": li.part_no,
                "description": li.description,
                "unit": li.unit,
                "qty": li.qty,
                "unit_price": li.unit_price,
                "tax_percent": li.tax_percent,
            })
        quotations.append({
            "id": q.id,
            "quote_number": q.quote_number,
            "quote_date": q.quote_date.isoformat() if q.quote_date else None,
            "doc_type": q.doc_type,
            "subject": q.subject,
            "tax_amount": q.tax_amount,
            "discount_amount": q.discount_amount,
            "pdf_path": q.pdf_path,
            "line_items": items,
        })

    invoices = []
    for inv in order.invoices:
        payments = [{"id": p.id, "amount": p.amount, "paid_date": p.paid_date.isoformat() if p.paid_date else None, "method": p.method} for p in inv.payments]
        inv_po = inv.purchase_order
        invoices.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
            "total_amount": inv.total_amount,
            "status": inv.status,
            "balance_due": inv.balance_due(),
            "total_paid": inv.total_paid(),
            "is_fully_paid": inv.is_fully_paid(),
            "pdf_path": inv.pdf_path,
            "purchase_order_id": inv.purchase_order_id,
            "purchase_order_number": inv_po.po_number if inv_po else None,
            "payments": payments,
        })

    challans = []
    for c in order.delivery_challans:
        c_po = c.purchase_order
        challans.append({
            "id": c.id,
            "challan_number": c.challan_number,
            "dispatch_date": c.dispatch_date.isoformat() if c.dispatch_date else None,
            "transport_mode": c.transport_mode,
            "pdf_path": c.pdf_path,
            "purchase_order_id": c.purchase_order_id,
            "purchase_order_number": c_po.po_number if c_po else None,
        })

    purchase_orders = [
        {
            "id": po.id,
            "po_number": po.po_number,
            "po_date": po.po_date.isoformat() if po.po_date else None,
            "status": po.status,
            "total_amount": float(po.total_amount) if po.total_amount else 0,
            "line_items": [
                {
                    "id": li.id,
                    "description": li.description,
                    "part_no": li.part_no,
                    "unit": li.unit,
                    "qty": li.qty,
                    "unit_price": float(li.unit_price) if li.unit_price else 0,
                }
                for li in po.line_items
            ],
        }
        for po in pos
    ]

    return {
        "id": order.id,
        "order_number": order.order_number,
        "title": order.title,
        "status": order.status,
        "inquiry_date": order.inquiry_date.isoformat() if order.inquiry_date else None,
        "notes": order.notes,
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
        "purchase_orders": purchase_orders,
        "quotations": quotations,
        "invoices": invoices,
        "delivery_challans": challans,
    }


@api_orders_bp.route("/api/v1/orders")
@jwt_required()
def list_orders():
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
        Order.query.filter_by(company_id=company_id)
        .outerjoin(Quotation)
        .join(Client)
        .options(
            db.contains_eager(Order.client),
            db.selectinload(Order.purchase_orders),
            db.selectinload(Order.quotations),
        )
    )

    if status:
        query = query.filter(Order.status == status)
    if client_id:
        query = query.filter(Order.client_id == client_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Order.id.cast(db.String).like(like),
                Order.order_number.ilike(like),
                Order.title.ilike(like),
                Quotation.quote_number.ilike(like),
            )
        )

    sort_map = {
        "id": Order.id,
        "order_number": Order.order_number,
        "client": Client.name,
        "quote_number": Quotation.quote_number,
    }
    sort_col = sort_map.get(sort_by, Order.id)
    query = query.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "success": True,
        "orders": [_serialize_order_list(o) for o in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
        "per_page": per_page,
    })


@api_orders_bp.route("/api/v1/orders/<int:order_id>")
@jwt_required()
def get_order(order_id):
    company_id = _get_company_id()
    order = db.session.query(Order).options(
        selectinload(Order.quotations),
        selectinload(Order.invoices).selectinload(Invoice.payments),
        selectinload(Order.invoices).selectinload(Invoice.credit_notes),
        selectinload(Order.invoices).selectinload(Invoice.purchase_order),
        selectinload(Order.delivery_challans).selectinload(DeliveryChallan.purchase_order),
        selectinload(Order.purchase_orders).selectinload(PurchaseOrder.line_items),
        selectinload(Order.documents),
    ).filter(Order.id == order_id).first()
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    return jsonify({"success": True, "order": _serialize_order_detail(order)})


@api_orders_bp.route("/api/v1/orders/search")
@jwt_required()
def search_orders():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify({"success": True, "results": []})

    like = f"%{q}%"
    orders = (
        Order.query.filter_by(company_id=company_id)
        .join(Client, Order.client_id == Client.id)
        .outerjoin(Quotation)
        .options(db.contains_eager(Order.client))
        .filter(
            db.or_(
                Order.order_number.ilike(like),
                Order.title.ilike(like),
                Client.name.ilike(like),
                Quotation.quote_number.ilike(like),
            )
        )
        .order_by(Order.id.desc())
        .limit(10)
        .all()
    )

    results = []
    seen = set()
    for o in orders:
        if o.id in seen:
            continue
        seen.add(o.id)
        results.append({
            "id": o.id,
            "order_number": o.order_number,
            "title": o.title,
            "client": o.client.name if o.client else None,
            "status": o.status,
        })

    return jsonify({"success": True, "results": results})


@api_orders_bp.route("/api/v1/orders", methods=["POST"])
@jwt_required()
def create_order():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    client_id = data.get("client_id")
    if not client_id:
        return jsonify({"success": False, "error": "validation_error", "message": "client_id is required."}), 400

    client = db.session.get(Client, int(client_id))
    if not client:
        return jsonify({"success": False, "error": "not_found", "message": "Client not found."}), 404

    max_num = db.session.query(
        db.func.max(cast(Order.order_number, Integer))
    ).filter_by(company_id=company_id).scalar()
    order_number = str((max_num or 0) + 1)

    order = Order(
        company_id=company_id,
        client_id=client.id,
        title=data.get("title", "").strip(),
        notes=data.get("notes", "").strip(),
        status="Pending",
        order_number=order_number,
        inquiry_date=datetime.utcnow(),
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({
        "success": True,
        "order": {
            "id": order.id,
            "order_number": order.order_number,
            "title": order.title,
            "status": order.status,
            "client": {"id": client.id, "name": client.name},
        },
    }), 201


VALID_STATUSES = ["Pending", "In Progress", "PO Received", "Delivered", "Cancelled", "On Hold"]


@api_orders_bp.route("/api/v1/orders/<int:order_id>", methods=["PUT"])
@jwt_required()
def edit_order(order_id):
    """Edit order title, notes, and status."""
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    order = db.session.get(Order, order_id)
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    if "title" in data:
        order.title = data["title"].strip() if data["title"] else ""

    if "notes" in data:
        order.notes = data["notes"].strip() if data["notes"] else ""

    if "status" in data:
        new_status = data["status"]
        if new_status not in VALID_STATUSES:
            return jsonify({"success": False, "error": "validation_error", "message": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"}), 400
        order.status = new_status

    db.session.commit()

    try:
        emit_company("list_refresh", {"section": "orders"}, order.company_id)
        emit_dashboard_update(order.company_id)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "order": _serialize_order_detail(order),
    })


@api_orders_bp.route("/api/v1/orders/<int:order_id>", methods=["DELETE"])
@jwt_required()
def delete_order(order_id):
    """Delete an order. Fails if it has quotations, invoices, or challans."""
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    order = db.session.query(Order).options(
        selectinload(Order.quotations),
        selectinload(Order.invoices),
        selectinload(Order.delivery_challans),
    ).filter(Order.id == order_id).first()
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    if order.quotations:
        return jsonify({"success": False, "error": "has_quotations", "message": "Cannot delete order with quotations. Delete quotations first."}), 400

    if order.invoices:
        return jsonify({"success": False, "error": "has_invoices", "message": "Cannot delete order with invoices. Delete invoices first."}), 400

    if order.delivery_challans:
        return jsonify({"success": False, "error": "has_challans", "message": "Cannot delete order with delivery challans. Delete challans first."}), 400

    order_id = order.id
    company_id = order.company_id
    db.session.delete(order)
    db.session.commit()

    try:
        emit_company("list_refresh", {"section": "orders"}, company_id)
        emit_dashboard_update(company_id)
    except Exception:
        pass

    return jsonify({"success": True, "message": "Order deleted."})


@api_orders_bp.route("/api/v1/orders/<int:order_id>/status", methods=["POST"])
@jwt_required()
def change_order_status(order_id):
    """Change order status."""
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    order = db.session.get(Order, order_id)
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("status"):
        return jsonify({"success": False, "error": "validation_error", "message": "status is required."}), 400

    new_status = data["status"]
    if new_status not in VALID_STATUSES:
        return jsonify({"success": False, "error": "validation_error", "message": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"}), 400

    order.status = new_status
    db.session.commit()

    try:
        emit_company("list_refresh", {"section": "orders"}, order.company_id)
        emit_dashboard_update(order.company_id)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "order": _serialize_order_detail(order),
    })

@api_orders_bp.route("/api/v1/orders/<int:order_id>/po", methods=["POST"])
@jwt_required()
def add_po(order_id):
    """Add or update purchase order for an order."""
    from werkzeug.utils import secure_filename
    from flask import current_app
    import os

    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    order = db.session.get(Order, order_id)
    if not order or order.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Order not found."}), 404

    data = request.get_json(silent=True) or {}
    po_id = data.get("po_id")
    po = None

    if attachment_path not in locals():
        attachment_path = None

    if po_id:
        po = db.session.get(PurchaseOrder, po_id)
        if not po or po.order_id != order.id:
            return jsonify({"success": False, "error": "not_found", "message": "Purchase order not found."}), 404

    if "file" in request.files:
        file = request.files["file"]
        if file.filename:
            allowed = ("pdf", "png", "jpg", "jpeg", "doc", "docx")
            if not any(file.filename.lower().endswith(ext) for ext in allowed):
                return jsonify({"success": False, "error": "validation_error", "message": "Accepted: PDF, PNG, JPG, DOC, DOCX."}), 400

            fname = secure_filename(file.filename)
            upload_dir = os.path.join(current_app.root_path, "static", "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            save_path = os.path.join(upload_dir, f"po_{order_id}_{fname}")
            file.save(save_path)
            attachment_path = f"uploads/po_{order_id}_{fname}"
        else:
            attachment_path = None
    else:
        attachment_path = None

    if not po:
        po = PurchaseOrder(
            order_id=order.id,
            po_number=data.get("po_number", ""),
            po_date=datetime.strptime(data["po_date"], "%Y-%m-%d").date() if data.get("po_date") else None,
            status=data.get("status", "Pending"),
            total_amount=float(data.get("total_amount", 0) or 0),
            attachment_path=attachment_path,
        )
        db.session.add(po)
    else:
        if data.get("po_number"):
            po.po_number = data["po_number"]
        if data.get("po_date"):
            po.po_date = datetime.strptime(data["po_date"], "%Y-%m-%d").date()
        if data.get("status"):
            po.status = data["status"]
        if data.get("total_amount") is not None:
            po.total_amount = float(data["total_amount"] or 0)
        if attachment_path:
            po.attachment_path = attachment_path

    db.session.commit()

    emit_company("list_refresh", {"section": "orders"}, order.company_id)
    emit_dashboard_update(order.company_id)

    return jsonify({
        "success": True,
        "purchase_order": {
            "id": po.id,
            "po_number": po.po_number,
            "po_date": po.po_date.isoformat() if po.po_date else None,
            "status": po.status,
            "total_amount": float(po.total_amount) if po.total_amount else 0,
            "attachment_path": po.attachment_path,
        },
    })
