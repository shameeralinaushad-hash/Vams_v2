import re
import os
import io
import json
from datetime import date, datetime, timedelta
from calendar import monthrange
import csv
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, extract
from models import db, Company, User, Order, Invoice, Expense, ExpenseCategory, RecurringExpenseTemplate, Notification, Payable, Client, Budget
from audit import log_action
from utils import parse_float, validate_upload, delete_file_if_exists
from werkzeug.utils import secure_filename
from PIL import Image
import pytesseract
import pdfplumber

ALLOWED_RECEIPT_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}


def save_receipt(file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_RECEIPT_EXTENSIONS:
        return None
    receipt_dir = os.path.join(current_app.root_path, "static", "receipts")
    os.makedirs(receipt_dir, exist_ok=True)
    filename = f"receipt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
    file.save(os.path.join(receipt_dir, filename))
    return filename

accounts_bp = Blueprint("accounts", __name__, url_prefix="/accounts")


def get_date_range(period):
    today = date.today()
    if period == "this_month":
        return date(today.year, today.month, 1), today
    elif period == "last_month":
        first = today.replace(day=1) - timedelta(days=1)
        return date(first.year, first.month, 1), first
    elif period == "quarter":
        quarter_start = today.replace(day=1)
        while quarter_start.month % 3 != 1:
            quarter_start = quarter_start.replace(day=1) - timedelta(days=1)
            quarter_start = quarter_start.replace(day=1)
        return quarter_start, today
    return date(today.year, 1, 1), today


def _categories_for_scope(scope):
    pairs = {"personal": ("personal", "general"), "general": ("general", "company"), "company": ("company", "general")}
    a, b = pairs.get(scope, (scope, scope))
    return ExpenseCategory.query.filter(
        db.or_(ExpenseCategory.scope == a, ExpenseCategory.scope == b)
    ).all()


def _expense_cat_totals(scope, start_date, end_date, company_id=None, user_id=None):
    filter_scope_pairs = {"personal": ("personal", "general"), "general": ("general", "company"), "company": ("company", "general")}
    a, b = filter_scope_pairs.get(scope, (scope, scope))

    join_cond = [Expense.category_id == ExpenseCategory.id]
    if scope == "personal":
        join_cond += [Expense.scope == "personal", Expense.created_by == user_id, Expense.expense_date.between(start_date, end_date)]
    elif scope == "general":
        join_cond += [Expense.scope == "general", Expense.expense_date.between(start_date, end_date)]
    elif scope == "company":
        join_cond += [Expense.company_id == company_id, Expense.expense_date.between(start_date, end_date)]

    return db.session.query(
        ExpenseCategory.id, ExpenseCategory.name, func.coalesce(func.sum(Expense.amount), 0).label("total")
    ).outerjoin(Expense, db.and_(*join_cond)
    ).filter(db.or_(ExpenseCategory.scope == a, ExpenseCategory.scope == b)
    ).group_by(ExpenseCategory.id).all()


# --- Budgets ---

BUDGET_SCOPES = {"personal": "Personal", "general": "General", "company": "Company"}


def _month_bounds(month, year):
    end_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, end_day)


def _effective_budget(category_id, scope, month, year, company_id):
    explicit = Budget.query.filter_by(
        scope=scope, category_id=category_id, company_id=company_id, month=month, year=year
    ).first()
    if explicit:
        return explicit, True
    prior = Budget.query.filter(
        Budget.scope == scope,
        Budget.category_id == category_id,
        Budget.company_id == company_id,
        Budget.recurring == True,
        db.or_(Budget.year < year, db.and_(Budget.year == year, Budget.month < month)),
    ).order_by(Budget.year.desc(), Budget.month.desc()).first()
    return prior, False


def _budget_rows(month, year, company_id, scope):
    start, end = _month_bounds(month, year)
    actuals = {cid: total for cid, _name, total in _expense_cat_totals(scope, start, end, company_id, current_user.id)}
    rows = []
    for cat in _categories_for_scope(scope):
        budget, explicit = _effective_budget(cat.id, scope, month, year, company_id)
        spent = actuals.get(cat.id, 0) or 0
        amount = budget.amount if budget else 0
        if not budget and spent == 0:
            continue
        pct = (spent / amount * 100) if amount > 0 else (100 if spent > 0 else 0)
        if amount > 0:
            status = "over" if spent > amount else "ok"
        else:
            status = "unbudgeted" if spent > 0 else "ok"
        rows.append({
            "category_id": cat.id,
            "category": cat.name,
            "category_scope": cat.scope,
            "budget": budget,
            "amount": amount,
            "spent": spent,
            "remaining": amount - spent,
            "pct": round(pct, 1),
            "status": status,
            "explicit": explicit,
            "recurring": bool(budget and budget.recurring),
        })
    return rows


def _budget_summary(rows):
    total_budget = sum(r["amount"] for r in rows)
    total_spent = sum(r["spent"] for r in rows)
    over = [r for r in rows if r["status"] == "over"]
    unbudgeted = [r for r in rows if r["status"] == "unbudgeted"]
    pct = (total_spent / total_budget * 100) if total_budget > 0 else (100 if total_spent > 0 else 0)
    return {
        "total_budget": total_budget,
        "total_spent": total_spent,
        "remaining": total_budget - total_spent,
        "pct": round(pct, 1),
        "over_count": len(over),
        "over": over,
        "unbudgeted": unbudgeted,
    }


def _save_budgets(scope, month, year, company_id):
    for cat in _categories_for_scope(scope):
        key = f"budget_{cat.id}"
        amount = parse_float(request.form.get(key, ""), 0)
        recurring = request.form.get(f"recur_{cat.id}") == "on"
        existing = Budget.query.filter_by(
            scope=scope, category_id=cat.id, company_id=company_id, month=month, year=year
        ).first()
        if amount <= 0:
            if existing:
                db.session.delete(existing)
            continue
        if existing:
            existing.amount = amount
            existing.recurring = recurring
        else:
            db.session.add(Budget(
                scope=scope, company_id=company_id, category_id=cat.id,
                month=month, year=year, period_type="monthly", amount=amount,
                recurring=recurring, created_by=current_user.id,
            ))
    db.session.commit()
    log_action("save_budgets", "Budget", 0, f"Saved {scope} budgets for {year}-{month:02d}")


def _copy_budgets_from_prev(scope, month, year, company_id):
    prev_m, prev_y = (month - 1, year) if month > 1 else (12, year - 1)
    prev_rows = Budget.query.filter_by(scope=scope, company_id=company_id, month=prev_m, year=prev_y).all()
    for p in prev_rows:
        existing = Budget.query.filter_by(
            scope=scope, category_id=p.category_id, company_id=company_id, month=month, year=year
        ).first()
        if existing:
            existing.amount = p.amount
            existing.recurring = p.recurring
        else:
            db.session.add(Budget(
                scope=scope, company_id=company_id, category_id=p.category_id,
                month=month, year=year, period_type="monthly", amount=p.amount,
                recurring=p.recurring, created_by=current_user.id,
            ))
    db.session.commit()


def seed_categories():
    if ExpenseCategory.query.first():
        return
    defaults = [
        ("Hospitality", "general"), ("Utilities", "general"), ("Labour", "general"),
        ("Office", "general"), ("Travel", "general"),
        ("Food", "personal"), ("Shopping", "personal"), ("Health", "personal"),
        ("Entertainment", "personal"), ("Transport", "personal"), ("Bills", "personal"),
        ("Raw Materials", "company"), ("Equipment", "company"), ("Marketing", "company"),
        ("Maintenance", "company"),
    ]
    for name, scope in defaults:
        db.session.add(ExpenseCategory(name=name, scope=scope))
    db.session.commit()


# --- Combined Dashboard ---

def _check_overdue_notifications(company_id):
    admins = User.query.filter(User.role == "admin", User.is_active_user == True).all()
    if not admins or not company_id:
        return
    now = date.today()

    overdue = Invoice.query.join(Order).filter(
        Order.company_id == company_id,
        Invoice.status != "cancelled",
        Invoice.invoice_date < now,
    ).all()
    overdue_count = sum(1 for inv in overdue if not inv.is_fully_paid())

    overdue_payable_count = Payable.query.filter(
        Payable.company_id == company_id,
        Payable.is_paid == False,
        Payable.due_date < now,
    ).count()

    for admin in admins:
        if overdue_count > 0:
            existing = Notification.query.filter_by(
                user_id=admin.id, is_read=False,
                link=url_for("payments.list_payments"),
            ).filter(Notification.message.like("%overdue%receivable%")).first()
            if not existing:
                Notification.send(
                    admin.id,
                    f"{overdue_count} overdue invoice(s) — action needed on receivables.",
                    link=url_for("payments.list_payments"),
                )
        if overdue_payable_count > 0:
            existing = Notification.query.filter_by(
                user_id=admin.id, is_read=False,
                link=url_for("payments.list_payments", tab="payables"),
            ).filter(Notification.message.like("%overdue%payable%")).first()
            if not existing:
                Notification.send(
                    admin.id,
                    f"{overdue_payable_count} overdue payable(s) — payments due to vendors.",
                    link=url_for("payments.list_payments", tab="payables"),
                )


@accounts_bp.route("/")
@login_required
def dashboard():
    seed_categories()
    period = request.args.get("period", "this_month")
    start_date, end_date = get_date_range(period)
    company_id = session.get("active_company_id")

    total_income = 0
    total_expenses = 0
    net_position = 0

    if company_id:
        invoices = Invoice.query.join(Order).filter(
            Order.company_id == company_id,
            Invoice.invoice_date.between(start_date, end_date) if period != "all" else True,
        ).all()
        total_income = sum(inv.net_revenue() for inv in invoices if inv.is_current and not inv.is_cancelled())

    expense_query = Expense.query
    if company_id:
        expense_query = expense_query.filter(
            db.or_(Expense.company_id == company_id, Expense.scope.in_(["personal", "general"]))
        )
    period_expenses = expense_query.filter(Expense.expense_date.between(start_date, end_date)).all()
    total_expenses = sum(e.amount for e in period_expenses)
    net_position = total_income - total_expenses

    monthly_labels = []
    monthly_income = []
    monthly_expenses = []
    today = date.today()
    for i in range(5, -1, -1):
        ym = today.year * 12 + today.month - 1 - i
        y = ym // 12
        m = ym % 12 + 1
        monthly_labels.append(f"{y}-{m:02d}")
        inc = 0
        exp = 0
        if company_id:
            invs = Invoice.query.join(Order).filter(
                Order.company_id == company_id,
                Invoice.is_current == True,
                Invoice.status != "cancelled",
                extract("year", Invoice.invoice_date) == y,
                extract("month", Invoice.invoice_date) == m,
            ).all()
            inc = round(sum(inv.net_revenue() for inv in invs), 2)
        exps = Expense.query.filter(
            Expense.expense_date.between(date(y, m, 1), date(y, m, monthrange(y, m)[1]))
        )
        if company_id:
            exps = exps.filter(db.or_(Expense.company_id == company_id, Expense.scope.in_(["personal", "general"])))
        exp = round(sum(e.amount for e in exps.all()), 2)
        monthly_income.append(inc)
        monthly_expenses.append(exp)

    top_categories = db.session.query(
        ExpenseCategory.name, func.coalesce(func.sum(Expense.amount), 0).label("total")
    ).join(Expense, Expense.category_id == ExpenseCategory.id, isouter=True
    ).filter(Expense.expense_date.between(start_date, end_date)).group_by(ExpenseCategory.id).order_by(
        func.coalesce(func.sum(Expense.amount), 0).desc()
    ).limit(5).all()

    recurring_url = url_for("accounts.list_recurring_templates")
    generate_recurring_url = url_for("accounts.generate_recurring")

    total_inflow = sum(
        inv.net_revenue() for inv in
        Invoice.query.join(Order).filter(
            Invoice.is_current == True,
            Invoice.status != "cancelled",
            Invoice.invoice_date.between(start_date, end_date) if period != "all" else True,
        ).all()
    )
    total_outflow = sum(
        e.amount for e in
        Expense.query.filter(
            Expense.scope != "personal",
            Expense.expense_date.between(start_date, end_date),
        ).all()
    )

    # Recurring expense templates due
    now = date.today()
    recurring_due = RecurringExpenseTemplate.query.filter(
        RecurringExpenseTemplate.company_id == company_id,
        RecurringExpenseTemplate.is_active == True,
        RecurringExpenseTemplate.day_of_month <= now.day,
        db.or_(
            RecurringExpenseTemplate.last_generated_year != now.year,
            RecurringExpenseTemplate.last_generated_month != now.month,
            RecurringExpenseTemplate.last_generated_year == None,
        )
    ).count()

    # Receivables & Payables
    if company_id:
        invoices = Invoice.query.join(Order).filter(Order.company_id == company_id).all()
        unpaid = [inv for inv in invoices if not inv.is_fully_paid() and not inv.is_cancelled()]
        total_receivable = sum(inv.balance_due() for inv in unpaid)
        aging_receivable = {"0_30": 0, "31_60": 0, "60_plus": 0}
        for inv in unpaid:
            days = inv.days_overdue()
            if days <= 30:
                aging_receivable["0_30"] += inv.balance_due()
            elif days <= 60:
                aging_receivable["31_60"] += inv.balance_due()
            else:
                aging_receivable["60_plus"] += inv.balance_due()
    else:
        total_receivable = 0
        aging_receivable = {"0_30": 0, "31_60": 0, "60_plus": 0}

    total_payable = Payable.query.filter(
        Payable.company_id == company_id,
        Payable.is_paid == False,
    ).with_entities(func.coalesce(func.sum(Payable.amount), 0)).scalar() if company_id else 0
    overdue_payable = Payable.query.filter(
        Payable.company_id == company_id,
        Payable.is_paid == False,
        Payable.due_date < now,
).with_entities(func.coalesce(func.sum(Payable.amount), 0)).scalar() if company_id else 0

    _check_overdue_notifications(company_id)

    _today = date.today()
    budget_rows = []
    if company_id:
        for s in BUDGET_SCOPES:
            budget_rows += _budget_rows(_today.month, _today.year, company_id, s)
    budget_summary = _budget_summary(budget_rows)
    _check_budget_notifications(company_id)

    return render_template("accounts/dashboard.html",
        period=period, total_income=total_income, total_expenses=total_expenses,
        net_position=net_position,
        monthly_labels=monthly_labels, monthly_income=monthly_income,
        monthly_expenses=monthly_expenses, top_categories=top_categories,
        recurring_due=recurring_due,
        recurring_url=recurring_url,
        generate_recurring_url=generate_recurring_url,
        total_inflow=total_inflow, total_outflow=total_outflow,
        total_receivable=total_receivable, aging_receivable=aging_receivable,
        total_payable=total_payable, overdue_payable=overdue_payable,
        budget_summary=budget_summary, budget_month_label=_today.strftime("%B %Y"),
    )


# --- Personal Expenses ---

@accounts_bp.route("/personal")
@login_required
def personal_expenses():
    period = request.args.get("period", "this_month")
    start_date, end_date = get_date_range(period)
    category_id = request.args.get("category_id", type=int)
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 50

    query = Expense.query.filter(Expense.scope == "personal", Expense.created_by == current_user.id)
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if search:
        query = query.filter(db.or_(Expense.notes.ilike(f"%{search}%"), Expense.payee.ilike(f"%{search}%")))
    pagination = query.order_by(Expense.expense_date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    expenses = pagination.items

    this_month = sum(e.amount for e in Expense.query.filter(
        Expense.scope == "personal",
        Expense.created_by == current_user.id,
        Expense.expense_date.between(date.today().replace(day=1), date.today())
    ).all())
    last_month_start = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    last_month = sum(e.amount for e in Expense.query.filter(
        Expense.scope == "personal",
        Expense.created_by == current_user.id,
        Expense.expense_date.between(last_month_start, date.today().replace(day=1) - timedelta(days=1))
    ).all())
    ytd = sum(e.amount for e in Expense.query.filter(
        Expense.scope == "personal",
        Expense.created_by == current_user.id,
        Expense.expense_date.between(date(date.today().year, 1, 1), date.today())
    ).all())

    categories = _categories_for_scope("personal")
    cat_totals = _expense_cat_totals("personal", start_date, end_date, user_id=current_user.id)

    today = date.today()
    budget_rows = _budget_rows(today.month, today.year, None, "personal")
    budget_summary = _budget_summary(budget_rows)

    return render_template("accounts/personal.html",
        period=period, expenses=expenses, categories=categories,
        this_month=this_month, last_month=last_month, ytd=ytd,
        cat_totals=cat_totals, selected_category=category_id, search=search,
        page=pagination.page, pages=pagination.pages, total=pagination.total,
        budget_rows=budget_rows, budget_summary=budget_summary,
    )


@accounts_bp.route("/personal/add", methods=["POST"])
@login_required
def personal_add_expense():
    category_id = request.form.get("category_id", type=int)
    amount = parse_float(request.form.get("amount"))
    notes = request.form.get("notes", "").strip()
    payee = request.form.get("payee", "").strip()
    expense_date_str = request.form.get("expense_date", "")
    expense_date = datetime.strptime(expense_date_str, "%Y-%m-%d").date() if expense_date_str else date.today()

    if amount <= 0:
        flash("Amount must be greater than 0.")
        return redirect(url_for("accounts.personal_expenses"))

    receipt = save_receipt(request.files.get("receipt"))
    e = Expense(scope="personal", category_id=category_id, amount=amount,
                notes=notes, payee=payee or None, expense_date=expense_date,
                receipt_filename=receipt, created_by=current_user.id)
    db.session.add(e)
    db.session.commit()
    log_action("add_expense", "Expense", e.id, f"Personal expense {amount}")
    _check_budget_notifications(None)
    flash("Personal expense logged.")
    return redirect(url_for("accounts.personal_expenses"))


@accounts_bp.route("/personal/edit/<int:expense_id>", methods=["POST"])
@login_required
def personal_edit_expense(expense_id):
    e = Expense.query.filter_by(id=expense_id, scope="personal", created_by=current_user.id).first_or_404()
    e.category_id = request.form.get("category_id", type=int)
    e.amount = parse_float(request.form.get("amount"))
    e.notes = request.form.get("notes", "").strip() or None
    e.payee = request.form.get("payee", "").strip() or None
    date_str = request.form.get("expense_date", "")
    if date_str:
        e.expense_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    receipt = save_receipt(request.files.get("receipt"))
    if receipt:
        if e.receipt_filename:
            delete_file_if_exists(os.path.join(current_app.root_path, "static", "receipts", e.receipt_filename))
        e.receipt_filename = receipt
    e.updated_by = current_user.id
    db.session.commit()
    log_action("edit_expense", "Expense", e.id, f"Edited personal expense {e.amount}")
    _check_budget_notifications(None)
    flash("Expense updated.")
    return redirect(url_for("accounts.personal_expenses"))


@accounts_bp.route("/personal/delete/<int:expense_id>", methods=["POST"])
@login_required
def personal_delete_expense(expense_id):
    e = Expense.query.filter_by(id=expense_id, scope="personal", created_by=current_user.id).first_or_404()
    if e.receipt_filename:
        delete_file_if_exists(os.path.join(current_app.root_path, "static", "receipts", e.receipt_filename))
    db.session.delete(e)
    db.session.commit()
    flash("Personal expense deleted.")
    return redirect(url_for("accounts.personal_expenses"))


# --- General Expenses ---

@accounts_bp.route("/general")
@login_required
def general_expenses():
    period = request.args.get("period", "this_month")
    start_date, end_date = get_date_range(period)
    category_id = request.args.get("category_id", type=int)
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 50

    categories = _categories_for_scope("general")

    query = Expense.query.filter(Expense.scope == "general")
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if search:
        query = query.filter(db.or_(Expense.notes.ilike(f"%{search}%"), Expense.payee.ilike(f"%{search}%")))
    pagination = query.order_by(Expense.expense_date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    expenses = pagination.items

    overall_spent = sum(e.amount for e in Expense.query.filter(
        Expense.scope == "general",
        Expense.expense_date.between(start_date, end_date)
    ).all())

    today = date.today()
    budget_rows = _budget_rows(today.month, today.year, None, "general")
    budget_summary = _budget_summary(budget_rows)

    return render_template("accounts/general.html",
        period=period, expenses=expenses, categories=categories,
        overall_spent=overall_spent, selected_category=category_id, search=search,
        page=pagination.page, pages=pagination.pages, total=pagination.total,
        recurring_url=url_for("accounts.list_recurring_templates"),
        budget_rows=budget_rows, budget_summary=budget_summary,
    )


@accounts_bp.route("/general/add", methods=["POST"])
@login_required
def general_add_expense():
    category_id = request.form.get("category_id", type=int)
    amount = parse_float(request.form.get("amount"))
    notes = request.form.get("notes", "").strip()
    payee = request.form.get("payee", "").strip()
    payment_method = request.form.get("payment_method", "").strip()
    expense_date_str = request.form.get("expense_date", "")
    expense_date = datetime.strptime(expense_date_str, "%Y-%m-%d").date() if expense_date_str else date.today()

    if amount <= 0:
        flash("Amount must be greater than 0.")
        return redirect(url_for("accounts.general_expenses"))

    receipt = save_receipt(request.files.get("receipt"))
    e = Expense(scope="general", category_id=category_id, amount=amount,
                notes=notes, payee=payee or None, payment_method=payment_method or None,
                expense_date=expense_date, receipt_filename=receipt, created_by=current_user.id)
    db.session.add(e)
    db.session.commit()
    log_action("add_expense", "Expense", e.id, f"General expense {amount}")
    _check_budget_notifications(None)
    flash("General expense logged.")
    return redirect(url_for("accounts.general_expenses"))


@accounts_bp.route("/general/edit/<int:expense_id>", methods=["POST"])
@login_required
def general_edit_expense(expense_id):
    if current_user.role not in ("admin", "hr"):
        flash("You don't have permission to edit general expenses.")
        return redirect(url_for("accounts.general_expenses"))
    e = Expense.query.filter_by(id=expense_id, scope="general").first_or_404()
    e.category_id = request.form.get("category_id", type=int)
    e.amount = parse_float(request.form.get("amount"))
    e.notes = request.form.get("notes", "").strip() or None
    e.payee = request.form.get("payee", "").strip() or None
    e.payment_method = request.form.get("payment_method", "").strip() or None
    date_str = request.form.get("expense_date", "")
    if date_str:
        e.expense_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    receipt = save_receipt(request.files.get("receipt"))
    if receipt:
        if e.receipt_filename:
            delete_file_if_exists(os.path.join(current_app.root_path, "static", "receipts", e.receipt_filename))
        e.receipt_filename = receipt
    e.updated_by = current_user.id
    db.session.commit()
    log_action("edit_expense", "Expense", e.id, f"Edited general expense {e.amount}")
    _check_budget_notifications(None)
    flash("Expense updated.")
    return redirect(url_for("accounts.general_expenses"))


@accounts_bp.route("/general/delete/<int:expense_id>", methods=["POST"])
@login_required
def general_delete_expense(expense_id):
    if current_user.role not in ("admin", "hr"):
        flash("You don't have permission to delete general expenses.")
        return redirect(url_for("accounts.general_expenses"))
    e = Expense.query.filter_by(id=expense_id, scope="general").first_or_404()
    if e.receipt_filename:
        delete_file_if_exists(os.path.join(current_app.root_path, "static", "receipts", e.receipt_filename))
    db.session.delete(e)
    db.session.commit()
    flash("General expense deleted.")
    return redirect(url_for("accounts.general_expenses"))


# --- Company Accounts ---

@accounts_bp.route("/companies")
@login_required
def company_accounts():
    company_id = request.args.get("company_id", type=int) or session.get("active_company_id")
    company = db.session.get(Company, company_id) if company_id else None
    if not company:
        flash("Select a company first.")
        return redirect(url_for("companies.list_companies"))

    period = request.args.get("period", "this_month")
    start_date, end_date = get_date_range(period)
    category_id = request.args.get("category_id", type=int)
    search = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 50

    all_companies = Company.query.all()

    invoices = Invoice.query.join(Order).filter(Order.company_id == company_id).all()
    total_revenue = sum(inv.net_revenue() for inv in invoices if inv.is_current and not inv.is_cancelled())
    period_revenue = sum(inv.net_revenue() for inv in invoices if
                         inv.is_current and not inv.is_cancelled() and inv.invoice_date
                         and start_date <= inv.invoice_date <= end_date)

    collected_revenue = sum(inv.total_paid() for inv in invoices if
                            inv.is_current and not inv.is_cancelled() and inv.invoice_date
                            and start_date <= inv.invoice_date <= end_date)
    outstanding = period_revenue - collected_revenue

    query = Expense.query.filter(Expense.company_id == company_id)
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if search:
        query = query.filter(db.or_(Expense.notes.ilike(f"%{search}%"), Expense.payee.ilike(f"%{search}%")))
    pagination = query.order_by(Expense.expense_date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    expenses = pagination.items

    total_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.company_id == company_id
    ).scalar()
    period_expenses = sum(e.amount for e in Expense.query.filter(
        Expense.company_id == company_id,
        Expense.expense_date.between(start_date, end_date)
    ).all())
    net_profit = collected_revenue - period_expenses

    categories = _categories_for_scope("company")
    cat_totals = _expense_cat_totals("company", start_date, end_date, company_id=company_id)

    today = date.today()
    budget_rows = _budget_rows(today.month, today.year, company_id, "company")
    budget_summary = _budget_summary(budget_rows)

    monthly_labels = []
    monthly_revenue = []
    monthly_collected = []
    monthly_exp = []
    for i in range(5, -1, -1):
        ym = today.year * 12 + today.month - 1 - i
        y = ym // 12
        m = ym % 12 + 1
        monthly_labels.append(f"{y}-{m:02d}")
        rev = sum(inv.net_revenue() for inv in invoices if
                  inv.is_current and not inv.is_cancelled() and inv.invoice_date
                  and inv.invoice_date.year == y and inv.invoice_date.month == m)
        monthly_revenue.append(round(rev, 2))
        coll = sum(inv.total_paid() for inv in invoices if
                   inv.is_current and not inv.is_cancelled() and inv.invoice_date
                   and inv.invoice_date.year == y and inv.invoice_date.month == m)
        monthly_collected.append(round(coll, 2))
        exps = sum(e.amount for e in Expense.query.filter(
            Expense.company_id == company_id,
            Expense.expense_date.between(date(y, m, 1), date(y, m, monthrange(y, m)[1]))
        ).all())
        monthly_exp.append(round(exps, 2))

    return render_template("accounts/company.html",
        company=company, all_companies=all_companies, period=period,
        total_revenue=total_revenue, period_revenue=period_revenue,
        collected_revenue=collected_revenue, outstanding=outstanding,
        total_expenses=total_expenses, period_expenses=period_expenses,
        net_profit=net_profit,
        expenses=expenses, categories=categories,
        cat_totals=cat_totals, selected_category=category_id, search=search,
        monthly_labels=monthly_labels, monthly_revenue=monthly_revenue,
        monthly_collected=monthly_collected, monthly_exp=monthly_exp,
        page=pagination.page, pages=pagination.pages, total=pagination.total,
        budget_rows=budget_rows, budget_summary=budget_summary,
    )


@accounts_bp.route("/companies/add", methods=["POST"])
@login_required
def company_add_expense():
    company_id = request.form.get("company_id", type=int)
    category_id = request.form.get("category_id", type=int)
    amount = parse_float(request.form.get("amount"))
    notes = request.form.get("notes", "").strip()
    payee = request.form.get("payee", "").strip()
    payment_method = request.form.get("payment_method", "").strip()
    expense_date_str = request.form.get("expense_date", "")
    expense_date = datetime.strptime(expense_date_str, "%Y-%m-%d").date() if expense_date_str else date.today()

    if not company_id:
        flash("Select a company.")
        return redirect(url_for("accounts.company_accounts"))
    if amount <= 0:
        flash("Amount must be greater than 0.")
        return redirect(url_for("accounts.company_accounts", company_id=company_id))

    receipt = save_receipt(request.files.get("receipt"))
    e = Expense(scope="company", company_id=company_id, category_id=category_id,
                amount=amount, notes=notes, payee=payee or None,
                payment_method=payment_method or None,
                expense_date=expense_date, receipt_filename=receipt, created_by=current_user.id)
    db.session.add(e)
    db.session.commit()
    log_action("add_expense", "Expense", e.id, f"Company expense {amount} for {company_id}")
    _check_budget_notifications(company_id)
    flash("Company expense logged.")
    return redirect(url_for("accounts.company_accounts", company_id=company_id))


@accounts_bp.route("/companies/edit/<int:expense_id>", methods=["POST"])
@login_required
def company_edit_expense(expense_id):
    e = Expense.query.get_or_404(expense_id)
    if e.scope != "company":
        flash("Invalid expense scope.")
        return redirect(url_for("accounts.company_accounts"))
    cid = e.company_id
    e.category_id = request.form.get("category_id", type=int)
    e.amount = parse_float(request.form.get("amount"))
    e.notes = request.form.get("notes", "").strip() or None
    e.payee = request.form.get("payee", "").strip() or None
    e.payment_method = request.form.get("payment_method", "").strip() or None
    date_str = request.form.get("expense_date", "")
    if date_str:
        e.expense_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    receipt = save_receipt(request.files.get("receipt"))
    if receipt:
        if e.receipt_filename:
            delete_file_if_exists(os.path.join(current_app.root_path, "static", "receipts", e.receipt_filename))
        e.receipt_filename = receipt
    e.updated_by = current_user.id
    db.session.commit()
    log_action("edit_expense", "Expense", e.id, f"Edited company expense {e.amount}")
    _check_budget_notifications(cid)
    flash("Expense updated.")
    return redirect(url_for("accounts.company_accounts", company_id=cid))


@accounts_bp.route("/companies/delete/<int:expense_id>", methods=["POST"])
@login_required
def company_delete_expense(expense_id):
    e = Expense.query.get_or_404(expense_id)
    if e.scope != "company":
        flash("Invalid expense scope.")
        return redirect(url_for("accounts.company_accounts"))
    cid = e.company_id
    if e.receipt_filename:
        delete_file_if_exists(os.path.join(current_app.root_path, "static", "receipts", e.receipt_filename))
    db.session.delete(e)
    db.session.commit()
    flash("Company expense deleted.")
    return redirect(url_for("accounts.company_accounts", company_id=cid))


# --- Recurring Expenses (§3.5) ---

@accounts_bp.route("/recurring")
@login_required
def list_recurring_templates():
    company_id = session.get("active_company_id")
    templates = RecurringExpenseTemplate.query.filter_by(company_id=company_id).order_by(RecurringExpenseTemplate.created_at.desc()).all()
    categories = ExpenseCategory.query.order_by(ExpenseCategory.scope, ExpenseCategory.name).all()
    return render_template("accounts/recurring_expenses.html", templates=templates, categories=categories,
        add_recurring_url=url_for("accounts.add_recurring_template"),
        generate_recurring_url=url_for("accounts.generate_recurring"),
        dashboard_url=url_for("accounts.dashboard"),
        delete_recurring_base=url_for("accounts.delete_recurring_template", template_id="__ID__").replace("__ID__", ""),
    )


@accounts_bp.route("/recurring/add", methods=["POST"])
@login_required
def add_recurring_template():
    if current_user.role not in ("admin", "hr"):
        flash("Only admins and HR can manage recurring expenses.")
        return redirect(url_for("accounts.list_recurring_templates"))
    company_id = session.get("active_company_id")
    t = RecurringExpenseTemplate(
        scope=request.form["scope"],
        company_id=company_id,
        category_id=request.form.get("category_id", type=int),
        amount=parse_float(request.form["amount"]),
        notes=request.form.get("notes", "").strip() or None,
        payee=request.form.get("payee", "").strip() or None,
        payment_method=request.form.get("payment_method", "").strip() or None,
        day_of_month=int(request.form.get("day_of_month", 1)),
        created_by=current_user.id,
    )
    db.session.add(t)
    db.session.commit()
    log_action("add_recurring", "RecurringExpenseTemplate", t.id, f"Added recurring {t.amount}")
    flash("Recurring expense template added.")
    return redirect(url_for("accounts.list_recurring_templates"))


@accounts_bp.route("/recurring/delete/<int:template_id>", methods=["POST"])
@login_required
def delete_recurring_template(template_id):
    if current_user.role not in ("admin", "hr"):
        flash("Only admins and HR can manage recurring expenses.")
        return redirect(url_for("accounts.list_recurring_templates"))
    t = db.session.get(RecurringExpenseTemplate, template_id)
    if t:
        db.session.delete(t)
        db.session.commit()
    return redirect(url_for("accounts.list_recurring_templates"))


@accounts_bp.route("/recurring/generate", methods=["POST"])
@login_required
def generate_recurring():
    company_id = session.get("active_company_id")
    now = date.today()
    days_in_month = monthrange(now.year, now.month)[1]
    templates = RecurringExpenseTemplate.query.filter(
        RecurringExpenseTemplate.company_id == company_id,
        RecurringExpenseTemplate.is_active == True,
        RecurringExpenseTemplate.day_of_month <= now.day,
    ).all()
    count = 0
    for t in templates:
        if t.last_generated_year == now.year and t.last_generated_month == now.month:
            continue
        safe_day = min(t.day_of_month, days_in_month)
        if safe_day > now.day:
            continue
        expense_date = date(now.year, now.month, safe_day)
        if t.category_id:
            cat = db.session.get(ExpenseCategory, t.category_id)
            if not cat or not cat.is_active:
                continue
        e = Expense(
            scope=t.scope,
            company_id=t.company_id,
            category_id=t.category_id,
            amount=t.amount,
            notes=t.notes,
            payee=t.payee,
            payment_method=t.payment_method,
            expense_date=expense_date,
            created_by=current_user.id,
        )
        db.session.add(e)
        db.session.flush()
        t.last_generated_month = now.month
        t.last_generated_year = now.year
        count += 1
    db.session.commit()
    if count:
        log_action("generate_recurring", "Expense", 0, f"Generated {count} recurring expenses")
        flash(f"{count} recurring expense(s) generated.")
    else:
        flash("Nothing to generate — all templates already generated this month.")
    return redirect(url_for("accounts.dashboard"))


# --- Sankey Diagram (§2.1) ---

# --- CSV Export ---

@accounts_bp.route("/export-csv/<scope>")
@login_required
def export_csv(scope):
    if scope not in ("personal", "general", "company"):
        flash("Invalid scope.")
        return redirect(url_for("accounts.dashboard"))

    company_id = request.args.get("company_id", type=int)
    query = Expense.query.filter(Expense.scope == scope)
    if scope == "company" and company_id:
        query = query.filter(Expense.company_id == company_id)
    expenses = query.order_by(Expense.expense_date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Category", "Amount", "Payee", "Payment Method", "Notes", "Scope"])
    for e in expenses:
        writer.writerow([
            e.expense_date, e.category_ref.name if e.category_ref else "",
            e.amount, e.payee or "", e.payment_method or "", e.notes or "", e.scope,
        ])

    filename = f"expenses_{scope}_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --- Categories ---

@accounts_bp.route("/categories")
@login_required
def list_categories():
    scopes = {"personal": "Personal", "general": "General", "company": "Company"}
    categories = ExpenseCategory.query.order_by(ExpenseCategory.scope, ExpenseCategory.name).all()
    return render_template("accounts/categories.html", categories=categories, scopes=scopes)


@accounts_bp.route("/categories/add", methods=["POST"])
@login_required
def add_category():
    if current_user.role not in ("admin", "hr"):
        flash("Only admins and HR can manage categories.")
        return redirect(url_for("accounts.list_categories"))
    name = request.form.get("name", "").strip()
    scope = request.form.get("scope", "general")
    if not name:
        flash("Category name is required.")
        return redirect(url_for("accounts.list_categories"))
    existing = ExpenseCategory.query.filter_by(name=name, scope=scope).first()
    if existing:
        flash("Category already exists.")
        return redirect(url_for("accounts.list_categories"))
    db.session.add(ExpenseCategory(name=name, scope=scope, is_active=True))
    db.session.commit()
    log_action("add_category", "ExpenseCategory", 0, f"Added {name} ({scope})")
    flash("Category added.")
    return redirect(url_for("accounts.list_categories"))


@accounts_bp.route("/categories/toggle/<int:category_id>", methods=["POST"])
@login_required
def toggle_category(category_id):
    if current_user.role not in ("admin", "hr"):
        flash("Only admins and HR can manage categories.")
        return redirect(url_for("accounts.list_categories"))
    cat = db.session.get(ExpenseCategory, category_id)
    if cat:
        cat.is_active = not cat.is_active
        db.session.commit()
    return redirect(url_for("accounts.list_categories"))


# --- Budgets ---

@accounts_bp.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():
    seed_categories()
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select a company workspace first to manage budgets.")
        return redirect(url_for("accounts.dashboard"))

    scope = request.form.get("scope") or request.args.get("scope", "general")
    if scope not in BUDGET_SCOPES:
        scope = "general"
    today = date.today()
    month = request.form.get("month", type=int) or request.args.get("month", type=int) or today.month
    year = request.form.get("year", type=int) or request.args.get("year", type=int) or today.year
    try:
        month = int(month)
        year = int(year)
    except (TypeError, ValueError):
        month = today.month
        year = today.year
    if not 1 <= month <= 12:
        month = today.month

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "copy":
            _copy_budgets_from_prev(scope, month, year, company_id)
            flash("Copied budget amounts from the previous month.")
        elif request.form.get("budget_amount"):
            # Inline single-budget add from expense pages
            cat_id = request.form.get("category_id", type=int)
            amount = parse_float(request.form.get("budget_amount", ""), 0)
            recurring = request.form.get("recurring") == "1"
            if cat_id and amount > 0:
                existing = Budget.query.filter_by(
                    scope=scope, category_id=cat_id, company_id=company_id, month=month, year=year
                ).first()
                if existing:
                    existing.amount = amount
                    existing.recurring = recurring
                else:
                    db.session.add(Budget(
                        scope=scope, company_id=company_id, category_id=cat_id,
                        month=month, year=year, period_type="monthly", amount=amount,
                        recurring=recurring, created_by=current_user.id,
                    ))
                db.session.commit()
                log_action("add_budget_inline", "Budget", 0, f"Added {scope} budget for category {cat_id}: {amount}")
                flash("Budget added.")
            else:
                flash("Please select a category and enter an amount.")
        else:
            _save_budgets(scope, month, year, company_id)
            flash("Budgets saved.")
        return redirect(url_for("accounts.budgets", scope=scope, month=month, year=year))

    rows = _budget_rows(month, year, company_id, scope)
    summary = _budget_summary(rows)
    categories = _categories_for_scope(scope)
    today = date.today()
    return render_template(
        "accounts/budgets.html",
        scopes=BUDGET_SCOPES, active_scope=scope, month=month, year=year,
        rows=rows, summary=summary, categories=categories, today=today,
    )


@accounts_bp.route("/budgets/delete/<int:budget_id>", methods=["POST"])
@login_required
def delete_budget(budget_id):
    scope = request.form.get("scope", "general")
    month = request.form.get("month", type=int) or date.today().month
    year = request.form.get("year", type=int) or date.today().year
    b = db.session.get(Budget, budget_id)
    if b:
        b_scope = b.scope
        b_label = b.category.name if b.category else b.category_id
        db.session.delete(b)
        db.session.commit()
        log_action("delete_budget", "Budget", budget_id, f"Deleted {b_scope} budget for {b_label}")
        flash("Budget removed.")
    return redirect(url_for("accounts.budgets", scope=scope, month=month, year=year))


def _check_budget_notifications(company_id):
    today = date.today()
    rows = []
    for s in BUDGET_SCOPES:
        rows += _budget_rows(today.month, today.year, company_id, s)
    over = [r for r in rows if r["status"] == "over"]
    warning = [r for r in rows if r["status"] == "warn"]
    alerts = []
    if over:
        alerts.append(f"{len(over)} category(ies) over budget")
    if warning:
        alerts.append(f"{len(warning)} category(ies) at 75%+ usage")
    if not alerts:
        return
    admins = User.query.filter(User.role == "admin", User.is_active_user == True).all()
    link = url_for("accounts.budgets", month=today.month, year=today.year)
    top = max(over, key=lambda r: r["pct"]) if over else max(warning, key=lambda r: r["pct"])
    msg = "; ".join(alerts) + f" — '{top['category']}' at {top['pct']:.0f}%."
    for admin in admins:
        existing = Notification.query.filter_by(user_id=admin.id, is_read=False, link=link).filter(
            Notification.message.like("%budget%")
        ).first()
        if not existing:
            Notification.send(admin.id, msg, link=link)


# --- Bulk Actions ---

@accounts_bp.route("/bulk/delete", methods=["POST"])
@login_required
def bulk_delete_expenses():
    ids = request.form.getlist("ids[]", type=int)
    scope = request.form.get("scope")
    if not ids or scope not in ("personal", "general", "company"):
        return jsonify({"ok": False, "error": "Invalid request"}), 400

    q = Expense.query.filter(Expense.id.in_(ids), Expense.scope == scope)
    if scope == "personal":
        q = q.filter(Expense.created_by == current_user.id)
    expenses = q.all()
    count = len(expenses)

    for e in expenses:
        if e.receipt_filename:
            delete_file_if_exists(os.path.join(current_app.root_path, "static", "receipts", e.receipt_filename))
        db.session.delete(e)
    db.session.commit()
    log_action("bulk_delete_expenses", "Expense", 0, f"Bulk deleted {count} {scope} expenses")
    return jsonify({"ok": True, "count": count})


@accounts_bp.route("/bulk/recategorize", methods=["POST"])
@login_required
def bulk_recategorize_expenses():
    ids = request.form.getlist("ids[]", type=int)
    scope = request.form.get("scope")
    category_id = request.form.get("category_id", type=int)
    if not ids or scope not in ("personal", "general", "company") or not category_id:
        return jsonify({"ok": False, "error": "Invalid request"}), 400

    q = Expense.query.filter(Expense.id.in_(ids), Expense.scope == scope)
    if scope == "personal":
        q = q.filter(Expense.created_by == current_user.id)
    q.update({"category_id": category_id}, synchronize_session=False)
    db.session.commit()
    log_action("bulk_recategorize", "Expense", 0, f"Bulk recategorized {len(ids)} {scope} expenses")
    return jsonify({"ok": True, "count": len(ids)})


# --- Receipt OCR via Tesseract (§2.4) ---

@accounts_bp.route("/receipt-ocr", methods=["GET", "POST"])
@login_required
def receipt_ocr():
    company_id = session.get("active_company_id")
    categories = ExpenseCategory.query.order_by(ExpenseCategory.name).all()
    companies = Company.query.order_by(Company.name).all()

    if request.method == "POST":
        if "file" not in request.files:
            flash("No file uploaded.")
            return redirect(url_for("accounts.receipt_ocr"))

        file = request.files["file"]
        allowed = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "pdf")
        if not any(file.filename.lower().endswith(ext) for ext in allowed):
            flash("Accepted formats: PNG, JPG, GIF, WebP, BMP, PDF.")
            return redirect(url_for("accounts.receipt_ocr"))

        try:
            image_exts = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
            ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
            fname = secure_filename(file.filename or "receipt.jpg")
            save_path = os.path.join(current_app.root_path, "static", "uploads", f"ocr_{fname}")
            file.save(save_path)

            raw_text = ""
            if ext in image_exts:
                raw_text = _ocr_image_text(save_path)
            elif ext == "pdf":
                raw_text = _ocr_pdf_text(save_path)

            if not raw_text.strip():
                flash("No text could be extracted from the receipt.")
                delete_file_if_exists(save_path)
                return render_template("accounts/receipt_ocr.html", result=None, categories=categories, companies=companies)

            result = _parse_receipt_text(raw_text)
            delete_file_if_exists(save_path)
            ocr_items_json = json.dumps(result.get("items", []))

            if result.get("items"):
                flash(f"OCR extracted {len(result['items'])} items from receipt.")
            else:
                flash("Receipt text extracted but no line items found. Raw text shown below.")
            return render_template("accounts/receipt_ocr.html", result=result, filename=fname, raw_text=raw_text, categories=categories, companies=companies, ocr_items_json=ocr_items_json)

        except Exception as e:
            flash(f"OCR failed: {e}")
            return redirect(url_for("accounts.receipt_ocr"))

    return render_template("accounts/receipt_ocr.html", result=None, categories=categories, companies=companies)


@accounts_bp.route("/receipt-ocr/import", methods=["POST"])
@login_required
def receipt_ocr_import():
    vendor = request.form.get("vendor", "").strip()
    date_str = request.form.get("date_str", "").strip()
    total = parse_float(request.form.get("total"))
    scope = request.form.get("scope", "general")
    category_id = request.form.get("category_id", type=int)
    items_json = request.form.get("items_json", "").strip()

    if total <= 0:
        flash("Invalid expense amount from OCR.")
        return redirect(url_for("accounts.receipt_ocr"))

    expense_date = date.today()
    if date_str:
        try:
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
                expense_date = datetime.strptime(date_str, fmt).date()
                break
            else:
                expense_date = date.today()
        except ValueError:
            expense_date = date.today()

    notes = f"OCR receipt — {vendor}" if vendor else "OCR receipt"
    if items_json:
        try:
            items = json.loads(items_json)
            if items:
                item_lines = [f"{i.get('item','?')} x{i.get('qty',1)} @ {i.get('unit_price',0)}" for i in items[:5]]
                notes += "\n" + "\n".join(item_lines)
        except (json.JSONDecodeError, TypeError):
            pass

    company_id = None
    if scope == "company":
        company_id = session.get("active_company_id")

    e = Expense(
        scope=scope, company_id=company_id, category_id=category_id or None,
        amount=total, notes=notes, payee=vendor or None,
        expense_date=expense_date, created_by=current_user.id,
    )
    db.session.add(e)
    db.session.commit()
    log_action("add_expense", "Expense", e.id, f"OCR import: {total} ({scope})")
    flash(f"Expense of {total:,.2f} imported from OCR receipt ({scope}).")
    return redirect(url_for("accounts.dashboard"))


def _ocr_image_text(path):
    try:
        img = Image.open(path)
        img = img.convert("L")
        if pytesseract.pytesseract.tesseract_cmd == "tesseract":
            win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(win_path):
                pytesseract.pytesseract.tesseract_cmd = win_path
        return pytesseract.image_to_string(img)
    except Exception as e:
        raise RuntimeError(f"Tesseract OCR failed: {e}")


def _ocr_pdf_text(path):
    text_parts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception:
        pass
    if text_parts and any(len(p.strip()) > 50 for p in text_parts):
        return "\n".join(text_parts)
    try:
        import fitz  # PyMuPDF — lazy import to avoid venv conflicts
        doc = fitz.open(path)
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = img.convert("L")
            win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(win_path):
                pytesseract.pytesseract.tesseract_cmd = win_path
            t = pytesseract.image_to_string(img)
            if t.strip():
                text_parts.append(t)
        doc.close()
    except Exception as e:
        raise RuntimeError(f"Scanned PDF OCR failed: {e}")
    return "\n".join(text_parts)


_RECEIPT_TOTAL_RE = re.compile(
    r"(?:total|grand total|amount due|balance due|net|tender|sum)\s*:?\s*(?:rs|pk|usd|inr|)\s*:?\s*([0-9,]+\.\d{2})",
    re.IGNORECASE
)
_RECEIPT_DATE_RE = re.compile(
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
)
_RECEIPT_VENDOR_LINE_RE = re.compile(
    r"^(?!.*(?:total|subtotal|tax|amount|qty|price|rs\.|invoice|bill|receipt|date|phone|email|www|https|address|cash|change|due|balance|thank|store|shop|counter|check|item|description|particular))"
    r".{5,60}$",
    re.IGNORECASE
)
_RECEIPT_ITEM_RE = re.compile(
    r"^(.+?)\s+(\d+(?:\.\d+)?)\s*(?:x\s*)?([0-9,]+\.?\d*)\s*(?:@\s*)?([0-9,]+\.\d{2})?\s*$"
)
_RECEIPT_ITEM_SIMPLE_RE = re.compile(
    r"^(.+?)\s+([0-9,]+\.\d{2})\s*$"
)


def _parse_receipt_text(text):
    lines = text.split("\n")
    clean = [l.strip() for l in lines if l.strip()]

    result = {"vendor": "", "date": "", "total": 0.0, "items": []}

    date_matches = []
    total_matches = []
    item_candidates = []
    possible_vendor = ""

    for line in clean:
        m = _RECEIPT_TOTAL_RE.search(line)
        if m:
            try:
                total_matches.append(float(m.group(1).replace(",", "")))
            except ValueError:
                pass
            continue

        m = _RECEIPT_DATE_RE.search(line)
        if m:
            date_matches.append(m.group(1))
            continue

        m = _RECEIPT_ITEM_RE.match(line)
        if m:
            desc = m.group(1).strip()
            qty = float(m.group(2))
            price = float(m.group(3).replace(",", ""))
            item_candidates.append({"item": desc, "qty": qty, "unit_price": round(price / qty, 2) if qty else 0, "total": price})
            continue

        m = _RECEIPT_ITEM_SIMPLE_RE.match(line)
        if m:
            desc = m.group(1).strip()
            amt = float(m.group(2).replace(",", ""))
            if not any(kw in desc.lower() for kw in ("total", "subtotal", "tax", "change", "cash", "due", "balance")):
                item_candidates.append({"item": desc, "qty": 1, "unit_price": amt, "total": amt})
            continue

        if not possible_vendor and len(line) > 5 and len(line) < 60 and _RECEIPT_VENDOR_LINE_RE.match(line):
            possible_vendor = line

    if date_matches:
        result["date"] = date_matches[0]
    if total_matches:
        result["total"] = total_matches[-1]
    elif item_candidates:
        result["total"] = round(sum(it["total"] for it in item_candidates), 2)
    result["vendor"] = possible_vendor
    result["items"] = item_candidates

    return result

