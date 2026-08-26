import secrets
from datetime import date, datetime, timedelta
from calendar import monthrange
import io, os, zipfile, math, base64
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, extract
from models import db, Company, User, Employee, AttendanceRecord, PayrollRecord, Todo, AuditLog, ExpenseCategory, Expense, Holiday, Notification, TeamTask
from audit import log_action
from routes.auth import hr_required
from utils import parse_float
from pdf_templates.salary_slip_template import generate_salary_slip_pdf
from qrcode.main import make as make_qr

hr_bp = Blueprint("hr", __name__, url_prefix="/hr")


def _task_velocity_score(employee_id, month, year):
    """Rolling average velocity: tasks done this month vs 3-month historical avg.
    Returns 0-100 score. New hires with no history get 100 if any tasks done this month."""
    done_this_month = TeamTask.query.filter_by(
        assignee_id=employee_id, status="done"
    ).filter(
        extract("month", TeamTask.completed_at) == month,
        extract("year", TeamTask.completed_at) == year,
    ).count()

    prev_counts = []
    for i in range(1, 4):
        ym = year * 12 + month - 1 - i
        py = ym // 12
        pm = ym % 12 + 1
        c = TeamTask.query.filter_by(
            assignee_id=employee_id, status="done"
        ).filter(
            extract("month", TeamTask.completed_at) == pm,
            extract("year", TeamTask.completed_at) == py,
        ).count()
        prev_counts.append(c)

    rolling_avg = sum(prev_counts) / max(len(prev_counts), 1)
    if rolling_avg <= 0:
        return 100.0 if done_this_month > 0 else 0.0
    score = min(done_this_month / rolling_avg * 100, 100.0)
    return round(score, 1)


@hr_bp.route("/")
@login_required
@hr_required
def dashboard():
    month = request.args.get("month", type=int) or date.today().month
    year = request.args.get("year", type=int) or date.today().year

    employees = Employee.query.filter(Employee.is_active == True).all()
    total_employees = len(employees)

    total_present = AttendanceRecord.query.filter(
        extract("month", AttendanceRecord.date) == month,
        extract("year", AttendanceRecord.date) == year,
        AttendanceRecord.status == "present",
    ).count()
    total_records = AttendanceRecord.query.filter(
        extract("month", AttendanceRecord.date) == month,
        extract("year", AttendanceRecord.date) == year,
    ).count()
    avg_attendance = round((total_present / total_records * 100), 1) if total_records > 0 else 0

    payroll_count = PayrollRecord.query.filter_by(month=month, year=year).count()
    finalized_count = PayrollRecord.query.filter_by(month=month, year=year, status="finalized").count()
    paid_count = PayrollRecord.query.filter_by(month=month, year=year, status="paid").count()

    efficiency_data = []
    for emp in employees:
        total_d = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        present_d = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        pct = (present_d / total_d * 100) if total_d > 0 else 0
        task_vel = _task_velocity_score(emp.id, month, year)
        combined = round(pct * 0.6 + task_vel * 0.4, 1)
        efficiency_data.append({"employee": emp, "attendance_pct": round(pct, 1), "task_pct": task_vel, "efficiency": combined})

    lowest = sorted(efficiency_data, key=lambda x: x["efficiency"])[:5]

    attention = []
    if low_attn := [e for e in efficiency_data if e["attendance_pct"] < 80 and e["attendance_pct"] > 0]:
        attention.append({"text": f"{len(low_attn)} employee(s) below 80% attendance this month", "severity": "warning"})
        # Notify admins about low attendance
        admins = User.query.filter(User.role.in_(["admin", "hr"])).all()
        for u in admins:
            if u.id != getattr(current_user, 'id', None):
                Notification.send(u.id, f"{len(low_attn)} employee(s) below 80% attendance for {month}/{year}",
                                  url_for("hr.dashboard", month=month, year=year))
    if payroll_count == 0 and total_employees > 0:
        attention.append({"text": f"Payroll not yet generated for {month}/{year}", "severity": "warning"})

    monthly_attn = []
    for m in range(1, 13):
        t = AttendanceRecord.query.filter(
            extract("month", AttendanceRecord.date) == m,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        p = AttendanceRecord.query.filter(
            extract("month", AttendanceRecord.date) == m,
            extract("year", AttendanceRecord.date) == year,
            AttendanceRecord.status == "present",
        ).count()
        monthly_attn.append(round((p / t * 100), 1) if t > 0 else 0)

    hr_entities = ["Employee", "AttendanceRecord", "PayrollRecord"]
    activity = AuditLog.query.filter(
        AuditLog.entity_type.in_(hr_entities)
    ).order_by(AuditLog.created_at.desc()).limit(8).all()

    upcoming_holidays = Holiday.query.filter(Holiday.date >= date.today()).order_by(Holiday.date).limit(5).all()
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()
    return render_template("hr/dashboard.html",
        total_employees=total_employees, avg_attendance=avg_attendance,
        payroll_count=payroll_count, finalized_count=finalized_count, paid_count=paid_count,
        efficiency_data=efficiency_data, lowest=lowest, attention=attention,
        month=month, year=year, monthly_attn=monthly_attn, activity=activity,
        now=datetime.utcnow(), upcoming_holidays=upcoming_holidays,
        notifications=notifications,
    )


# --- Employees ---

@hr_bp.route("/employees")
@login_required
@hr_required
def employee_list():
    month = request.args.get("month", type=int) or date.today().month
    year = request.args.get("year", type=int) or date.today().year
    company_id = session.get("active_company_id")

    query = Employee.query
    if company_id:
        query = query.filter(db.or_(Employee.company_id == company_id, Employee.company_id == None))
    employees = query.order_by(Employee.name).all()

    for emp in employees:
        total_d = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        present_d = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        emp._attn_pct = round((present_d / total_d * 100), 1) if total_d > 0 else 0
        task_vel = _task_velocity_score(emp.id, month, year)
        emp._efficiency = round(emp._attn_pct * 0.6 + task_vel * 0.4, 1)

    users = User.query.order_by(User.name).all()
    return render_template("hr/employees.html", employees=employees, month=month, year=year, users=users)


@hr_bp.route("/employees/add", methods=["POST"])
@login_required
@hr_required
def add_employee():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Employee name is required.")
        return redirect(url_for("hr.employee_list"))
    user_id = request.form.get("user_id", type=int) or None
    if user_id:
        existing = Employee.query.filter_by(user_id=user_id).first()
        if existing:
            flash("That user account is already linked to another employee.")
            return redirect(url_for("hr.employee_list"))
    emp = Employee(
        name=name,
        email=request.form.get("email", "").strip() or None,
        phone=request.form.get("phone", "").strip() or None,
        department=request.form.get("department", "").strip() or None,
        designation=request.form.get("designation", "").strip() or None,
        employee_code=request.form.get("employee_code", "").strip() or None,
        base_monthly_salary=parse_float(request.form.get("base_monthly_salary")),
        user_id=user_id,
        date_joined=datetime.strptime(request.form["date_joined"], "%Y-%m-%d").date() if request.form.get("date_joined") else None,
    )
    db.session.add(emp)
    db.session.commit()
    log_action("add_employee", "Employee", emp.id, f"Added {name}")
    flash("Employee added.")
    return redirect(url_for("hr.employee_list"))


@hr_bp.route("/employees/edit/<int:employee_id>", methods=["POST"])
@login_required
@hr_required
def edit_employee(employee_id):
    emp = db.session.get(Employee, employee_id)
    if not emp:
        flash("Employee not found.")
        return redirect(url_for("hr.employee_list"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("Employee name is required.")
        return redirect(url_for("hr.employee_profile", employee_id=emp.id))
    user_id = request.form.get("user_id", type=int) or None
    if user_id and user_id != emp.user_id:
        existing = Employee.query.filter(Employee.user_id == user_id, Employee.id != emp.id).first()
        if existing:
            flash("That user account is already linked to another employee.")
            return redirect(url_for("hr.employee_profile", employee_id=emp.id))
    emp.name = name
    emp.email = request.form.get("email", "").strip() or None
    emp.phone = request.form.get("phone", "").strip() or None
    emp.department = request.form.get("department", "").strip() or None
    emp.designation = request.form.get("designation", "").strip() or None
    emp.employee_code = request.form.get("employee_code", "").strip() or None
    emp.base_monthly_salary = parse_float(request.form.get("base_monthly_salary"))
    emp.user_id = user_id

    emp.date_joined = datetime.strptime(request.form["date_joined"], "%Y-%m-%d").date() if request.form.get("date_joined") else emp.date_joined
    emp.date_left = datetime.strptime(request.form["date_left"], "%Y-%m-%d").date() if request.form.get("date_left") else emp.date_left
    emp.is_active = True if request.form.get("is_active") else False
    db.session.commit()
    log_action("edit_employee", "Employee", emp.id, f"Edited {name}")
    flash("Employee updated.")
    return redirect(url_for("hr.employee_profile", employee_id=emp.id))


@hr_bp.route("/employees/leave-range", methods=["POST"])
@login_required
@hr_required
def mark_leave_range():
    employee_id = request.form.get("employee_id", type=int)
    start_str = request.form.get("start_date", "")
    end_str = request.form.get("end_date", "")
    emp = db.session.get(Employee, employee_id) if employee_id else None
    if not emp:
        flash("Employee not found.")
        return redirect(url_for("hr.employee_list"))
    if not start_str or not end_str:
        flash("Start and end dates are required.")
        return redirect(url_for("hr.employee_profile", employee_id=emp.id))
    start = datetime.strptime(start_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_str, "%Y-%m-%d").date()
    if end < start:
        flash("End date cannot be before start date.")
        return redirect(url_for("hr.employee_profile", employee_id=emp.id))
    count = 0
    current = start
    while current <= end:
        existing = AttendanceRecord.query.filter_by(employee_id=emp.id, date=current).first()
        if existing:
            existing.status = "leave"
            existing.marked_by = current_user.id
        else:
            db.session.add(AttendanceRecord(employee_id=emp.id, date=current, status="leave", marked_by=current_user.id))
        count += 1
        current += timedelta(days=1)
    db.session.commit()
    flash(f"Marked {count} day(s) as leave for {emp.name}.")

    # Notify the employee about leave being marked
    user_notified = False
    for u in User.query.all():
        if u.employee and u.employee.id == emp.id and u.id != getattr(current_user, 'id', None):
            Notification.send(u.id, f"Leave recorded: {count} day(s) from {start_str} — {emp.name}",
                              url_for("hr.employee_profile", employee_id=emp.id))
            user_notified = True
            break
    if not user_notified:
        admins = User.query.filter(User.role.in_(["admin", "hr"])).all()
        for u in admins:
            if u.id != getattr(current_user, 'id', None):
                Notification.send(u.id, f"Leave recorded: {count} day(s) for {emp.name} from {start_str}",
                                  url_for("hr.employee_profile", employee_id=emp.id))

    return redirect(url_for("hr.employee_profile", employee_id=emp.id))


@hr_bp.route("/employees/delete/<int:employee_id>", methods=["POST"])
@login_required
@hr_required
def delete_employee(employee_id):
    emp = db.session.get(Employee, employee_id)
    if emp:
        AttendanceRecord.query.filter_by(employee_id=emp.id).delete()
        PayrollRecord.query.filter_by(employee_id=emp.id).delete()
        db.session.delete(emp)
        db.session.commit()
        flash("Employee deleted.")
    return redirect(url_for("hr.employee_list"))


@hr_bp.route("/employees/<int:employee_id>")
@login_required
@hr_required
def employee_profile(employee_id):
    emp = db.session.get(Employee, employee_id)
    if not emp:
        flash("Employee not found.")
        return redirect(url_for("hr.employee_list"))

    year = request.args.get("year", type=int) or date.today().year
    users = User.query.order_by(User.name).all()

    records = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
        extract("year", AttendanceRecord.date) == year,
    ).order_by(AttendanceRecord.date).all()

    heatmap = {}
    for r in records:
        heatmap[r.date.isoformat()] = r.status

    monthly_pct = []
    for m in range(1, 13):
        total = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
            extract("month", AttendanceRecord.date) == m,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        present = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
            extract("month", AttendanceRecord.date) == m,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        monthly_pct.append(round((present / total * 100), 1) if total > 0 else 0)

    payroll_history = PayrollRecord.query.filter_by(employee_id=emp.id).order_by(PayrollRecord.year.desc(), PayrollRecord.month.desc()).all()

    now = date.today()
    task_vel = _task_velocity_score(emp.id, now.month, now.year)
    task_done_this_month = TeamTask.query.filter_by(assignee_id=emp.id, status="done").filter(
        extract("month", TeamTask.completed_at) == now.month,
        extract("year", TeamTask.completed_at) == now.year,
    ).count()
    task_rolling_counts = []
    for i in range(1, 4):
        ym = now.year * 12 + now.month - 1 - i
        task_rolling_counts.append(TeamTask.query.filter_by(assignee_id=emp.id, status="done").filter(
            extract("month", TeamTask.completed_at) == ym % 12 + 1,
            extract("year", TeamTask.completed_at) == ym // 12,
        ).count())
    task_rolling_avg = round(sum(task_rolling_counts) / 3, 1) if any(task_rolling_counts) else 0

    todos = Todo.query.filter_by(assignee_id=emp.user_id).order_by(Todo.due_date.asc()).all() if emp.user_id else []

    current_month_present = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
        extract("month", AttendanceRecord.date) == now.month,
        extract("year", AttendanceRecord.date) == now.year,
    ).count()
    current_month_total = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
        extract("month", AttendanceRecord.date) == now.month,
        extract("year", AttendanceRecord.date) == now.year,
    ).count()
    attn_pct = round((current_month_present / current_month_total * 100), 1) if current_month_total > 0 else 0
    efficiency = round(attn_pct * 0.6 + task_vel * 0.4, 1)
    leave_stats = emp.get_paid_leave_stats()

    return render_template("hr/profile.html",
        emp=emp, heatmap=heatmap, monthly_pct=monthly_pct,
        payroll_history=payroll_history, efficiency=efficiency,
        attn_pct=attn_pct, task_pct=task_vel, year=year,
        users=users, todos=todos,
        task_done_this_month=task_done_this_month, task_rolling_avg=task_rolling_avg,
        leave_stats=leave_stats,
    )


# --- Attendance ---

@hr_bp.route("/attendance")
@login_required
@hr_required
def attendance():
    month = request.args.get("month", type=int) or date.today().month
    year = request.args.get("year", type=int) or date.today().year
    company_id = session.get("active_company_id")

    query = Employee.query
    if company_id:
        query = query.filter(db.or_(Employee.company_id == company_id, Employee.company_id == None))
    employees = query.order_by(Employee.name).all()

    records = AttendanceRecord.query.filter(
        extract("month", AttendanceRecord.date) == month,
        extract("year", AttendanceRecord.date) == year,
    ).all()

    record_map = {}
    for r in records:
        record_map[(r.employee_id, r.date.isoformat())] = r.status

    for emp in employees:
        total_d = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        present_d = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        emp._monthly_pct = round((present_d / total_d * 100), 1) if total_d > 0 else 0

    _, days_in_month = monthrange(year, month)
    month_holidays = set()
    month_holiday_names = {}
    for h in Holiday.query.filter(
        db.or_(
            db.and_(extract("year", Holiday.date) == year, extract("month", Holiday.date) == month, Holiday.is_recurring == False),
            db.and_(extract("month", Holiday.date) == month, Holiday.is_recurring == True),
        )
    ).all():
        month_holidays.add(h.date.isoformat())
        month_holiday_names[h.date.isoformat()] = h.name
    return render_template("hr/attendance.html",
        employees=employees, record_map=record_map,
        month=month, year=year, days_in_month=days_in_month,
        month_holidays=month_holidays, month_holiday_names=month_holiday_names,
    )


@hr_bp.route("/attendance/mark", methods=["POST"])
@login_required
@hr_required
def mark_attendance():
    date_str = request.form.get("date", "")
    attn_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    month = attn_date.month
    year = attn_date.year

    employees = Employee.query.all()
    for emp in employees:
        status = request.form.get(f"status_{emp.id}", "").strip()
        if not status:
            continue
        existing = AttendanceRecord.query.filter_by(employee_id=emp.id, date=attn_date).first()
        if existing:
            existing.status = status
            existing.marked_by = current_user.id
        else:
            db.session.add(AttendanceRecord(employee_id=emp.id, date=attn_date, status=status, marked_by=current_user.id))
    db.session.commit()
    flash(f"Attendance recorded for {attn_date}.")
    return redirect(url_for("hr.attendance", month=month, year=year))


@hr_bp.route("/attendance/toggle", methods=["POST"])
@login_required
@hr_required
def toggle_attendance():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    emp_id = data.get("employee_id")
    date_str = data.get("date")
    new_status = data.get("status", "").strip()
    if not emp_id or not date_str or not new_status:
        return jsonify({"error": "Missing employee_id, date, or status"}), 400
    try:
        attn_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400
    if attn_date > date.today():
        return jsonify({"error": "Cannot mark future dates"}), 400
    valid_statuses = {"present", "absent", "half_day", "leave"}
    if new_status not in valid_statuses:
        return jsonify({"error": f"Invalid status: {new_status}"}), 400
    emp = db.session.get(Employee, emp_id)
    if not emp:
        return jsonify({"error": "Employee not found"}), 404
    existing = AttendanceRecord.query.filter_by(employee_id=emp_id, date=attn_date).first()
    if existing:
        existing.status = new_status
        existing.marked_by = current_user.id
    else:
        db.session.add(AttendanceRecord(employee_id=emp_id, date=attn_date, status=new_status, marked_by=current_user.id))
    db.session.commit()
    return jsonify({"ok": True, "employee_id": emp_id, "date": date_str, "status": new_status})


# --- Payroll ---

@hr_bp.route("/payroll")
@login_required
@hr_required
def payroll():
    month = request.args.get("month", type=int) or date.today().month
    year = request.args.get("year", type=int) or date.today().year

    records = PayrollRecord.query.filter_by(month=month, year=year).order_by(PayrollRecord.employee_id).all()
    employees = Employee.query.order_by(Employee.name).all()
    _, working_days = monthrange(year, month)
    working_days = working_days - 8

    return render_template("hr/payroll.html",
        records=records, employees=employees, month=month, year=year,
        working_days=working_days,
    )


@hr_bp.route("/payroll/generate", methods=["POST"])
@login_required
@hr_required
def generate_payroll():
    month = request.form.get("month", type=int) or date.today().month
    year = request.form.get("year", type=int) or date.today().year
    _, working_days = monthrange(year, month)
    working_days = working_days - 8

    employees = Employee.query.filter(Employee.is_active == True).all()
    count = 0
    start_of_month = date(year, month, 1)
    for emp in employees:
        existing = PayrollRecord.query.filter_by(employee_id=emp.id, month=month, year=year).first()
        if existing and existing.status != "draft":
            continue
        present = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        half_days = AttendanceRecord.query.filter_by(employee_id=emp.id, status="half_day").filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        leaves_this_month = AttendanceRecord.query.filter_by(employee_id=emp.id, status="leave").filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        prior_leaves = AttendanceRecord.query.filter_by(employee_id=emp.id, status="leave").filter(
            AttendanceRecord.date < start_of_month
        ).count()
        stats = emp.get_paid_leave_stats(as_of_date=start_of_month)
        available_before = max(0, stats["earned"] - prior_leaves)
        paid_leaves_used = min(leaves_this_month, available_before)
        daily_rate = emp.base_monthly_salary / working_days if working_days > 0 else 0
        payable_days = present + (0.5 * half_days) + paid_leaves_used
        calculated = daily_rate * payable_days
        if calculated > emp.base_monthly_salary:
            calculated = emp.base_monthly_salary
        calculated = round(calculated, 2)
        if existing:
            existing.days_present = present
            existing.half_days = half_days
            existing.paid_leaves_used = paid_leaves_used
            existing.calculated_salary = calculated
            existing.final_salary = round(calculated + existing.adjustment_amount, 2)
        else:
            db.session.add(PayrollRecord(
                employee_id=emp.id, month=month, year=year,
                base_salary=emp.base_monthly_salary, days_present=present,
                half_days=half_days, paid_leaves_used=paid_leaves_used,
                working_days_in_month=working_days,
                calculated_salary=calculated,
                final_salary=calculated,
                status="draft", generated_by=current_user.id,
            ))
        count += 1
    db.session.commit()
    flash(f"Payroll generated for {count} employee(s).")

    # Notify employees about payroll generation
    notified_ids = set()
    for u in User.query.all():
        if u.id in notified_ids:
            continue
        if u.employee and any(e.id == u.employee.id for e in employees):
            Notification.send(u.id, f"Payroll generated for {month}/{year}",
                              url_for("hr.payroll", month=month, year=year))
            notified_ids.add(u.id)

    return redirect(url_for("hr.payroll", month=month, year=year))


@hr_bp.route("/payroll/adjust", methods=["POST"])
@login_required
@hr_required
def payroll_adjust():
    record_id = request.form.get("record_id", type=int)
    adjustment = parse_float(request.form.get("adjustment_amount"))
    note = request.form.get("adjustment_note", "").strip()
    rec = db.session.get(PayrollRecord, record_id)
    if rec and rec.status == "draft":
        rec.adjustment_amount = adjustment
        rec.adjustment_note = note or None
        rec.final_salary = rec.calculated_salary + adjustment
        db.session.commit()
        flash("Adjustment applied.")
    return redirect(url_for("hr.payroll", month=rec.month, year=rec.year))


@hr_bp.route("/payroll/finalize/<int:record_id>", methods=["POST"])
@login_required
@hr_required
def payroll_finalize(record_id):
    rec = db.session.get(PayrollRecord, record_id)
    if rec and rec.status == "draft":
        rec.status = "finalized"
        db.session.flush()
        _create_payroll_expense(rec)
        db.session.commit()
        flash("Payroll record finalized.")
    return redirect(url_for("hr.payroll", month=rec.month, year=rec.year))


def _create_payroll_expense(rec):
    emp = db.session.get(Employee, rec.employee_id)
    if not emp:
        return
    existing_expense = Expense.query.filter_by(payroll_record_id=rec.id).first()
    if existing_expense:
        existing_expense.amount = rec.final_salary
        existing_expense.updated_by = current_user.id
        return
    labour_cat = ExpenseCategory.query.filter_by(name="Labour").first()
    exp = Expense(
        scope="general",
        company_id=emp.company_id,
        category_id=labour_cat.id if labour_cat else None,
        amount=rec.final_salary,
        notes=f"Salary – {emp.name} ({rec.month}/{rec.year})",
        payee=emp.name,
        expense_date=date(rec.year, rec.month, 1),
        payroll_record_id=rec.id,
        created_by=current_user.id,
    )
    db.session.add(exp)


@hr_bp.route("/payroll/mark-paid/<int:record_id>", methods=["POST"])
@login_required
@hr_required
def payroll_mark_paid(record_id):
    rec = db.session.get(PayrollRecord, record_id)
    if rec and rec.status == "finalized":
        rec.status = "paid"
        db.session.flush()
        _create_payroll_expense(rec)
        db.session.commit()
        flash("Payroll marked as paid.")
    return redirect(url_for("hr.payroll", month=rec.month, year=rec.year))


@hr_bp.route("/payroll/edit/<int:record_id>", methods=["POST"])
@login_required
@hr_required
def payroll_edit(record_id):
    rec = db.session.get(PayrollRecord, record_id)
    if not rec:
        flash("Payroll record not found.")
        return redirect(url_for("hr.payroll"))
    days_present = request.form.get("days_present", type=int) or 0
    half_days = request.form.get("half_days", type=int) or 0
    paid_leaves_used = parse_float(request.form.get("paid_leaves_used")) or 0.0
    working_days = request.form.get("working_days_in_month", type=int) or rec.working_days_in_month
    adjustment = parse_float(request.form.get("adjustment_amount"))
    daily_rate = rec.base_salary / working_days if working_days > 0 else 0
    payable_days = days_present + (0.5 * half_days) + paid_leaves_used
    calculated = daily_rate * payable_days
    if calculated > rec.base_salary:
        calculated = rec.base_salary
    rec.days_present = days_present
    rec.half_days = half_days
    rec.paid_leaves_used = paid_leaves_used
    rec.working_days_in_month = working_days
    rec.calculated_salary = round(calculated, 2)
    rec.adjustment_amount = adjustment
    rec.final_salary = round(calculated + adjustment, 2)
    db.session.flush()
    _create_payroll_expense(rec)
    db.session.commit()
    log_action("edit_payroll", "PayrollRecord", rec.id, f"Edited payroll for {rec.employee.name} {rec.month}/{rec.year}")
    flash("Payroll record updated.")
    return redirect(url_for("hr.payroll", month=rec.month, year=rec.year))


@hr_bp.route("/payroll/delete/<int:record_id>", methods=["POST"])
@login_required
@hr_required
def payroll_delete(record_id):
    rec = db.session.get(PayrollRecord, record_id)
    if not rec:
        flash("Payroll record not found.")
        return redirect(url_for("hr.payroll"))
    month = rec.month
    year = rec.year
    emp_name = rec.employee.name
    Expense.query.filter_by(payroll_record_id=record_id).delete()
    db.session.delete(rec)
    db.session.commit()
    log_action("delete_payroll", "PayrollRecord", record_id, f"Deleted payroll for {emp_name} {month}/{year}")
    flash("Payroll record deleted.")
    return redirect(url_for("hr.payroll", month=month, year=year))


@hr_bp.route("/payroll/slip/<int:record_id>")
@login_required
@hr_required
def download_salary_slip(record_id):
    rec = db.session.get(PayrollRecord, record_id)
    if not rec:
        flash("Payroll record not found.")
        return redirect(url_for("hr.payroll"))
    emp = db.session.get(Employee, rec.employee_id)
    company = db.session.get(Company, emp.company_id) if emp and emp.company_id else None
    pdf_dir = os.path.join(current_app.root_path, "static", "generated_pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f"salary_slip_{record_id}.pdf")
    generate_salary_slip_pdf(company, emp, rec, pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name=f"salary_slip_{emp.name}_{rec.month}_{rec.year}.pdf")


@hr_bp.route("/payroll/slips-bulk", methods=["POST"])
@login_required
@hr_required
def download_bulk_slips():
    month = request.form.get("month", type=int) or date.today().month
    year = request.form.get("year", type=int) or date.today().year
    records = PayrollRecord.query.filter_by(month=month, year=year).all()
    if not records:
        flash("No payroll records for this period.")
        return redirect(url_for("hr.payroll", month=month, year=year))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rec in records:
            emp = db.session.get(Employee, rec.employee_id)
            if not emp:
                continue
            company = db.session.get(Company, emp.company_id) if emp.company_id else None
            pdf_dir = os.path.join(current_app.root_path, "static", "generated_pdfs")
            os.makedirs(pdf_dir, exist_ok=True)
            pdf_path = os.path.join(pdf_dir, f"salary_slip_{rec.id}.pdf")
            generate_salary_slip_pdf(company, emp, rec, pdf_path)
            zf.write(pdf_path, f"{emp.name}_{rec.month}_{rec.year}.pdf")
            try:
                os.remove(pdf_path)
            except OSError:
                pass
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"salary_slips_{month}_{year}.zip")


# --- Efficiency ---

@hr_bp.route("/efficiency")
@login_required
@hr_required
def efficiency():
    month = request.args.get("month", type=int) or date.today().month
    year = request.args.get("year", type=int) or date.today().year
    sort = request.args.get("sort", "combined")
    company_id = session.get("active_company_id")

    query = Employee.query
    if company_id:
        query = query.filter(db.or_(Employee.company_id == company_id, Employee.company_id == None))
    employees = query.order_by(Employee.name).all()

    data = []
    for emp in employees:
        total_d = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        present_d = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        attn_pct = (present_d / total_d * 100) if total_d > 0 else 0
        task_vel = _task_velocity_score(emp.id, month, year)
        combined = round(attn_pct * 0.6 + task_vel * 0.4, 1)
        data.append({
            "employee": emp,
            "attendance_pct": round(attn_pct, 1),
            "task_pct": task_vel,
            "efficiency": combined,
        })

    reverse = sort != "efficiency"
    data.sort(key=lambda x: x.get(sort, 0) if sort in x else 0, reverse=reverse)

    chart_data = [
        {"name": d["employee"].name, "attendance_pct": d["attendance_pct"], "task_pct": d["task_pct"], "efficiency": d["efficiency"]}
        for d in data
    ]
    return render_template("hr/efficiency.html", efficiency_data=data, chart_data=chart_data, month=month, year=year, sort=sort)


# --- Holidays ---

@hr_bp.route("/holidays")
@login_required
@hr_required
def list_holidays():
    year = request.args.get("year", type=int) or date.today().year
    holidays = Holiday.query.filter(
        db.or_(
            db.and_(extract("year", Holiday.date) == year, Holiday.is_recurring == False),
            Holiday.is_recurring == True,
        )
    ).order_by(Holiday.date).all()
    return render_template("hr/holidays.html", holidays=holidays, year=year)


@hr_bp.route("/holidays/add", methods=["POST"])
@login_required
@hr_required
def add_holiday():
    date_str = request.form.get("date", "")
    name = request.form.get("name", "").strip()
    is_recurring = True if request.form.get("is_recurring") else False
    if not date_str or not name:
        flash("Date and name are required.")
        return redirect(url_for("hr.list_holidays"))
    try:
        h_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date.")
        return redirect(url_for("hr.list_holidays"))
    existing = Holiday.query.filter_by(date=h_date, company_id=None).first()
    if existing:
        flash(f"Holiday already exists on {h_date}.")
        return redirect(url_for("hr.list_holidays"))
    h = Holiday(date=h_date, name=name, is_recurring=is_recurring)
    db.session.add(h)
    db.session.commit()
    Notification.send_all_employees(f"New holiday: {name} on {h_date}", url_for("hr.list_holidays"))
    log_action("add_holiday", "Holiday", h.id, f"Added {name} on {h_date}")
    flash(f"Holiday '{name}' added.")
    return redirect(url_for("hr.list_holidays", year=h_date.year))


@hr_bp.route("/holidays/delete/<int:holiday_id>", methods=["POST"])
@login_required
@hr_required
def delete_holiday(holiday_id):
    h = db.session.get(Holiday, holiday_id)
    if h:
        db.session.delete(h)
        db.session.commit()
        log_action("delete_holiday", "Holiday", holiday_id, f"Deleted {h.name}")
        flash("Holiday deleted.")
    return redirect(url_for("hr.list_holidays"))


# --- Notifications ---

@hr_bp.route("/notifications/read/<int:notif_id>", methods=["POST"])
@login_required
@hr_required
def mark_notification_read(notif_id):
    n = db.session.get(Notification, notif_id)
    if n and n.user_id == current_user.id:
        n.is_read = True
        db.session.commit()
    return jsonify({"ok": True})


@hr_bp.route("/notifications/read-all", methods=["POST"])
@login_required
@hr_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


# --- QR Attendance ---

@hr_bp.route("/attendance/qr-setup")
@login_required
@hr_required
def qr_setup():
    scan_url = url_for("hr.qr_landing", _external=True)
    img = make_qr(scan_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()
    return render_template("hr/qr_setup.html", qr_b64=qr_b64, scan_url=scan_url)


@hr_bp.route("/attendance/qr")
def qr_landing():
    if current_user.is_authenticated:
        if current_user.employee:
            ua = (request.user_agent.string or "").lower()
            mobile_patterns = ("android", "iphone", "ipad", "ipod", "blackberry", "windows phone", "opera mini", "iemobile", "mobile")
            if any(p in ua for p in mobile_patterns):
                return redirect(url_for("mobile.qr_scan"))
            return redirect(url_for("hr.qr_scan"))
        flash("No employee profile linked to your account.")
        return redirect(url_for("auth.login"))
    return redirect(url_for("auth.login"))


@hr_bp.route("/attendance/scan")
@login_required
def qr_scan():
    emp = current_user.employee
    if not emp:
        flash("No employee profile linked to your account.")
        return redirect(url_for("home"))
    today = date.today()
    existing = AttendanceRecord.query.filter_by(employee_id=emp.id, date=today).first()
    if existing:
        return render_template("hr/qr_result.html", emp=emp, status=existing.status, already_marked=True)
    db.session.add(AttendanceRecord(employee_id=emp.id, date=today, status="present", marked_by=current_user.id))
    db.session.commit()
    log_action("qr_attendance", "AttendanceRecord", emp.id, f"QR attendance marked for {emp.name}")
    return render_template("hr/qr_result.html", emp=emp, status="present", already_marked=False)


@hr_bp.route("/employees/create-accounts", methods=["POST"])
@login_required
@hr_required
def bulk_create_user_accounts():
    created = 0
    skipped = 0
    employees = Employee.query.filter(Employee.user_id == None).order_by(Employee.name).all()
    for emp in employees:
        email = emp.email
        if not email:
            email = (emp.employee_code or f"emp{emp.id}") + "@vams.local"
        if User.query.filter_by(email=email).first():
            skipped += 1
            continue
        password = secrets.token_urlsafe(8)
        user = User(email=email, name=emp.name, role="employee")
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        emp.user_id = user.id
        log_action("create_user_account", "User", user.id, f"Auto-created user account for {emp.name}")
        created += 1
    db.session.commit()
    flash(f"Created {created} user account(s). Skipped {skipped} (already existed).")
    return redirect(url_for("hr.employee_list"))
