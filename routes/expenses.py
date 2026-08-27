from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, Expense, Order, Client, ExpenseCategory
from audit import log_action
from permissions import permission_required
from utils import parse_float
from socket_events import emit_company, emit_dashboard_update

expenses_bp = Blueprint("expenses", __name__, url_prefix="/expenses")


@expenses_bp.route("/")
def list_expenses():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    expenses = Expense.query.filter_by(company_id=company_id).order_by(Expense.expense_date.desc()).all()
    total = sum(e.amount for e in expenses)
    orders = Order.query.filter_by(company_id=company_id).order_by(Order.id.desc()).all()
    categories = [c.name for c in ExpenseCategory.query.filter_by(is_active=True).all()] or ["Other"]

    return render_template("expenses/list.html", expenses=expenses, total=total, orders=orders, categories=categories)


@expenses_bp.route("/add", methods=["POST"])
def add_expense():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    order_id = request.form.get("order_id") or None
    category = request.form.get("category", "Other")
    amount = parse_float(request.form.get("amount"))
    notes = request.form.get("notes", "").strip()
    expense_date_str = request.form.get("expense_date", "")
    expense_date_val = datetime.strptime(expense_date_str, "%Y-%m-%d").date() if expense_date_str else date.today()

    if amount <= 0:
        flash("Expense amount must be greater than 0.")
        return redirect(request.referrer or url_for("expenses.list_expenses"))

    expense = Expense(
        company_id=company_id,
        order_id=int(order_id) if order_id else None,
        category=category,
        amount=amount,
        expense_date=expense_date_val,
        notes=notes,
    )
    db.session.add(expense)
    db.session.commit()

    log_action("add_expense", "Expense", expense.id, f"Logged {category} expense of {amount:.2f}" + (f" for order #{order_id}" if order_id else ""))

    flash("Expense logged.")
    emit_company("list_refresh", {"section": "expenses"}, company_id)
    emit_dashboard_update(company_id)
    return redirect(request.referrer or url_for("expenses.list_expenses"))


@expenses_bp.route("/delete/<int:expense_id>", methods=["POST"])
@permission_required("manage_expenses")
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    order_id = expense.order_id

    db.session.delete(expense)
    db.session.commit()

    log_action("delete_expense", "Expense", expense_id, "Deleted expense")

    flash("Expense deleted.")
    emit_company("list_refresh", {"section": "expenses"}, expense.company_id)
    emit_dashboard_update(expense.company_id)
    if order_id:
        return redirect(url_for("orders.view_order", order_id=order_id))
    return redirect(url_for("expenses.list_expenses"))