import json
from datetime import date
from flask import Blueprint, render_template, request, session, redirect, url_for
from models import db, Order, Invoice, Client, DeliveryChallan, ClientCompanyLink
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

    query = Invoice.query.join(Order).filter(
        Order.company_id == company_id,
        Invoice.is_current == True,
        Invoice.status != "cancelled",
    )
    if client_id:
        query = query.filter(Order.client_id == client_id)
    if date_from and date_to:
        query = query.filter(Invoice.invoice_date >= date_from, Invoice.invoice_date <= date_to)

    all_invoices = query.order_by(Invoice.invoice_date.desc()).all()

    revenue = sum(i.net_revenue() for i in all_invoices)
    total_expenses = sum(
        sum(e.amount for e in i.order.expenses) for i in all_invoices if i.order
    )
    profit = revenue - total_expenses
    margin = round((profit / revenue * 100), 1) if revenue > 0 else 0

    avg_fulfillment = db.session.query(func.avg(DeliveryChallan.dispatch_date - Order.inquiry_date)) \
        .select_from(Order) \
        .join(DeliveryChallan, Order.id == DeliveryChallan.order_id) \
        .filter(Order.company_id == company_id) \
        .scalar()
    avg_fulfillment_val = round(float(avg_fulfillment)) if avg_fulfillment else 0

    # Top 3 clients by revenue (from invoices)
    client_totals = defaultdict(float)
    for inv in all_invoices:
        client = inv.order.client if inv.order else None
        if client:
            client_totals[client.name] += inv.net_revenue()
    sorted_clients = sorted(client_totals.items(), key=lambda x: x[1], reverse=True)[:3]

    class ClientSummary:
        def __init__(self, name, total):
            self.name = name
            self.total = total
            self.formatted_total = format_currency(total)

    top_clients = [ClientSummary(name, total) for name, total in sorted_clients]

    # Monthly revenue trend (last 6 months) by invoice date
    today = date.today()
    months = []
    for i in range(5, -1, -1):
        y, m = today.year, today.month - i
        while m < 1:
            m += 12
            y -= 1
        months.append((y, m))

    monthly_revenue = []
    for y, m in months:
        month_total = sum(
            inv.net_revenue() for inv in all_invoices
            if inv.invoice_date and inv.invoice_date.year == y and inv.invoice_date.month == m
        )
        monthly_revenue.append(float(month_total))

    month_labels = [f"{y}-{m:02d}" for y, m in months]

    # Allocation: profit vs expenses
    profit_share = float(profit) if revenue > 0 else 0
    expense_share = float(total_expenses) if revenue > 0 else 0

    # Pagination
    total_count = len(all_invoices)
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_invoices = all_invoices[start:end]

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