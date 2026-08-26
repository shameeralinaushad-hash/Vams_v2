from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import current_user
from models import db, Payment, Invoice, Order, Payable, Notification, User
from audit import log_action
from permissions import permission_required
from utils import parse_float

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")


@payments_bp.route("/")
def list_payments():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    # Track which tab should be open (defaults to 'receivables')
    active_tab = request.args.get("tab", "receivables")

    invoices = (
        Invoice.query.join(Order)
        .filter(Order.company_id == company_id)
        .order_by(Invoice.invoice_date.desc())
        .all()
    )

    unpaid = [inv for inv in invoices if not inv.is_fully_paid() and not inv.is_cancelled()]
    aging = {"0_30": 0, "31_60": 0, "60_plus": 0}
    for inv in unpaid:
        days = inv.days_overdue()
        if days <= 30:
            aging["0_30"] += inv.balance_due()
        elif days <= 60:
            aging["31_60"] += inv.balance_due()
        else:
            aging["60_plus"] += inv.balance_due()

    payables = Payable.query.filter_by(company_id=company_id).order_by(
        Payable.is_paid.asc(), Payable.due_date.asc()
    ).all()
    total_payable_outstanding = sum(p.amount for p in payables if not p.is_paid)

    # ========================================================
    # --- DYNAMIC CHART DATA GENERATION (LAST 6 MONTHS) ------
    # ========================================================
    today = date.today()
    months_data = []

    temp_year = today.year
    temp_month = today.month

    for _ in range(6):
        label = datetime(temp_year, temp_month, 1).strftime("%b")
        months_data.insert(0, {
            "year": temp_year,
            "month": temp_month,
            "label": label,
            "receivable_total": 0.0,
            "payable_total": 0.0
        })
        temp_month -= 1
        if temp_month == 0:
            temp_month = 12
            temp_year -= 1

    for inv in invoices:
        inv_date = inv.invoice_date
        if isinstance(inv_date, str):
            try:
                inv_date = datetime.strptime(inv_date, "%Y-%m-%d").date()
            except ValueError:
                continue

        if inv_date:
            for m in months_data:
                if inv_date.year == m["year"] and inv_date.month == m["month"]:
                    m["receivable_total"] += float(inv.total_amount or 0)
                    break

    for p in payables:
        p_date = p.due_date
        if isinstance(p_date, str):
            try:
                p_date = datetime.strptime(p_date, "%Y-%m-%d").date()
            except ValueError:
                continue

        if p_date:
            for m in months_data:
                if p_date.year == m["year"] and p_date.month == m["month"]:
                    m["payable_total"] += float(p.amount or 0)
                    break

    chart_months = [m["label"] for m in months_data]
    chart_receivables = [round(m["receivable_total"], 2) for m in months_data]
    chart_payables = [round(m["payable_total"], 2) for m in months_data]

    return render_template(
        "payments/list.html",
        invoices=invoices,
        aging=aging,
        payables=payables,
        total_payable_outstanding=total_payable_outstanding,
        chart_months=chart_months,
        chart_receivables=chart_receivables,
        chart_payables=chart_payables,
        active_tab=active_tab  # <--- Passed to Jinja template
    )


@payments_bp.route("/invoice/<int:invoice_id>/add", methods=["POST"])
def add_payment(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=invoice.order_id)

    amount = parse_float(request.form.get("amount"))
    paid_date_str = request.form.get("paid_date", "")
    paid_date = datetime.strptime(paid_date_str, "%Y-%m-%d").date() if paid_date_str else date.today()
    method = request.form.get("method", "")
    notes = request.form.get("notes", "")

    if amount <= 0:
        flash("Payment amount must be greater than 0.")
        return redirect(redirect_target)

    db.session.add(Payment(
        invoice_id=invoice.id, amount=amount, paid_date=paid_date, method=method, notes=notes
    ))
    db.session.commit()

    # Notify admins about payment received
    admins = User.query.filter(User.role.in_(["admin", "hr"])).all()
    for u in admins:
        if u.id != getattr(current_user, 'id', None):
            Notification.send(u.id, f"Payment of {amount:.2f} received for invoice {invoice.invoice_number}",
                              url_for("payments.list_payments"))

    log_action("add_payment", "Invoice", invoice.id,
               f"Logged payment of {amount:.2f} against invoice {invoice.invoice_number}")

    return redirect(redirect_target)


@payments_bp.route("/delete/<int:payment_id>", methods=["POST"])
@permission_required("delete_payments")
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    invoice = payment.invoice
    order_id = invoice.order_id
    invoice_number = invoice.invoice_number
    amount = payment.amount

    redirect_target = request.form.get("next") or request.referrer or url_for("orders.view_order", order_id=order_id)

    db.session.delete(payment)
    db.session.commit()

    log_action("delete_payment", "Payment", payment_id,
               f"Deleted payment of {amount:.2f} against invoice {invoice_number}")

    flash(f"Payment of {amount:.2f} removed from invoice {invoice_number}.")
    return redirect(redirect_target)


# ---------------- Payable (money you owe) ----------------

@payments_bp.route("/payable/add", methods=["POST"])
def add_payable():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    owed_to = request.form.get("owed_to", "").strip()
    amount = parse_float(request.form.get("amount"))
    due_date_str = request.form.get("due_date", "")
    due_date_val = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None
    method = request.form.get("method", "")
    notes = request.form.get("notes", "").strip()

    if not owed_to or amount <= 0:
        flash("Please provide who it's owed to and a valid amount.")
        return redirect(url_for("payments.list_payments", tab="payables"))

    payable = Payable(
        company_id=company_id, owed_to=owed_to, amount=amount,
        due_date=due_date_val, method=method, notes=notes
    )
    db.session.add(payable)
    db.session.commit()

    log_action("add_payable", "Payable", payable.id, f"Logged payable of {amount:.2f} owed to {owed_to}")

    flash("Payable added.")
    return redirect(url_for("payments.list_payments", tab="payables"))


@payments_bp.route("/payable/toggle/<int:payable_id>", methods=["POST"])
def toggle_payable(payable_id):
    payable = Payable.query.get_or_404(payable_id)

    payable.is_paid = not payable.is_paid
    payable.paid_date = date.today() if payable.is_paid else None
    db.session.commit()

    log_action("toggle_payable", "Payable", payable.id,
               f"Marked payable to {payable.owed_to} as {'paid' if payable.is_paid else 'unpaid'}")

    return redirect(url_for("payments.list_payments", tab="payables"))


@payments_bp.route("/payable/delete/<int:payable_id>", methods=["POST"])
def delete_payable(payable_id):
    payable = Payable.query.get_or_404(payable_id)
    owed_to = payable.owed_to

    db.session.delete(payable)
    db.session.commit()

    log_action("delete_payable", "Payable", payable_id, f"Deleted payable owed to {owed_to}")

    flash("Payable deleted.")
    return redirect(url_for("payments.list_payments", tab="payables"))