from datetime import date, datetime
from calendar import monthrange
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Employee, AttendanceRecord, TeamTask, Notification, PayrollRecord, Order, Client, Quotation, Invoice, DeliveryChallan, PurchaseOrder
from audit import log_action
from sqlalchemy import extract
from login_throttle import record_failure, clear_failures, is_locked_out, MAX_ATTEMPTS
from rate_limiter import limiter

mobile_bp = Blueprint("mobile", __name__, url_prefix="/m")


def _emp():
    if current_user.is_authenticated and current_user.employee:
        return current_user.employee
    emp_id = session.get("m_emp_id")
    return db.session.get(Employee, emp_id) if emp_id else None


@mobile_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("mobile.home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if is_locked_out(email):
            flash("Account is locked out due to too many failed attempts. Please try again later.")
            return redirect(url_for("mobile.login"))

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active_user:
            clear_failures(email)
            login_user(user, remember=True)
            if user.employee:
                session["m_emp_id"] = user.employee.id
            flash("Logged in.")
            return redirect(url_for("mobile.home"))

        record_failure(email)
        if is_locked_out(email):
            log_action("account_locked", "User", user.id if user else None,
                       f"Account '{email}' locked out after {MAX_ATTEMPTS} failed login attempts (mobile)")
        flash("Invalid email or password.")
        return redirect(url_for("mobile.login"))
    return render_template("mobile/login.html")


@mobile_bp.route("/logout")
def logout():
    session.pop("m_emp_id", None)
    logout_user()
    return redirect(url_for("mobile.login"))


@mobile_bp.route("/")
def home():
    emp = _emp()
    if not emp:
        if current_user.is_authenticated:
            return render_template("mobile/no_profile.html")
        return redirect(url_for("mobile.login"))
    today = date.today()
    today_rec = AttendanceRecord.query.filter_by(employee_id=emp.id, date=today).first()
    month_start = date(today.year, today.month, 1)
    present_count = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == emp.id,
        AttendanceRecord.date >= month_start,
        AttendanceRecord.date <= today,
        AttendanceRecord.status == "present",
    ).count()
    total_days = today.day
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count() if current_user.is_authenticated else 0
    pending_tasks = TeamTask.query.filter_by(assignee_id=emp.id, status="to_do").count()
    return render_template("mobile/dashboard.html",
        emp=emp, today_rec=today_rec,
        present_count=present_count, total_days=total_days,
        unread=unread, pending_tasks=pending_tasks,
    )


@mobile_bp.route("/attendance")
def attendance():
    emp = _emp()
    if not emp:
        return redirect(url_for("mobile.login"))
    today = date.today()
    year = request.args.get("year", today.year, type=int)
    month = request.args.get("month", today.month, type=int)
    _, days_in_month = monthrange(year, month)

    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == emp.id,
        db.func.extract("year", AttendanceRecord.date) == year,
        db.func.extract("month", AttendanceRecord.date) == month,
    ).all()
    record_map = {r.date.day: r.status for r in records}

    present = sum(1 for r in records if r.status == "present")
    absent = sum(1 for r in records if r.status == "absent")
    half = sum(1 for r in records if r.status == "half_day")
    leave = sum(1 for r in records if r.status == "leave")
    total_marked = present + absent + half + leave
    pct = round(present / total_marked * 100) if total_marked else 0

    months = []
    for m in range(1, 13):
        months.append({"num": m, "name": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][m-1]})

    return render_template("mobile/attendance.html",
        emp=emp, year=year, month=month,
        days_in_month=days_in_month, record_map=record_map, today=today,
        present=present, absent=absent, half=half, leave=leave, pct=pct,
        months=months,
    )


@mobile_bp.route("/tasks")
def tasks():
    from datetime import timedelta
    emp = _emp()
    if not emp:
        return redirect(url_for("mobile.login"))
    today = date.today()
    end_of_week = today + timedelta(days=(6 - today.weekday()))
    open_tasks = TeamTask.query.filter_by(assignee_id=emp.id).filter(
        TeamTask.status.in_(["to_do", "in_progress"])
    ).order_by(TeamTask.due_date.asc(), TeamTask.created_at.desc()).all()
    done_tasks = TeamTask.query.filter_by(assignee_id=emp.id, status="done").order_by(
        TeamTask.completed_at.desc()
    ).limit(20).all()
    return render_template("mobile/tasks.html",
        emp=emp, today=today, end_of_week=end_of_week,
        open_tasks=open_tasks, done_tasks=done_tasks)


@mobile_bp.route("/tasks/toggle/<task_id>", methods=["POST"])
def toggle_task(task_id):
    emp = _emp()
    if not emp:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    task = db.session.get(TeamTask, int(task_id))
    if not task or task.assignee_id != emp.id:
        return jsonify({"ok": False, "error": "Not found"}), 404
    if task.status == "done":
        task.status = "to_do"
        task.completed_at = None
    else:
        task.status = "done"
        task.completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "status": task.status})


@mobile_bp.route("/profile")
def profile():
    emp = _emp()
    if not emp:
        return redirect(url_for("mobile.login"))
    today = date.today()
    month = today.month
    year = today.year

    present = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
        extract("month", AttendanceRecord.date) == month,
        extract("year", AttendanceRecord.date) == year,
    ).count()
    total_attn = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
        extract("month", AttendanceRecord.date) == month,
        extract("year", AttendanceRecord.date) == year,
    ).count()
    attn_pct = round((present / total_attn * 100), 1) if total_attn > 0 else 0

    tasks_done = TeamTask.query.filter_by(assignee_id=emp.id, status="done").filter(
        extract("month", TeamTask.completed_at) == month,
        extract("year", TeamTask.completed_at) == year,
    ).count()
    payrolls = PayrollRecord.query.filter_by(employee_id=emp.id).order_by(
        PayrollRecord.year.desc(), PayrollRecord.month.desc()
    ).limit(6).all()
    leave_stats = emp.get_paid_leave_stats()

    return render_template("mobile/profile.html",
        emp=emp, attn_pct=attn_pct,
        tasks_done=tasks_done, payrolls=payrolls,
        leave_stats=leave_stats,
    )


@mobile_bp.route("/attendance/scan")
def qr_scan():
    emp = _emp()
    if not emp:
        flash("No employee profile linked to your account.")
        return redirect(url_for("mobile.login"))
    today = date.today()
    existing = AttendanceRecord.query.filter_by(employee_id=emp.id, date=today).first()
    if existing:
        return render_template("mobile/qr_result.html", emp=emp, status=existing.status, already_marked=True)
    db.session.add(AttendanceRecord(employee_id=emp.id, date=today, status="present", marked_by=current_user.id))
    db.session.commit()
    log_action("qr_attendance", "AttendanceRecord", emp.id, f"QR attendance marked for {emp.name}")
    return render_template("mobile/qr_result.html", emp=emp, status="present", already_marked=False)


# ── Work Tab ───────────────────────────────────────────────────────
def _color_from_name(name):
    colors = ["#2563eb","#7c3aed","#059669","#d97706","#dc2626","#0891b2","#be185d","#6b7280"]
    h = sum(ord(c) for c in (name or "X"))
    return colors[h % len(colors)]


def _initials(name):
    parts = (name or "?").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return (parts[0][:2]).upper()


@mobile_bp.route("/work")
@login_required
def work():
    tab = request.args.get("tab", "orders")
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select a company first.")
        return redirect(url_for("home"))

    items = []
    stats = []

    if tab == "orders":
        orders = Order.query.filter_by(company_id=company_id).order_by(Order.created_at.desc()).limit(50).all()
        for o in orders:
            po = o.purchase_order
            status = po.status if po else "No PO"
            badge_cls = "badge-success" if po and po.status == "Received" else "badge-warning" if po and po.status == "Pending" else "badge-secondary"
            items.append({
                "url": url_for("orders.view_order", order_id=o.id),
                "initials": _initials(o.client.name if o.client else "??"),
                "color": _color_from_name(o.client.name if o.client else ""),
                "title": f"#{o.order_number or o.id} — {o.title or 'Untitled'}",
                "subtitle": o.client.name if o.client else "No client",
                "meta": f"{o.inquiry_date} • PO: {po.po_number if po and po.po_number else '—'}",
                "badge": status,
                "badge_class": badge_cls,
            })
        received = Order.query.filter_by(company_id=company_id).join(PurchaseOrder).filter(PurchaseOrder.status.in_(["Received","Delivered","Partially Delivered"])).count()
        pending = Order.query.filter_by(company_id=company_id).join(PurchaseOrder).filter(PurchaseOrder.status == "Pending").count()
        stats = [{"value": received, "label": "Active"}, {"value": pending, "label": "Pending PO"}]

    elif tab == "quotations":
        quotes = Quotation.query.filter_by(company_id=company_id).order_by(Quotation.id.desc()).limit(50).all()
        for q in quotes:
            client = q.order.client if q.order else None
            items.append({
                "url": url_for("quotations.view_quotation", quotation_id=q.id),
                "initials": _initials(client.name if client else "??"),
                "color": _color_from_name(client.name if client else ""),
                "title": q.quote_number or f"QT-{q.id}",
                "subtitle": client.name if client else "No client",
                "meta": f"{q.quote_date or ''}",
                "badge": "Draft" if not q.pdf_path else "Ready",
                "badge_class": "badge-secondary" if not q.pdf_path else "badge-success",
            })

    elif tab == "invoices":
        invs = Invoice.query.filter_by(company_id=company_id).order_by(Invoice.id.desc()).limit(50).all()
        for i in invs:
            bal = i.balance_due()
            badge_cls = "badge-success" if i.is_fully_paid() else "badge-danger" if bal > 0 else "badge-secondary"
            client = i.order.client if i.order else None
            items.append({
                "url": url_for("invoices.view_invoice", invoice_id=i.id),
                "initials": _initials(client.name if client else "??"),
                "color": _color_from_name(client.name if client else ""),
                "title": i.invoice_number or f"INV-{i.id}",
                "subtitle": client.name if client else "No client",
                "meta": f"{i.invoice_date} • {i.status.title()}",
                "badge": f"Bal: {bal:,.0f}" if not i.is_fully_paid() else "Paid",
                "badge_class": badge_cls,
            })
        total_outstanding = sum(i.balance_due() for i in invs)
        paid_count = sum(1 for i in invs if i.is_fully_paid())
        stats = [{"value": f"{total_outstanding:,.0f}", "label": "Outstanding"}, {"value": paid_count, "label": "Paid"}]

    elif tab == "challans":
        challans = DeliveryChallan.query.filter_by(company_id=company_id).order_by(DeliveryChallan.id.desc()).limit(50).all()
        for c in challans:
            client = c.order.client if c.order else None
            items.append({
                "url": url_for("challans.view_challan", challan_id=c.id),
                "initials": _initials(client.name if client else "??"),
                "color": _color_from_name(client.name if client else ""),
                "title": c.challan_number or f"DC-{c.id}",
                "subtitle": client.name if client else "No client",
                "meta": f"{c.dispatch_date}",
                "badge": "Ready" if c.pdf_path else "Draft",
                "badge_class": "badge-success" if c.pdf_path else "badge-secondary",
            })

    elif tab == "clients":
        clients = Client.query.filter_by(company_id=company_id).order_by(Client.name).limit(50).all()
        for c in clients:
            order_count = Order.query.filter_by(client_id=c.id, company_id=company_id).count()
            items.append({
                "url": url_for("clients.view_client", client_id=c.id),
                "initials": _initials(c.name),
                "color": _color_from_name(c.name),
                "title": c.name,
                "subtitle": c.contact_info or c.email or "",
                "meta": f"{order_count} order{'s' if order_count != 1 else ''}",
                "badge": "",
                "badge_class": "",
            })

    return render_template("mobile/work.html", tab=tab, items=items, stats=stats)


# ── Quick Action Placeholders ──────────────────────────────────────
@mobile_bp.route("/new/order")
@login_required
def new_order():
    return redirect(url_for("orders.add_order"))


@mobile_bp.route("/new/quotation")
@login_required
def new_quotation():
    return redirect(url_for("quotations.create_quotation"))


@mobile_bp.route("/new/invoice")
@login_required
def new_invoice():
    return redirect(url_for("invoices.create_invoice"))


@mobile_bp.route("/new/client")
@login_required
def new_client():
    return redirect(url_for("clients.add_client"))


# ── More Menu (server-rendered fallback) ───────────────────────────
@mobile_bp.route("/more")
@login_required
def more():
    return render_template("mobile/more.html")


# ── Install Page ───────────────────────────────────────────────────
@mobile_bp.route("/install")
def install_page():
    ua = request.headers.get("User-Agent", "").lower()
    is_ios = "iphone" in ua or "ipad" in ua
    is_android = "android" in ua
    is_safari = "safari" in ua and "chrome" not in ua
    return render_template("mobile/install.html", is_ios=is_ios, is_android=is_android, is_safari=is_safari)
