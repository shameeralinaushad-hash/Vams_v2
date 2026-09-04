from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime, timedelta, date
from sqlalchemy import func
from models import db, Order, Invoice, Client, PurchaseOrder, Quotation, TeamTask, PersonalItem, Employee, Todo, Expense, ActionSnooze
from important_actions import build_actions, DEFAULT_SNOOZE_HOURS

api_dashboard_bp = Blueprint("api_dashboard", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _get_greeting():
    from zoneinfo import ZoneInfo
    hour = datetime.now(ZoneInfo("Asia/Karachi")).hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    return "Good evening"


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

    po_pending = sum(1 for o in orders if o.purchase_orders and any(po.status == "Pending" for po in o.purchase_orders))
    po_received = sum(1 for o in orders if o.purchase_orders and any(po.status == "Received" for po in o.purchase_orders))
    po_delivered = sum(1 for o in orders if o.purchase_orders and any(po.status == "Delivered" for po in o.purchase_orders))
    po_cancelled = sum(1 for o in orders if o.purchase_orders and any(po.status == "Cancelled" for po in o.purchase_orders))

    recent_orders = (
        Order.query.filter_by(company_id=company_id)
        .join(Client, Order.client_id == Client.id, isouter=True)
        .options(db.joinedload(Order.client), db.selectinload(Order.purchase_orders))
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )

    recent = []
    for o in recent_orders:
        po = o.purchase_orders[0] if o.purchase_orders else None
        recent.append({
            "id": o.id,
            "order_number": o.order_number,
            "title": o.title,
            "status": o.status,
            "inquiry_date": o.inquiry_date.isoformat() if o.inquiry_date else None,
            "client": o.client.name if o.client else None,
            "po_status": po.status if po else None,
            "po_amount": float(po.total_amount) if po and po.total_amount else None,
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

    # --- Important actions ---
    today = date.today()
    overdue_invoices = []
    for o in orders:
        for inv in o.invoices:
            if inv.status != "cancelled" and not inv.is_fully_paid() and inv.days_overdue() >= 30:
                overdue_invoices.append(inv)

    pending_orders = [o for o in orders if o.status == "Pending"]
    no_quotation_orders = [o for o in orders if o.status == "Pending" and not o.quotation]

    snooze_rows = ActionSnooze.query.filter(
        ActionSnooze.company_id == company_id,
        ActionSnooze.snoozed_until > datetime.utcnow(),
    ).all()
    snooze_keys = {(s.source, s.source_id) for s in snooze_rows}

    team_tasks_for_actions = []
    if employee:
        team_tasks_for_actions = (
            TeamTask.query.filter_by(assignee_id=employee.id)
            .filter(TeamTask.status != "done")
            .order_by(TeamTask.due_date.asc().nullslast(), TeamTask.created_at.desc())
            .limit(10)
            .all()
        )

    actions = build_actions(
        company_id=company_id,
        overdue_invoices=overdue_invoices,
        pending=pending_orders,
        no_quotation_orders=no_quotation_orders,
        team_tasks=team_tasks_for_actions,
        snooze_keys=snooze_keys,
    )

    # --- Financial summary ---
    total_expenses = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(Expense.company_id == company_id).scalar()
    estimated_profit = total_revenue - total_expenses

    # --- Todos ---
    priority_order = db.case(
        (Todo.priority == "high", 0), (Todo.priority == "medium", 1), (Todo.priority == "low", 2), else_=1
    )
    todos = Todo.query.filter_by(company_id=company_id).order_by(
        Todo.is_done.asc(), priority_order, Todo.due_date.is_(None), Todo.due_date.asc()
    ).limit(10).all()
    todos_list = [{
        "id": t.id, "text": t.text, "is_done": t.is_done,
        "priority": t.priority, "due_date": t.due_date.isoformat() if t.due_date else None,
    } for t in todos]

    return jsonify({
        "success": True,
        "greeting": _get_greeting(),
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
        "financial_summary": {
            "total_revenue": total_revenue,
            "total_outstanding": total_outstanding,
            "total_profit": estimated_profit,
        },
        "important_actions": actions,
        "todos": todos_list,
        "recent_orders": recent,
        "assigned_tasks": assigned_tasks,
        "personal_tasks": personal_tasks,
    })


@api_dashboard_bp.route("/api/v1/dashboard/actions/dismiss", methods=["POST"])
@jwt_required()
def dismiss_action():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "message": "No active company."}), 400

    data = request.get_json(silent=True) or {}
    source = (data.get("source") or "").strip()
    if not source:
        return jsonify({"success": False, "message": "Missing source."}), 400

    try:
        source_id = int(data.get("source_id")) if data.get("source_id") else None
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Bad source_id."}), 400

    try:
        hours = float(data.get("snooze_hours", DEFAULT_SNOOZE_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_SNOOZE_HOURS

    snooze = ActionSnooze.query.filter_by(
        company_id=company_id, source=source, source_id=source_id).first()
    if snooze:
        snooze.snoozed_until = datetime.utcnow() + timedelta(hours=hours)
    else:
        snooze = ActionSnooze(
            company_id=company_id, source=source, source_id=source_id,
            snoozed_until=datetime.utcnow() + timedelta(hours=hours))
        db.session.add(snooze)
    db.session.commit()
    return jsonify({"success": True})
