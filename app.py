import os
import logging
import zoneinfo
from calendar import monthrange
from datetime import datetime, date, timedelta
from logging.handlers import RotatingFileHandler

from flask import (
    Flask, render_template, session, redirect, url_for,
    flash, send_from_directory, jsonify, request, make_response
)
from flask_login import LoginManager, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from dotenv import load_dotenv
from sqlalchemy import extract
from sqlalchemy.orm import selectinload

from config import Config
from models import db, Company, User, Order, Invoice, Todo, Expense, ExpenseCategory, Employee, AttendanceRecord, PayrollRecord, Holiday, Notification, TeamTask, Quotation, DeliveryChallan, PersonalItem, ActionSnooze, PurchaseOrder, PurchaseOrderLineItem
from important_actions import build_actions, DEFAULT_SNOOZE_HOURS
from ml.tender_extractor import extract_items_from_file

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # --- Custom Currency Filter ---
    @app.template_filter('currency')
    def format_currency(value):
        if value is None:
            return "0"
        try:
            value = float(value)
        except (ValueError, TypeError):
            return str(value)

        # Format millions with M, others with commas, 0 dollar signs
        if value >= 1000000:
            return f"{value / 1000000:,.2f}M"
        else:
            return f"{value:,.0f}"

    # --- Custom Local Time Filter ---
    @app.template_filter('local_time')
    def local_time_filter(value):
        if value is None:
            return ""
        # Assume the value is naive UTC, add UTC timezone info
        utc_dt = value.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
        # Convert to Asia/Karachi (PKT)
        local_dt = utc_dt.astimezone(zoneinfo.ZoneInfo("Asia/Karachi"))
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')

    # --- Jinja2 globals ---
    app.jinja_env.globals.update(date=date, timedelta=timedelta)

    os.makedirs(os.path.join(app.root_path, "database"), exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["LETTERHEAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["CLIENT_LOGO_FOLDER"], exist_ok=True)
    os.makedirs(app.config["COMPANY_LOGO_FOLDER"], exist_ok=True)
    os.makedirs(app.config["SIGNATURE_FOLDER"], exist_ok=True)
    os.makedirs(app.config["COMPANY_DOCS_FOLDER"], exist_ok=True)
    os.makedirs(app.config["RECEIPTS_FOLDER"], exist_ok=True)

    # ---- Logging setup ----
    log_dir = os.path.join(app.root_path, "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=1024 * 1024 * 5, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
    ))
    file_handler.setLevel(logging.WARNING)
    app.logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    app.logger.addHandler(console)
    app.logger.setLevel(logging.DEBUG)

    for logger_name in ("werkzeug",):
        l = logging.getLogger(logger_name)
        l.setLevel(logging.DEBUG)
        l.addHandler(console)

    if not app.debug:
        app.jinja_env.auto_reload = False

    db.init_app(app)
    migrate = Migrate(app, db)
    csrf = CSRFProtect(app)

    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[app.config.get("RATELIMIT_DEFAULT", "120 per minute")],
        storage_uri="memory://",
        enabled=app.config.get("RATELIMIT_ENABLED", True),
    )

    # --- Security headers ---
    @app.after_request
    def add_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if app.config.get("SESSION_COOKIE_SECURE", False):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        # Updated from User.query.get() for SQLAlchemy 2.0 compatibility
        return db.session.get(User, int(user_id))

    # Register module blueprints
    from routes.auth import auth_bp, admin_required
    from routes.companies import companies_bp
    from routes.clients import clients_bp
    from routes.orders import orders_bp
    from routes.quotations import quotations_bp
    from routes.invoices import invoices_bp
    from routes.challans import challans_bp
    from routes.catalog import catalog_bp
    from routes.payments import payments_bp
    from routes.reports import reports_bp
    from routes.todos import todos_bp
    from routes.expenses import expenses_bp
    from routes.search import search_bp
    from routes.company_documents import company_documents_bp
    from routes.maintenance import maintenance_bp, is_maintenance_mode_on
    from routes.settings import settings_bp
    from routes.pdf_view import pdf_view_bp
    from routes.accounts import accounts_bp
    from routes.hr import hr_bp
    from routes.tasks import tasks_bp
    from routes.projects import projects_bp
    from routes.ai import ai_bp
    from routes.mobile import mobile_bp
    app.register_blueprint(mobile_bp)
    app.register_blueprint(pdf_view_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(quotations_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(challans_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(todos_bp)
    app.register_blueprint(company_documents_bp)

    # --- PWA Service Worker Route ---
    @app.route('/sw.js')
    def serve_service_worker():
        return send_from_directory('static', 'sw.js')

    @app.route('/offline/')
    def offline_page():
        return render_template("errors/offline.html")

    # Mobile device detection via user-agent
    MOBILE_UA_PATTERNS = (
        "android", "iphone", "ipad", "ipod", "blackberry",
        "windows phone", "opera mini", "iemobile", "mobile"
    )
    def _is_mobile():
        ua = (request.user_agent.string or "").lower()
        return any(p in ua for p in MOBILE_UA_PATTERNS)

    @app.before_request
    def redirect_mobile():
        if not _is_mobile():
            return None
        if request.endpoint and request.endpoint.startswith("mobile."):
            return None
        if request.endpoint in ("static", "offline_page", "hr.qr_landing", "hr.qr_scan", "serve_service_worker"):
            return None
        if request.endpoint and request.endpoint.startswith("ai."):
            return None
        if session.get("desktop_mode") or request.args.get("desktop") == "1":
            if request.args.get("desktop") == "1":
                session["desktop_mode"] = True
            return None
        if current_user.is_authenticated:
            return redirect(url_for("mobile.home"))
        return redirect(url_for("mobile.login"))

    @app.before_request
    def require_login():
        allowed_endpoints = {"auth.login", "static", "offline_page", "hr.qr_landing", "hr.qr_scan", "mobile.login", "mobile.home", "mobile.attendance", "mobile.qr_scan", "mobile.tasks", "mobile.toggle_task", "mobile.logout"}
        if request.endpoint and request.endpoint not in allowed_endpoints and not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.path))

    with app.app_context():
        db.create_all()

        # One-time migration sentinel — skip if already completed
        migration_flag = os.path.join(os.path.dirname(__file__), "database", ".migrated")
        if not os.path.exists(migration_flag):

            # Migrate expenses table: add new columns + make company_id nullable
            import sqlalchemy as sa
            insp = sa.inspect(db.engine)
            exp_cols_info = insp.get_columns("expenses")
            exp_cols = [c["name"] for c in exp_cols_info]
            old_company_nullable = next(
                (c.get("nullable", True) for c in exp_cols_info if c["name"] == "company_id"),
                True
            )
            exp_missing_new = [c for c in ["category_id", "scope", "payment_method", "receipt_filename", "created_by", "payee", "payroll_record_id", "updated_by", "updated_at"] if c not in exp_cols]
            if exp_missing_new or not old_company_nullable:
                col_defs_sql = [
                    "id INTEGER PRIMARY KEY AUTOINCREMENT",
                    "company_id INTEGER REFERENCES companies(id)",
                    "order_id INTEGER REFERENCES orders(id)",
                    "category VARCHAR(100)",
                    "category_id INTEGER REFERENCES expense_categories(id)",
                    "scope VARCHAR(20) DEFAULT 'company'",
                    "amount FLOAT NOT NULL",
                    "expense_date DATE",
                    "notes VARCHAR(300)",
                    "payee VARCHAR(200)",
                    "payment_method VARCHAR(20)",
                    "receipt_filename VARCHAR(200)",
                    "payroll_record_id INTEGER REFERENCES payroll_records(id)",
                    "created_by INTEGER REFERENCES users(id)",
                    "updated_by INTEGER REFERENCES users(id)",
                    "created_at DATETIME",
                    "updated_at DATETIME",
                ]
                all_src = [
                    "id", "company_id", "order_id", "category",
                    "NULL AS category_id", "'company' AS scope",
                    "amount", "expense_date", "notes",
                    "NULL AS payee",
                    "NULL AS payment_method", "NULL AS receipt_filename",
                    "NULL AS payroll_record_id",
                    "NULL AS created_by", "NULL AS updated_by",
                    "created_at", "NULL AS updated_at",
                ]
                db.session.execute(sa.text("DROP TABLE IF EXISTS expenses_new"))
                db.session.execute(sa.text(f"CREATE TABLE expenses_new ({', '.join(col_defs_sql)})"))
                db.session.execute(sa.text(f"INSERT INTO expenses_new SELECT {', '.join(all_src)} FROM expenses"))
                db.session.execute(sa.text("DROP TABLE expenses"))
                db.session.execute(sa.text("ALTER TABLE expenses_new RENAME TO expenses"))
            db.session.commit()

            # Migrate employees table: add new columns
            emp_cols_info = sa.inspect(db.engine).get_columns("employees")
            emp_cols = [c["name"] for c in emp_cols_info]
            emp_missing = [c for c in ["email", "phone", "department", "employee_code", "user_id", "date_left"] if c not in emp_cols]
            if emp_missing:
                col_defs = [
                    "id INTEGER PRIMARY KEY AUTOINCREMENT",
                    "name VARCHAR(150) NOT NULL",
                    "email VARCHAR(150)",
                    "phone VARCHAR(30)",
                    "department VARCHAR(100)",
                    "designation VARCHAR(100)",
                    "employee_code VARCHAR(50)",
                    "company_id INTEGER REFERENCES companies(id)",
                    "user_id INTEGER REFERENCES users(id)",
                    "base_monthly_salary FLOAT DEFAULT 0",
                    "date_joined DATE",
                    "date_left DATE",
                    "is_active BOOLEAN DEFAULT 1",
                    "created_at DATETIME",
                ]
                src_cols = (
                    "id", "name",
                    "NULL AS email", "NULL AS phone", "NULL AS department",
                    "designation", "NULL AS employee_code",
                    "company_id", "NULL AS user_id",
                    "base_monthly_salary", "date_joined",
                    "NULL AS date_left", "is_active", "created_at"
                )
                db.session.execute(sa.text("DROP TABLE IF EXISTS employees_new"))
                db.session.execute(sa.text(f"CREATE TABLE employees_new ({', '.join(col_defs)})"))
                db.session.execute(sa.text(f"INSERT INTO employees_new SELECT {', '.join(src_cols)} FROM employees"))
                db.session.execute(sa.text("DROP TABLE employees"))
                db.session.execute(sa.text("ALTER TABLE employees_new RENAME TO employees"))
                db.session.commit()

            # Migrate payroll_records table: add paid_leaves_used column
            pr_cols_info = sa.inspect(db.engine).get_columns("payroll_records")
            pr_cols = [c["name"] for c in pr_cols_info]
            if "paid_leaves_used" not in pr_cols:
                db.session.execute(sa.text("ALTER TABLE payroll_records ADD COLUMN paid_leaves_used FLOAT DEFAULT 0"))
                db.session.commit()

            # Migrate budgets table: add month, year, recurring
            bud_cols_info = sa.inspect(db.engine).get_columns("budgets")
            bud_cols = [c["name"] for c in bud_cols_info]
            bud_missing = [c for c in ["month", "year", "recurring"] if c not in bud_cols]
            if bud_missing:
                bud_col_defs = [
                    "id INTEGER PRIMARY KEY AUTOINCREMENT",
                    "scope VARCHAR(30) NOT NULL",
                    "company_id INTEGER REFERENCES companies(id)",
                    "category_id INTEGER REFERENCES expense_categories(id)",
                    "month INTEGER NOT NULL DEFAULT 1",
                    "year INTEGER NOT NULL DEFAULT 2026",
                    "period_type VARCHAR(10) DEFAULT 'monthly'",
                    "period_start DATE",
                    "period_end DATE",
                    "amount FLOAT NOT NULL",
                    "recurring BOOLEAN DEFAULT 0",
                    "created_by INTEGER REFERENCES users(id)",
                    "created_at DATETIME",
                ]
                bud_src = (
                    "id", "scope", "company_id", "category_id",
                    "COALESCE(CAST(strftime('%m', period_start) AS INTEGER), 1) AS month",
                    "COALESCE(CAST(strftime('%Y', period_start) AS INTEGER), 2026) AS year",
                    "period_type", "period_start", "period_end",
                    "amount", "0 AS recurring", "created_by", "created_at"
                )
                db.session.execute(sa.text("DROP TABLE IF EXISTS budgets_new"))
                db.session.execute(sa.text(f"CREATE TABLE budgets_new ({', '.join(bud_col_defs)})"))
                db.session.execute(sa.text(f"INSERT INTO budgets_new SELECT {', '.join(bud_src)} FROM budgets"))
                db.session.execute(sa.text("DROP TABLE budgets"))
                db.session.execute(sa.text("ALTER TABLE budgets_new RENAME TO budgets"))
                db.session.commit()

            # Migrate task_templates table: add sub_tasks column
            tbl_names = sa.inspect(db.engine).get_table_names()
            if "task_templates" in tbl_names:
                tt_cols = [c["name"] for c in sa.inspect(db.engine).get_columns("task_templates")]
                if "sub_tasks" not in tt_cols:
                    db.session.execute(sa.text("ALTER TABLE task_templates ADD COLUMN sub_tasks TEXT DEFAULT '[]'"))
                    db.session.commit()

            # Migrate team_task_comments: add parent_id for Q&A replies
            if "team_task_comments" in tbl_names:
                ttc_cols = [c["name"] for c in sa.inspect(db.engine).get_columns("team_task_comments")]
                if "parent_id" not in ttc_cols:
                    db.session.execute(sa.text("ALTER TABLE team_task_comments ADD COLUMN parent_id INTEGER REFERENCES team_task_comments(id)"))
                    db.session.commit()

            # Migrate personal_items: add category and estimated_minutes
            if "personal_items" in tbl_names:
                pi_cols = [c["name"] for c in sa.inspect(db.engine).get_columns("personal_items")]
                if "category" not in pi_cols:
                    db.session.execute(sa.text("ALTER TABLE personal_items ADD COLUMN category VARCHAR(50)"))
                if "estimated_minutes" not in pi_cols:
                    db.session.execute(sa.text("ALTER TABLE personal_items ADD COLUMN estimated_minutes INTEGER"))
                if "category" not in pi_cols or "estimated_minutes" not in pi_cols:
                    db.session.commit()

            # Migrate users: add hidden_widgets and email_notifications
            if "users" in tbl_names:
                u_cols = [c["name"] for c in sa.inspect(db.engine).get_columns("users")]
                if "hidden_widgets" not in u_cols:
                    db.session.execute(sa.text("ALTER TABLE users ADD COLUMN hidden_widgets TEXT DEFAULT ''"))
                if "email_notifications" not in u_cols:
                    db.session.execute(sa.text("ALTER TABLE users ADD COLUMN email_notifications BOOLEAN DEFAULT 0"))
                if "hidden_widgets" not in u_cols or "email_notifications" not in u_cols:
                    db.session.commit()

            # Migrate task_templates: add recurring fields
            if "task_templates" in tbl_names:
                tt_cols = [c["name"] for c in sa.inspect(db.engine).get_columns("task_templates")]
            if "day_of_month" not in tt_cols:
                db.session.execute(sa.text("ALTER TABLE task_templates ADD COLUMN day_of_month INTEGER"))
            if "is_active" not in tt_cols:
                db.session.execute(sa.text("ALTER TABLE task_templates ADD COLUMN is_active BOOLEAN DEFAULT 1"))
            if "last_generated_month" not in tt_cols:
                db.session.execute(sa.text("ALTER TABLE task_templates ADD COLUMN last_generated_month INTEGER"))
            if "last_generated_year" not in tt_cols:
                db.session.execute(sa.text("ALTER TABLE task_templates ADD COLUMN last_generated_year INTEGER"))
            if any(c not in tt_cols for c in ("day_of_month", "is_active", "last_generated_month", "last_generated_year")):
                db.session.commit()

            # Migrate team_tasks: add project_id for Projects feature
            if "team_tasks" in tbl_names:
                tt_cols2 = [c["name"] for c in sa.inspect(db.engine).get_columns("team_tasks")]
                if "project_id" not in tt_cols2:
                    db.session.execute(sa.text("ALTER TABLE team_tasks ADD COLUMN project_id INTEGER REFERENCES projects(id)"))
                    db.session.commit()
                if "archived_at" not in tt_cols2:
                    db.session.execute(sa.text("ALTER TABLE team_tasks ADD COLUMN archived_at DATETIME"))
                    db.session.commit()

            # Write sentinel so migrations only run once
            try:
                with open(migration_flag, "w") as f:
                    f.write("1")
            except OSError:
                pass

        # Late migration for personal_items: add recurrence_rule (runs every startup, safe)
        try:
            import sqlalchemy as sa2
            pi_cols = [c["name"] for c in sa2.inspect(db.engine).get_columns("personal_items")]
            if "recurrence_rule" not in pi_cols:
                db.session.execute(sa2.text("ALTER TABLE personal_items ADD COLUMN recurrence_rule VARCHAR(50)"))
                db.session.commit()
        except Exception:
            pass

        # Seed default Pakistani holidays (fixed date)
        if Holiday.query.count() == 0:
            fixed_holidays = [
                (date(2026, 3, 23), "Pakistan Day", True),
                (date(2026, 5, 1), "Labour Day", True),
                (date(2026, 8, 14), "Independence Day", True),
                (date(2026, 9, 6), "Defence Day", True),
                (date(2026, 12, 25), "Quaid-e-Azam Day", True),
            ]
            for h_date, h_name, recurring in fixed_holidays:
                existing = Holiday.query.filter_by(date=h_date, company_id=None).first()
                if not existing:
                    db.session.add(Holiday(date=h_date, name=h_name, is_recurring=recurring))
            db.session.commit()

        @app.before_request
        def check_maintenance_mode():
            exempt_endpoints = {"static", "auth.login", "auth.logout",
                                "maintenance.enable_maintenance", "maintenance.disable_maintenance"}
            if request.endpoint in exempt_endpoints:
                return None
            if not is_maintenance_mode_on(app):
                return None
            if current_user.is_authenticated and current_user.role == "admin":
                return None

            flag_path = app.config["MAINTENANCE_FLAG_PATH"]
            try:
                with open(flag_path, "r", encoding="utf-8") as f:
                    message = f.read().strip()
            except OSError:
                message = None

            return render_template("errors/maintenance.html", message=message), 503

    # Deterministic avatar color filter
    AVATAR_PALETTE = ['#14181f','#d64545','#d99a2b','#1e9e63','#8b5cf6','#36a2eb']
    def avatar_color(name):
        if not name:
            return AVATAR_PALETTE[0]
        idx = sum(ord(c) for c in name) % len(AVATAR_PALETTE)
        return AVATAR_PALETTE[idx]
    app.add_template_filter(avatar_color)

    @app.context_processor
    def inject_companies():
        active_id = session.get("active_company_id")
        # Updated from Company.query.get() for SQLAlchemy 2.0 compatibility
        active_company_obj = db.session.get(Company, active_id) if active_id else None

        overdue_count = 0
        if active_id:
            invoices = Invoice.query.join(Order).filter(Order.company_id == active_id).all()
            overdue_count = len([inv for inv in invoices if
                                 not inv.is_fully_paid() and not inv.is_cancelled() and inv.days_overdue() > 30])

        unread_notifs = 0
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                unread_notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        except Exception:
            pass

        # Auto-detect page_id for AI context
        ep = (request.endpoint or "").split(".")
        if ep and ep[0] in ("home", "dashboard"):
            page_id = "dashboard"
        elif ep and ep[0] == "tasks" and len(ep) > 1:
            page_id = ep[1]
            if page_id in ("my_space",):
                page_id = "tasks/mine"
        elif ep and ep[0] == "projects":
            page_id = "projects"
        elif ep and ep[0] == "orders":
            page_id = "orders"
        elif ep and ep[0] in ("clients", "companies"):
            page_id = ep[0]
        elif ep and ep[0] in ("invoices", "quotations", "challans"):
            page_id = "documents"
        elif ep and ep[0] in ("expenses", "accounts"):
            page_id = "accounts"
        elif ep and ep[0] == "hr":
            page_id = "hr"
        elif ep and ep[0] == "catalog":
            page_id = "catalog"
        elif ep and ep[0] in ("reports", "search"):
            page_id = ep[0]
        else:
            page_id = "general"

        now_local = datetime.now(zoneinfo.ZoneInfo("Asia/Karachi"))
        today_line = now_local.strftime("%A, %b %d")

        section_meta = {
            "companies": (url_for("companies.list_companies"), "Companies"),
            "clients": (url_for("clients.list_clients"), "Clients"),
            "orders": (url_for("orders.list_orders"), "Orders"),
            "quotations": (url_for("quotations.list_quotations"), "Quotations"),
            "invoices": (url_for("invoices.list_invoices"), "Invoices"),
            "challans": (url_for("challans.list_challans"), "Challans"),
            "company_documents": (url_for("company_documents.list_documents"), "Documents"),
            "tasks": (url_for("tasks.my_space"), "Tasks"),
            "accounts": (url_for("accounts.dashboard"), "Accounts"),
            "hr": (url_for("hr.dashboard"), "HR"),
            "catalog": (url_for("catalog.list_catalog"), "Catalog"),
            "reports": (url_for("reports.list_reports"), "Reports"),
            "search": (url_for("search.global_search"), "Search"),
            "settings": (url_for("settings.view_settings"), "Settings"),
            "auth": (url_for("auth.profile"), "Account"),
            "expenses": (url_for("expenses.list_expenses"), "Expenses"),
            "payments": (url_for("payments.list_payments"), "Payments"),
            "projects": (url_for("projects.list_projects"), "Projects"),
        }

        return {
            "all_companies": Company.query.all(),
            "active_company_obj": active_company_obj,
            "overdue_count": overdue_count,
            "maintenance_mode_on": is_maintenance_mode_on(app),
            "unread_notifications": unread_notifs,
            "page_id": page_id,
            "today_line": today_line,
            "section_meta": section_meta,
        }

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error(f"Server Error: {error}")
        return render_template("errors/500.html"), 500

    @app.route("/")
    @login_required
    def home():
        # Get today's date as a string (e.g., "2026-07-23")
        today_str = date.today().isoformat()

        # Read the cookie tracking the last daily visit
        last_visit = request.cookies.get('last_daily_visit')

        # Show the splash only if the cookie doesn't match today's date
        show_splash = (last_visit != today_str)

        # Employee dashboard for employee-role users
        if current_user.role == "employee" and current_user.employee:
            emp = current_user.employee
            today = date.today()
            today_rec = AttendanceRecord.query.filter_by(employee_id=emp.id, date=today).first()
            present_count = AttendanceRecord.query.filter_by(employee_id=emp.id, status="present").filter(
                extract("month", AttendanceRecord.date) == today.month,
                extract("year", AttendanceRecord.date) == today.year,
            ).count()
            total_marked = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
                extract("month", AttendanceRecord.date) == today.month,
                extract("year", AttendanceRecord.date) == today.year,
            ).count()
            attn_pct = round((present_count / total_marked * 100)) if total_marked else 0
            _, days_in_month = monthrange(today.year, today.month)
            month_start = date(today.year, today.month, 1)
            first_weekday_padding = (month_start.weekday() + 6) % 7
            records = AttendanceRecord.query.filter_by(employee_id=emp.id).filter(
                extract("month", AttendanceRecord.date) == today.month,
                extract("year", AttendanceRecord.date) == today.year,
            ).all()
            calendar = {r.date.day: r.status for r in records}
            open_tasks = TeamTask.query.filter_by(assignee_id=emp.id).filter(
                TeamTask.status.in_(["to_do", "in_progress"])
            ).order_by(TeamTask.due_date.asc(), TeamTask.created_at.desc()).all()
            pending_tasks = len(open_tasks)
            upcoming_holidays = Holiday.query.filter(Holiday.date >= today).order_by(Holiday.date).limit(5).all()
            month_names = ["January","February","March","April","May","June","July","August","September","October","November","December"]
            return render_template("employee_dashboard.html",
                emp=emp, today_rec=today_rec, present_count=present_count,
                total_marked=total_marked, attn_pct=attn_pct,
                days_in_month=days_in_month, first_weekday_padding=first_weekday_padding,
                calendar=calendar, today_day=today.day, year=today.year,
                month_name=month_names[today.month - 1], tasks=open_tasks,
                pending_tasks=pending_tasks, upcoming_holidays=upcoming_holidays,
                attendance_allowed=True, show_splash=show_splash,
            )

        company_id = session.get("active_company_id")
        # Updated from Company.query.get() for SQLAlchemy 2.0 compatibility
        active_company = db.session.get(Company, company_id) if company_id else None

        # --- Date / period filter (drives KPIs, charts and comparison badges) ---
        today = date.today()
        range_mode = request.args.get("range", "ytd")  # ytd | all | custom
        period = request.args.get("period", "monthly")  # daily | monthly | yearly
        if period not in ("daily", "monthly", "yearly"):
            period = "monthly"

        def _parse_date(raw):
            if not raw:
                return None
            try:
                return datetime.strptime(raw, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None

        date_from = date_to = None
        if range_mode == "all":
            date_from = date_to = None
        else:
            date_from = _parse_date(request.args.get("from")) or date(today.year, 1, 1)
            date_to = _parse_date(request.args.get("to")) or today

        compare = request.args.get("compare", "1") == "1"

        # Prior window = same length immediately before the selected range
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from
        prior_from = prior_to = None
        if date_from and date_to:
            span = (date_to - date_from).days + 1
            prior_from = date_from - timedelta(days=span)
            prior_to = date_from - timedelta(days=1)

        users = User.query.all()

        stats = {
            "total_expenses": 0,
            "estimated_profit": 0,
            "total_companies": Company.query.count(),
            "total_orders": 0,
            "total_invoiced": 0,
            "outstanding": 0,
            "win_rate": None,
            "won_count": 0,
            "not_received_count": 0,
            "pending_count": 0,
            "po_pending": 0,
            "po_received": 0,
            "po_delivered": 0,
            "po_partially_delivered": 0,
            "po_cancelled": 0,
            "po_none": 0,
        }
        recent_orders = []
        chart_labels = []
        chart_revenue = []
        todos = []
        warnings = []
        overdue_invoices = []
        pending = []
        no_quotation_orders = []
        actions = []
        doc_pipeline = {"quotes": 0, "unpaid": 0, "unpaid_value": 0.0, "overdue": 0, "challans": 0}
        deltas = {"revenue": None, "receivables": None, "expenses": None, "profit": None, "orders": None}
        insight_items = []

        if company_id:
            orders = Order.query.options(selectinload(Order.quotations)).filter_by(company_id=company_id).all()
            stats["total_orders"] = len(orders)
            won = [o for o in orders if o.status == "PO Received"]
            not_received = [o for o in orders if o.status == "Not Received"]
            pending = [o for o in orders if o.status == "Pending"]
            stats["won_count"] = len(won)
            stats["not_received_count"] = len(not_received)
            stats["pending_count"] = len(pending)
            decided = len(won) + len(not_received)
            stats["win_rate"] = round((len(won) / decided) * 100, 1) if decided > 0 else None

            def _po_in_range(po, frm, to):
                return po.po_date and (frm is None or po.po_date >= frm) and (to is None or po.po_date <= to)

            def _exp_in_range(exp, frm, to):
                d = exp.expense_date or exp.created_at.date() if exp.created_at else exp.expense_date
                if d is None:
                    return True
                return (frm is None or d >= frm) and (to is None or d <= to)

            # PO-based revenue: sum of line items from received POs in date range
            pos = PurchaseOrder.query.join(Order).filter(
                Order.company_id == company_id,
                PurchaseOrder.status.in_(["Received", "Delivered", "Partially Delivered"])
            ).all()
            in_range_pos = [po for po in pos if _po_in_range(po, date_from, date_to)]
            stats["total_invoiced"] = sum(po.total_amount for po in in_range_pos)
            stats["outstanding"] = 0  # No invoice outstanding tracking for now

            # PO status counts for pie chart
            _status_key_map = {
                "Pending": "po_pending",
                "Received": "po_received",
                "Delivered": "po_delivered",
                "Partially Delivered": "po_partially_delivered",
                "Cancelled": "po_cancelled",
            }
            for order in orders:
                order_date = order.created_at.date() if order.created_at else None
                in_range = order_date and (date_from is None or order_date >= date_from) and (date_to is None or order_date <= date_to)
                if not in_range:
                    continue
                po = order.purchase_order
                if po:
                    key = _status_key_map.get(po.status)
                    if key:
                        stats[key] += 1
                else:
                    stats["po_none"] += 1

            expenses = Expense.query.filter_by(company_id=company_id).all()
            in_range_exp = [e for e in expenses if _exp_in_range(e, date_from, date_to)]
            stats["total_expenses"] = sum(e.amount for e in in_range_exp)
            stats["estimated_profit"] = stats["total_invoiced"] - stats["total_expenses"]

            # --- Prior-period deltas for comparison badges ---
            deltas = {
                "revenue": None, "receivables": None, "expenses": None, "profit": None,
                "orders": None,
            }
            if compare and prior_from is not None:
                prior_rev = sum(po.total_amount for po in pos if _po_in_range(po, prior_from, prior_to))
                prior_exp = sum(e.amount for e in expenses if _exp_in_range(e, prior_from, prior_to))
                prior_profit = prior_rev - prior_exp
                prior_orders = sum(1 for o in orders if o.created_at.date() and prior_from <= o.created_at.date() <= prior_to) if orders else 0

                def _pct(cur, prev):
                    if not prev:
                        return None
                    return round((cur - prev) / prev * 100, 1)

                deltas["revenue"] = _pct(stats["total_invoiced"], prior_rev)
                deltas["receivables"] = None
                deltas["expenses"] = _pct(stats["total_expenses"], prior_exp)
                deltas["profit"] = _pct(stats["estimated_profit"], prior_profit)
                if prior_orders:
                    deltas["orders"] = _pct(stats["total_orders"], prior_orders)
            else:
                deltas = {k: None for k in deltas}

            recent_orders = sorted(orders, key=lambda o: o.created_at, reverse=True)[:5]

            # --- Chart bucketing by period granularity ---
            chart_labels, chart_revenue = [], []
            if date_from is None:
                dated = [po for po in pos if po.po_date]
                if dated:
                    c_start = min(po.po_date for po in dated)
                    c_end = max(po.po_date for po in dated)
                else:
                    c_start = c_end = today
            else:
                c_start, c_end = date_from, date_to

            if period == "daily":
                cur = c_start
                while cur <= c_end and len(chart_labels) <= 120:
                    chart_labels.append(cur.strftime("%b %d"))
                    chart_revenue.append(round(sum(po.total_amount for po in in_range_pos if po.po_date == cur), 2))
                    cur += timedelta(days=1)
            elif period == "yearly":
                for yy in range(c_start.year, c_end.year + 1):
                    chart_labels.append(str(yy))
                    chart_revenue.append(round(sum(po.total_amount for po in in_range_pos if po.po_date and po.po_date.year == yy), 2))
            else:  # monthly
                cur = date(c_start.year, c_start.month, 1)
                end = date(c_end.year, c_end.month, 1)
                while cur <= end and len(chart_labels) <= 120:
                    chart_labels.append(cur.strftime("%b %Y"))
                    chart_revenue.append(round(sum(po.total_amount for po in in_range_pos if po.po_date and po.po_date.year == cur.year and po.po_date.month == cur.month), 2))
                    if cur.month == 12:
                        cur = date(cur.year + 1, 1, 1)
                    else:
                        cur = date(cur.year, cur.month + 1, 1)

            priority_order = db.case(
                (Todo.priority == "high", 0), (Todo.priority == "medium", 1), (Todo.priority == "low", 2), else_=1
            )
            todos = Todo.query.filter_by(company_id=company_id).order_by(Todo.is_done.asc(), priority_order,
                                                                         Todo.due_date.is_(None),
                                                                         Todo.due_date.asc()).all()
            if pending:
                warnings.append({"text": f"{len(pending)} order(s) still awaiting PO",
                                 "link": url_for("orders.list_orders", status="Pending"), "critical": False})
            no_quotation_orders = [o for o in orders if o.status == "Pending" and not o.quotation]
            if no_quotation_orders:
                warnings.append({"text": f"{len(no_quotation_orders)} order(s) have no quotation yet",
                                 "link": url_for("orders.list_orders", status="Pending"), "critical": False})

            # --- Document pipeline (works-in-progress / "what's outstanding now") ---
            active_quotes = Quotation.query.join(Order).filter(
                Order.company_id == company_id, Quotation.is_current.is_(True)).all()
            doc_pipeline["quotes"] = sum(
                1 for q in active_quotes if q.order and q.order.status in ("Pending", "Not Received"))
            active_challans = DeliveryChallan.query.join(Order).filter(
                Order.company_id == company_id, DeliveryChallan.is_current.is_(True)).all()
            doc_pipeline["challans"] = sum(1 for c in active_challans if not c.dispatch_date)

            # --- Dynamic Insights feed (rotates in the gradient card) ---
            def _insight_currency(v):
                try:
                    v = float(v or 0)
                except (ValueError, TypeError):
                    return "0"
                return f"{v / 1000000:,.2f}M" if v >= 1000000 else f"{v:,.0f}"

            win_rate = stats.get("win_rate")
            insight_items = [{
                "icon": "bi-graph-up-arrow", "tag": "Win Rate",
                "value": f"{win_rate}%" if win_rate is not None else "—",
                "title": "Order Win Rate",
                "body": f"You have secured {stats.get('won_count', 0)} of "
                        f"{stats.get('won_count', 0) + stats.get('not_received_count', 0)} decided orders in this period."
                        if win_rate is not None else
                        "Win rate appears once orders are marked won or lost.",
                "bar": win_rate if win_rate is not None else 0,
            }, {
                "icon": "bi-cash-stack", "tag": "Cash Flow",
                "value": _insight_currency(doc_pipeline.get("unpaid_value", 0)),
                "title": "Unpaid Invoices Outstanding",
                "body": f"{doc_pipeline.get('unpaid', 0)} unpaid invoice(s) still in the pipeline waiting to be collected.",
                "bar": 40 if doc_pipeline.get("unpaid", 0) > 0 else 0,
            }, {
                "icon": "bi-funnel", "tag": "Pipeline",
                "value": str(doc_pipeline.get("quotes", 0)),
                "title": "Quotes Still in Play",
                "body": f"{doc_pipeline.get('quotes', 0)} quotation(s) awaiting a decision. A quick follow-up can close the deal.",
                "bar": 50 if doc_pipeline.get("quotes", 0) > 0 else 0,
            }, {
                "icon": "bi-cash-coin", "tag": "Profit",
                "value": _insight_currency(stats.get("estimated_profit", 0)),
                "title": "Estimated Profit",
                "body": "Invoiced revenue minus recorded expenses for the selected period.",
                "bar": 75 if stats.get("estimated_profit", 0) > 0 else 0,
            }, {
                "icon": "bi-lightbulb", "tag": "Tip",
                "value": "TIP",
                "title": "Remind before due dates",
                "body": "A gentle reminder a few days before an invoice is due cuts overdue balances dramatically.",
                "bar": 0,
            }, {
                "icon": "bi-newspaper", "tag": "News",
                "value": "NEWS",
                "title": "Business Market Watch",
                "body": "Ordering materials early protects delivery commitments as supplier lead times stretch.",
                "bar": 0,
            }]

        # --- Personal dashboard tasks (wired to the Tasks tab) ---
        my_team_tasks = []
        emp = current_user.employee if hasattr(current_user, "employee") else None
        if emp:
            my_team_tasks = TeamTask.query.filter(
                TeamTask.assignee_id == emp.id,
                TeamTask.archived_at.is_(None),
                TeamTask.status.in_(["to_do", "in_progress"]),
            ).order_by(TeamTask.due_date.is_(None), TeamTask.due_date.asc(), TeamTask.created_at.desc()).limit(6).all()

        my_personal_todos = PersonalItem.query.filter(
            PersonalItem.user_id == current_user.id,
            PersonalItem.lane == "task",
            PersonalItem.status != "done",
        ).order_by(PersonalItem.due_date.is_(None), PersonalItem.due_date.asc(),
                   PersonalItem.created_at.desc()).limit(8).all()

        task_overdue_count = sum(1 for t in my_team_tasks if t.due_date and t.due_date < date.today())
        task_due_today_count = sum(1 for t in my_team_tasks if t.due_date and t.due_date == date.today())

        # --- Hero: Important Actions queue + greeting ---
        greeting_hour = datetime.now(zoneinfo.ZoneInfo("Asia/Karachi")).hour
        if greeting_hour < 12:
            greeting = "Morning"
        elif greeting_hour < 17:
            greeting = "Afternoon"
        else:
            greeting = "Evening"
        first_name = (current_user.name or "").strip().split(" ")[0] or "there"

        if company_id:
            snooze_rows = ActionSnooze.query.filter(
                ActionSnooze.company_id == company_id,
                ActionSnooze.snoozed_until > datetime.utcnow(),
            ).all()
            snooze_keys = {(s.source, s.source_id) for s in snooze_rows}
            actions = build_actions(
                company_id=company_id,
                overdue_invoices=overdue_invoices,
                pending=pending,
                no_quotation_orders=no_quotation_orders,
                team_tasks=my_team_tasks,
                snooze_keys=snooze_keys,
            )

        # Render template using make_response so we can attach the daily cookie
        resp = make_response(render_template(
            "dashboard.html", stats=stats, recent_orders=recent_orders,
            chart_labels=chart_labels, chart_revenue=chart_revenue,
            active_company=active_company, todos=todos,
            users=users, show_splash=show_splash, doc_pipeline=doc_pipeline,
            hidden_widgets=(current_user.hidden_widgets or "").split(","),
            date_from=date_from, date_to=date_to, period=period, deltas=deltas,
            compare=compare, my_team_tasks=my_team_tasks, my_personal_todos=my_personal_todos,
            insight_items=insight_items, actions=actions,
            greeting=greeting, first_name=first_name,
            task_overdue_count=task_overdue_count, task_due_today_count=task_due_today_count,
        ))

        # If it's a new day, update the cookie so it won't show again until tomorrow
        if show_splash:
            resp.set_cookie('last_daily_visit', today_str, max_age=60 * 60 * 24 * 365, httponly=True, samesite='Lax')

        return resp

    @app.route("/dashboard/actions/dismiss", methods=["POST"])
    @login_required
    def dismiss_action():
        company_id = session.get("active_company_id")
        if not company_id:
            return jsonify({"ok": False, "error": "No active company"}), 400
        source = (request.form.get("source") or "").strip()
        if not source:
            return jsonify({"ok": False, "error": "Missing source"}), 400
        try:
            source_id = int(request.form.get("source_id")) if request.form.get("source_id") else None
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Bad source_id"}), 400
        try:
            hours = float(request.form.get("snooze_hours", DEFAULT_SNOOZE_HOURS))
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
        return jsonify({"ok": True})

    @app.route("/dashboard/actions/restore", methods=["POST"])
    @login_required
    def restore_action():
        company_id = session.get("active_company_id")
        source = (request.form.get("source") or "").strip()
        if not company_id or not source:
            return jsonify({"ok": False, "error": "Missing params"}), 400
        try:
            source_id = int(request.form.get("source_id")) if request.form.get("source_id") else None
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Bad source_id"}), 400
        ActionSnooze.query.filter_by(
            company_id=company_id, source=source, source_id=source_id).delete()
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/admin/backup-now")
    @login_required
    @admin_required
    def backup_now():
        from backup_database import run_backup
        run_backup()
        flash("Database backup created.")
        # Notify the current user about backup
        if current_user.is_authenticated:
            Notification.send(current_user.id, "Database backup created successfully",
                              url_for("home"))
        return redirect(url_for("home"))

    # --- DASHBOARD WIDGET PREFERENCES ---
    @app.route('/dashboard/toggle-widget', methods=['POST'])
    @login_required
    def toggle_widget():
        widget = request.form.get("widget", "")
        hidden = request.form.get("hidden") == "true"
        if not widget:
            return jsonify({"ok": False, "error": "Missing widget key"}), 400
        keys = set(current_user.hidden_widgets.split(",")) if current_user.hidden_widgets else set()
        if hidden:
            keys.add(widget)
        else:
            keys.discard(widget)
        keys.discard("")
        current_user.hidden_widgets = ",".join(sorted(keys))
        db.session.commit()
        return jsonify({"ok": True})

    # --- EXTRACTION ROUTES ---
    @app.route('/quotations/extract-local', methods=['POST'])
    @login_required
    def extract_local():
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file uploaded'}), 400
        if file.content_length and file.content_length > 50 * 1024 * 1024:
            return jsonify({'error': 'File exceeds 50MB limit'}), 413

        items = extract_items_from_file(file.stream, filename=file.filename, force_ai=False)
        return jsonify({'items': items})

    @app.route('/quotations/extract-with-groq', methods=['POST'])
    @login_required
    def extract_with_groq():
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file uploaded'}), 400
        if file.content_length and file.content_length > 50 * 1024 * 1024:
            return jsonify({'error': 'File exceeds 50MB limit'}), 413

        items = extract_items_from_file(file.stream, filename=file.filename, force_ai=True)
        return jsonify({'items': items})

    @app.route('/debug/clear-splash')
    @login_required
    def debug_clear_splash():
        resp = make_response(redirect(url_for('home')))
        resp.delete_cookie('last_daily_visit')
        return resp

    return app


app = create_app()

if __name__ == '__main__':
    debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() in ("1", "true", "yes")
    app.run(debug=debug_mode, port=5003)