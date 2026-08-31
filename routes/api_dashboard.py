from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime, timedelta
from sqlalchemy import func
from models import db, Order, Invoice, Client, PurchaseOrder, Quotation, TeamTask, PersonalItem, Employee

api_dashboard_bp = Blueprint("api_dashboard", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


@api_dashboard_bp.route("/api/v1/dashboard")
@jwt_required()
def get_dashboard():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    orders = Order.query.filter_by(company_id=company_id).all()

    total_orders = len(orders)
    won_count = sum(1 for o in orders if o.status == "PO Received")
    not_received_count = sum(1 for o in orders if o.status == "Not Received")
    pending_count = sum(1 for o in orders if o.status == "Pending")
    delivered_count = sum(1 for o in orders if o.status == "Delivered")

    decided = won_count + not_received_count
    win_rate = round((won_count / decided) * 100, 1) if decided > 0 else None

    total_revenue = 0
    total_paid = 0
    total_outstanding = 0
    for o in orders:
        for inv in o.invoices:
            if inv.status != "cancelled":
                total_revenue += inv.total_amount
                total_paid += inv.total_paid()
                total_outstanding += inv.balance_due()

    po_pending = sum(1 for o in orders if o.purchase_order and o.purchase_order.status == "Pending")
    po_received = sum(1 for o in orders if o.purchase_order and o.purchase_order.status == "Received")
    po_delivered = sum(1 for o in orders if o.purchase_order and o.purchase_order.status == "Delivered")
    po_cancelled = sum(1 for o in orders if o.purchase_order and o.purchase_order.status == "Cancelled")

    recent_orders = (
        Order.query.filter_by(company_id=company_id)
        .join(Client, Order.client_id == Client.id, isouter=True)
        .options(db.joinedload(Order.client), db.joinedload(Order.purchase_order))
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )

    recent = []
    for o in recent_orders:
        po = o.purchase_order
        recent.append({
            "id": o.id,
            "order_number": o.order_number,
            "title": o.title,
            "status": o.status,
            "inquiry_date": o.inquiry_date.isoformat() if o.inquiry_date else None,
            "client": o.client.name if o.client else None,
            "po_status": po.status if po else None,
            "po_amount": po.total_amount if po else None,
        })

    client_count = (
        db.session.query(func.count(db.distinct(Client.id)))
        .filter(Client.company_links.any(company_id=company_id))
        .scalar()
    )

    user_id = int(get_jwt_identity())
    employee = Employee.query.filter_by(user_id=user_id, company_id=company_id, is_active=True).first()

    assigned_tasks = []
    if employee:
        tasks = (
            TeamTask.query.filter_by(assignee_id=employee.id)
            .filter(TeamTask.status != "done")
            .order_by(TeamTask.due_date.asc().nullslast(), TeamTask.created_at.desc())
            .limit(10)
            .all()
        )
        for t in tasks:
            assigned_tasks.append({
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "order_number": t.order.order_number if t.order else None,
            })

    personal_tasks = []
    p_items = (
        PersonalItem.query.filter_by(user_id=user_id)
        .filter(PersonalItem.status != "done")
        .order_by(PersonalItem.due_date.asc().nullslast(), PersonalItem.created_at.desc())
        .limit(10)
        .all()
    )
    for p in p_items:
        personal_tasks.append({
            "id": p.id,
            "title": p.title,
            "lane": p.lane,
            "status": p.status,
            "priority": p.priority,
            "due_date": p.due_date.isoformat() if p.due_date else None,
        })

    return jsonify({
        "success": True,
        "stats": {
            "total_orders": total_orders,
            "won_count": won_count,
            "pending_count": pending_count,
            "not_received_count": not_received_count,
            "delivered_count": delivered_count,
            "win_rate": win_rate,
            "total_revenue": total_revenue,
            "total_paid": total_paid,
            "total_outstanding": total_outstanding,
            "po_pending": po_pending,
            "po_received": po_received,
            "po_delivered": po_delivered,
            "po_cancelled": po_cancelled,
            "client_count": client_count,
        },
        "recent_orders": recent,
        "assigned_tasks": assigned_tasks,
        "personal_tasks": personal_tasks,
    })
