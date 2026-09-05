import json
from datetime import date
from flask import Blueprint, render_template, request, session, redirect, url_for
from models import db, Order, Invoice, Client, DeliveryChallan, ClientCompanyLink, Payment, CreditNote, Expense
from sqlalchemy import func, extract
from collections import defaultdict

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def format_currency(value):
    if value is None:
        return "0.00"
    if value >= 1000000:
        return f"{value / 1000000:.2f}M"
    return f"{value:,.2f}"


def get_company_clients(company_id):
    return (
        Client.query
        .join(ClientCompanyLink, Client.id == ClientCompanyLink.client_id)
        .filter(ClientCompanyLink.company_id == company_id)
        .order_by(Client.name)
        .all()
    )


@reports_bp.route("/")
def list_reports():
    company_id = session.get("active_company_id")
    if not company_id:
        return redirect(url_for("companies.list_companies"))

    client_id = request.args.get("client_id", type=int)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    page = request.args.get("page", 1, type=int)
    per_page = 20

    query = db.session.query(Invoice).join(Order).filter(
        Order.company_id == company_id,
        Invoice.is_current == True,
        Invoice.status != "cancelled",
    )
    if client_id:
        query = query.filter(Order.client_id == client_id)
    if date_from and date_to:
        query = query.filter(Invoice.invoice_date >= date_from, Invoice.invoice_date <= date_to)

    # Paginated invoices for table display
    from sqlalchemy.orm import selectinload
    total_count = query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    page_invoices = query.options(
        selectinload(Invoice.order).selectinload(Order.client),
        selectinload(Invoice.payments),
        selectinload(Invoice.credit_notes),
    ).order_by(Invoice.invoice_date.desc()).offset((page - 1) * per_page).limit(per_page).all()

    # SQL aggregation for revenue (net of payments and credit notes)
    pay_sq = db.session.query(
        Payment.invoice_id, func.sum(Payment.amount).label("paid")
    ).group_by(Payment.invoice_id).subquery()
    credit_sq = db.session.query(
        CreditNote.invoice_id, func.sum(CreditNote.amount).label("credited")
    ).group_by(CreditNote.invoice_id).subquery()

    base_filter = [
        Order.company_id == company_id,
        Invoice.is_current == True,
        Invoice.status != "cancelled",
    ]
    if client_id:
        base_filter.append(Order.client_id == client_id)
    if date_from and date_to:
        base_filter.append(Invoice.invoice_date >= date_from)
        base_filter.append(Invoice.invoice_date <= date_to)

    rev_result = db.session.query(
        func.coalesce(func.sum(
            Invoice.total_amount
            - func.coalesce(pay_sq.c.paid, 0)
            - func.coalesce(credit_sq.c.credited, 0)
        ), 0)
    ).outerjoin(pay_sq, pay_sq.c.invoice_id == Invoice.id
    ).outerjoin(credit_sq, credit_sq.c.invoice_id == Invoice.id
    ).join(Order, Order.id == Invoice.order_id
    ).filter(*base_filter).scalar()
    revenue = float(rev_result)

    # SQL aggregation for expenses
    expense_filter = [
        Expense.company_id == company_id,
        Expense.expense_date >= date_from if date_from else True,
        Expense.expense_date <= date_to if date_to else True,
    ]
    if client_id:
        # Expenses linked to orders for this client
        expense_filter.append(Expense.order_id.in_(
            db.session.query(Order.id).filter(Order.client_id == client_id, Order.company_id == company_id)
        ))
    total_expenses = float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(*expense_filter).scalar()
    )

    profit = revenue - total_expenses
    margin = round((profit / revenue * 100), 1) if revenue > 0 else 0

    avg_fulfillment = db.session.query(func.avg(DeliveryChallan.dispatch_date - Order.inquiry_date)) \
        .select_from(Order) \
        .join(DeliveryChallan, Order.id == DeliveryChallan.order_id) \
        .filter(Order.company_id == company_id) \
        .scalar()
    avg_fulfillment_val = round(float(avg_fulfillment)) if avg_fulfillment else 0

    # Top 3 clients by revenue (SQL)
    top_client_rows = db.session.query(
        Client.name,
        func.sum(
            Invoice.total_amount
            - func.coalesce(pay_sq.c.paid, 0)
            - func.coalesce(credit_sq.c.credited, 0)
        ).label("revenue")
    ).outerjoin(pay_sq, pay_sq.c.invoice_id == Invoice.id
    ).outerjoin(credit_sq, credit_sq.c.invoice_id == Invoice.id
    ).join(Order, Order.id == Invoice.order_id
    ).join(Client, Client.id == Order.client_id
    ).filter(
        Order.company_id == company_id,
        Invoice.is_current == True,
        Invoice.status != "cancelled",
    ).group_by(Client.name).order_by(func.sum(
        Invoice.total_amount
        - func.coalesce(pay_sq.c.paid, 0)
        - func.coalesce(credit_sq.c.credited, 0)
    ).desc()).limit(3).all()

    class ClientSummary:
        def __init__(self, name, total):
            self.name = name
            self.total = total
            self.formatted_total = format_currency(total)

    top_clients = [ClientSummary(name, float(rev or 0)) for name, rev in top_client_rows]

    # Monthly revenue trend (last 6 months) - SQL
    today = date.today()
    months = []
    for i in range(5, -1, -1):
        y, m = today.year, today.month - i
        while m < 1:
            m += 12
            y -= 1
        months.append((y, m))

    monthly_rev_rows = db.session.query(
        extract("year", Invoice.invoice_date).label("y"),
        extract("month", Invoice.invoice_date).label("m"),
        func.sum(
            Invoice.total_amount
            - func.coalesce(pay_sq.c.paid, 0)
            - func.coalesce(credit_sq.c.credited, 0)
        ).label("revenue")
    ).outerjoin(pay_sq, pay_sq.c.invoice_id == Invoice.id
    ).outerjoin(credit_sq, credit_sq.c.invoice_id == Invoice.id
    ).join(Order, Order.id == Invoice.order_id
    ).filter(
        Order.company_id == company_id,
        Invoice.is_current == True,
        Invoice.status != "cancelled",
    ).group_by(
        extract("year", Invoice.invoice_date),
        extract("month", Invoice.invoice_date)
    ).all()

    rev_map = {(int(r.y), int(r.m)): float(r.revenue or 0) for r in monthly_rev_rows}
    monthly_revenue = [rev_map.get((y, m), 0) for y, m in months]
    month_labels = [f"{y}-{m:02d}" for y, m in months]

    # Allocation: profit vs expenses
    profit_share = float(profit) if revenue > 0 else 0
    expense_share = float(total_expenses) if revenue > 0 else 0

    charts_data = {
        "trend": monthly_revenue,
        "trend_labels": month_labels,
        "allocation": [profit_share, expense_share],
    }

    return render_template(
        "reports/list.html",
        invoices=page_invoices,
        format_currency=format_currency,
        analytics={
            "revenue": format_currency(revenue),
            "total_expenses": format_currency(total_expenses),
            "margin": margin,
            "fulfillment": avg_fulfillment_val,
        },
        top_clients=top_clients,
        charts_data=json.dumps(charts_data),
        clients=get_company_clients(company_id),
        filters={"client_id": client_id, "date_from": date_from, "date_to": date_to},
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total_count,
            "total_pages": total_pages,
        },
    )


@reports_bp.route("/import-legacy", methods=["GET"])
def import_legacy():
    company_id = session.get("active_company_id")
    if not company_id:
        return redirect(url_for("companies.list_companies"))

    clients = get_company_clients(company_id)

    return render_template("reports/import.html", clients=clients, message=None)