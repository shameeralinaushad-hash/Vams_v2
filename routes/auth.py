from functools import wraps
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Employee, AuditLog, Holiday, Notification, AttendanceRecord, PayrollRecord, Todo, TeamTask
from sqlalchemy import or_, extract, text
from permissions import AVAILABLE_PERMISSIONS
from login_throttle import is_locked_out, record_failure, clear_failures, minutes_until_unlock, MAX_ATTEMPTS
from audit import log_action
import requests as http_requests

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _min_pw_len():
    return current_app.config.get("MIN_PASSWORD_LENGTH", 8)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Admin access required.")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


def hr_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role not in ("admin", "hr"):
            flash("HR access required.")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        # --- Turnstile verification ---
        turnstile_secret = current_app.config.get("TURNSTILE_SECRET_KEY", "")
        if turnstile_secret:
            token = request.form.get("cf-turnstile-response", "")
            if not token:
                flash("Please complete the security check.")
                return render_template("auth/login.html")
            resp = http_requests.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": turnstile_secret, "response": token},
                timeout=5,
            )
            result = resp.json()
            if not result.get("success"):
                flash("Security check failed. Please try again.")
                return render_template("auth/login.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if is_locked_out(email):
            wait = minutes_until_unlock(email)
            flash(f"Too many failed login attempts for this account. Please try again in about {wait} minute(s).")
            return render_template("auth/login.html")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_active_user:
            clear_failures(email)
            login_user(user, remember=True)
            if not user.employee:
                emp = Employee.query.filter_by(email=email).first()
                if emp and not emp.user_id:
                    flash("Your email matches an employee profile. Visit your profile to link it.", "info")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("home"))

        record_failure(email)
        if is_locked_out(email):
            log_action("account_locked", "User", user.id if user else None,
                       f"Account '{email}' locked out after {MAX_ATTEMPTS} failed login attempts")
        flash("Invalid email or password.")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")

        if not current_user.check_password(current_password):
            flash("Current password is incorrect.")
            return redirect(url_for("auth.change_password"))

        if len(new_password) < _min_pw_len():
            flash(f"New password must be at least {_min_pw_len()} characters.")
            return redirect(url_for("auth.change_password"))

        current_user.set_password(new_password)
        db.session.commit()
        flash("Password updated.")
        return redirect(url_for("home"))

    return render_template("auth/change_password.html")


@auth_bp.route("/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "staff")
        new_password = request.form.get("new_password", "")

        existing = User.query.filter(User.email == email, User.id != user.id).first()
        if existing:
            flash("Another user already has that email.")
            return redirect(url_for("auth.edit_user", user_id=user.id))

        if user.id == current_user.id and role != "admin":
            flash("You can't remove your own admin access.")
            return redirect(url_for("auth.edit_user", user_id=user.id))

        user.email = email
        user.name = name
        user.role = role

        link_emp_id = request.form.get("link_employee_id", "")
        if link_emp_id == "__unlink__":
            if user.employee:
                user.employee.user_id = None
        elif link_emp_id:
            emp = db.session.get(Employee, int(link_emp_id))
            if emp and emp.user_id and emp.user_id != user.id:
                flash("That employee is already linked to another user.")
                return redirect(url_for("auth.edit_user", user_id=user.id))
            if emp:
                emp.user_id = user.id

        selected_perms = request.form.getlist("permissions")
        valid_keys = {key for key, _ in AVAILABLE_PERMISSIONS}
        user.permissions = ",".join(p for p in selected_perms if p in valid_keys)

        if new_password:
            if len(new_password) < _min_pw_len():
                flash(f"New password must be at least {_min_pw_len()} characters.")
                return redirect(url_for("auth.edit_user", user_id=user.id))
            user.set_password(new_password)

        db.session.commit()
        flash(f"User '{user.email}' updated.")
        return redirect(url_for("auth.list_users"))

    employees = Employee.query.order_by(Employee.name).all()
    return render_template("auth/edit_user.html", user=user, available_permissions=AVAILABLE_PERMISSIONS, employees=employees)


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        current_user.name = name
        db.session.commit()
        flash("Profile updated.")
        return redirect(url_for("auth.profile"))

    emp = current_user.employee
    month = date.today().month
    year = date.today().year

    attn_pct = 0
    monthly_pct = []
    payroll_history = []
    efficiency = 0
    todo_total = 0
    todo_done = 0
    tasks = []

    if emp:
        records = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
            extract("year", AttendanceRecord.date) == year,
        ).order_by(AttendanceRecord.date).all()

        heatmap = {}
        for r in records:
            heatmap[r.date.isoformat()] = r.status

        present = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        total = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
            extract("month", AttendanceRecord.date) == month,
            extract("year", AttendanceRecord.date) == year,
        ).count()
        attn_pct = round((present / total * 100), 1) if total > 0 else 0

        for m in range(1, 13):
            t = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
                extract("month", AttendanceRecord.date) == m,
                extract("year", AttendanceRecord.date) == year,
            ).count()
            p = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
                extract("month", AttendanceRecord.date) == m,
                extract("year", AttendanceRecord.date) == year,
            ).count()
            monthly_pct.append(round((p / t * 100), 1) if t > 0 else 0)

        payroll_history = PayrollRecord.query.filter_by(employee_id=emp.id).order_by(
            PayrollRecord.year.desc(), PayrollRecord.month.desc()
        ).all()

        done_this_month = TeamTask.query.filter_by(assignee_id=emp.id, status="done").filter(
            extract("month", TeamTask.completed_at) == month,
            extract("year", TeamTask.completed_at) == year,
        ).count()
        prev_counts = []
        for i in range(1, 4):
            ym = year * 12 + month - 1 - i
            py = ym // 12
            pm = ym % 12 + 1
            c = TeamTask.query.filter_by(assignee_id=emp.id, status="done").filter(
                extract("month", TeamTask.completed_at) == pm,
                extract("year", TeamTask.completed_at) == py,
            ).count()
            prev_counts.append(c)
        rolling_avg = sum(prev_counts) / max(len(prev_counts), 1)
        task_pct = round(min(done_this_month / rolling_avg * 100, 100.0), 1) if rolling_avg > 0 else (100.0 if done_this_month > 0 else 0.0)
        efficiency = round(attn_pct * 0.6 + task_pct * 0.4, 1)
        task_done_this_month = done_this_month
        task_rolling_avg = round(sum(prev_counts) / 3, 1) if any(prev_counts) else 0
        tasks = Todo.query.filter_by(assignee_id=emp.user_id).order_by(Todo.due_date.asc()).all() if emp.user_id else []
        leave_stats = emp.get_paid_leave_stats()
    else:
        heatmap = {}
        monthly_pct = [0] * 12
        tasks = []
        leave_stats = None
        task_pct = 0
        task_done_this_month = 0
        task_rolling_avg = 0

    upcoming_holidays = Holiday.query.filter(Holiday.date >= date.today()).order_by(Holiday.date).limit(5).all()
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()
    return render_template("auth/profile.html",
        emp=emp, heatmap=heatmap, monthly_pct=monthly_pct,
        payroll_history=payroll_history, attn_pct=attn_pct,
        efficiency=efficiency, task_pct=task_pct,
        task_done_this_month=task_done_this_month, task_rolling_avg=task_rolling_avg,
        tasks=tasks, year=year, leave_stats=leave_stats,
        upcoming_holidays=upcoming_holidays, notifications=notifications,
    )


@auth_bp.route("/users")
@login_required
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("auth/users.html", users=users)


@auth_bp.route("/users/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_user():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff")

        if User.query.filter_by(email=email).first():
            flash("A user with that email already exists.")
            return redirect(url_for("auth.add_user"))

        if len(password) < _min_pw_len():
            flash(f"Password must be at least {_min_pw_len()} characters.")
            return redirect(url_for("auth.add_user"))

        user = User(email=email, name=name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        emp = Employee.query.filter_by(email=email).first()
        if emp and not emp.user_id:
            emp.user_id = user.id
        db.session.commit()
        flash(f"User '{email}' created.")
        return redirect(url_for("auth.list_users"))

    return render_template("auth/add_user.html")


@auth_bp.route("/users/toggle/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("You can't deactivate your own account.")
        return redirect(url_for("auth.list_users"))

    user.is_active_user = not user.is_active_user
    db.session.commit()
    flash(f"User '{user.email}' {'activated' if user.is_active_user else 'deactivated'}.")
    return redirect(url_for("auth.list_users"))


@auth_bp.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("You can't delete your own account.")
        return redirect(url_for("auth.list_users"))

    _detach_user_dependencies(user.id)
    db.session.delete(user)
    log_action("user.deleted", "user", user.id, f"Admin {current_user.email} deleted user {user.email}")
    db.session.commit()
    flash(f"User '{user.email}' deleted.")
    return redirect(url_for("auth.list_users"))


def _detach_user_dependencies(user_id):
    """Sever every row that references the user so FK constraints allow deletion.

    Columns with a direct FK to ``users.id`` are either set to NULL (nullable
    columns) or deleted (NOT NULL columns). Children of deleted rows that do not
    reference users directly are cleaned up first to satisfy their own FKs.
    """
    targets = []
    for mapper in db.Model.registry.mappers:
        for col in mapper.columns:
            for fk in col.foreign_keys:
                if fk.column.table.name == "users" and fk.column.name == "id":
                    targets.append((col.table.name, col.name, col.nullable))

    dedup = {}
    for table, column, nullable in targets:
        dedup.setdefault((table, column), nullable)

    db.session.execute(text(
        "DELETE FROM personal_item_milestones WHERE personal_item_id IN "
        "(SELECT id FROM personal_items WHERE user_id = :uid)"
    ), {"uid": user_id})

    for (table, column), nullable in dedup.items():
        if nullable:
            db.session.execute(text(
                f'UPDATE "{table}" SET "{column}" = NULL WHERE "{column}" = :uid'
            ), {"uid": user_id})
        else:
            db.session.execute(text(
                f'DELETE FROM "{table}" WHERE "{column}" = :uid'
            ), {"uid": user_id})


@auth_bp.route("/audit-log")
@login_required
@admin_required
def audit_log():
    # Fixed: Changed AuditLog.timestamp to AuditLog.created_at
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).all()
    # Fixed: Pointing to the correct folder
    return render_template("reports/audit_log.html", logs=logs)


@auth_bp.route("/toggle-email-notify", methods=["POST"])
@login_required
def toggle_email_notify():
    current_user.email_notifications = request.form.get("email_notifications") == "on"
    db.session.commit()
    flash("Email notification preference updated.")
    return redirect(request.referrer or url_for("auth.profile"))