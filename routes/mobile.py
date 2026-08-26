from datetime import date, datetime
from calendar import monthrange
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Employee, AttendanceRecord, TeamTask, Notification, PayrollRecord
from audit import log_action
from sqlalchemy import extract

mobile_bp = Blueprint("mobile", __name__, url_prefix="/m")


def _emp():
    if current_user.is_authenticated and current_user.employee:
        return current_user.employee
    emp_id = session.get("m_emp_id")
    return db.session.get(Employee, emp_id) if emp_id else None


@mobile_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("mobile.home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active_user:
            login_user(user, remember=True)
            if user.employee:
                session["m_emp_id"] = user.employee.id
            flash("Logged in.")
            return redirect(url_for("mobile.home"))
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
