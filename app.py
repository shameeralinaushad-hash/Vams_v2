import os
import time
import logging
import zoneinfo
from calendar import monthrange
from datetime import datetime, date, timedelta, timezone
from logging.handlers import RotatingFileHandler

from flask import (
    Flask, render_template, session, redirect, url_for,
    flash, send_from_directory, jsonify, request, make_response,
    Response, stream_with_context, g
)
from flask_login import LoginManager, login_required, current_user
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from flask_caching import Cache
from flask_compress import Compress
from dotenv import load_dotenv
from sqlalchemy import extract
from sqlalchemy.orm import selectinload

from config import Config
from models import db, Company, User, Order, Invoice, Todo, Expense, ExpenseCategory, Employee, AttendanceRecord, PayrollRecord, Holiday, Notification, TeamTask, Quotation, DeliveryChallan, PersonalItem, ActionSnooze, PurchaseOrder, PurchaseOrderLineItem
from important_actions import build_actions, DEFAULT_SNOOZE_HOURS
from rate_limiter import limiter

load_dotenv()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # --- Rate Limiter (from shared module) ---
    limiter.init_app(app)

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

    # ---- Logging setup (production: INFO only, no DEBUG) ----
    log_dir = os.path.join(app.root_path, "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=1024 * 1024 * 5, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)  # Reduced from DEBUG to INFO
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    app.logger.addHandler(console)
    app.logger.setLevel(logging.INFO)  # Reduced from DEBUG to INFO

    for logger_name in ("werkzeug",):
        l = logging.getLogger(logger_name)
        l.setLevel(logging.WARNING)  # Reduced from DEBUG to WARNING
        l.addHandler(console)

    if not app.debug:
        app.jinja_env.auto_reload = False

    db.init_app(app)
    migrate = Migrate(app, db)
    csrf = CSRFProtect(app)

    # --- Cache (SimpleCache — per-worker in-memory; works well with 4 workers) ---
    cache = Cache(app, config={
        "CACHE_TYPE": "SimpleCache",
        "CACHE_DEFAULT_TIMEOUT": 300,  # 5 minutes
    })
    app.cache = cache

    # --- Gzip/Brotli compression (60-80% reduction on HTML/CSS/JS) ---
    Compress(app)

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
    from routes.gmail import gmail_bp
    from routes.app_update import app_update_bp
    from routes.api_auth import api_auth_bp, init_jwt
    from routes.api_orders import api_orders_bp
    from routes.api_clients import api_clients_bp
    from routes.api_invoices import api_invoices_bp
    from routes.api_dashboard import api_dashboard_bp
    from routes.api_quotations import api_quotations_bp
    from routes.api_challans import api_challans_bp
    from routes.api_notifications import api_notifications_bp
    from routes.api_tasks import api_tasks_bp
    from routes.api_hr import api_hr_bp
    from routes.api_accounts import api_accounts_bp
    from routes.api_companies import api_companies_bp
    from routes.api_catalog import api_catalog_bp
    from routes.api_projects import api_projects_bp
    from routes.api_todos import api_todos_bp
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
    app.register_blueprint(gmail_bp)
    app.register_blueprint(app_update_bp)
    app.register_blueprint(api_auth_bp)
    app.register_blueprint(api_orders_bp)
    app.register_blueprint(api_clients_bp)
    app.register_blueprint(api_invoices_bp)
    app.register_blueprint(api_dashboard_bp)
    app.register_blueprint(api_quotations_bp)
    app.register_blueprint(api_challans_bp)
    app.register_blueprint(api_notifications_bp)
    app.register_blueprint(api_tasks_bp)
    app.register_blueprint(api_hr_bp)
    app.register_blueprint(api_accounts_bp)
    app.register_blueprint(api_companies_bp)
    app.register_blueprint(api_catalog_bp)
    app.register_blueprint(api_projects_bp)
    app.register_blueprint(api_todos_bp)
    # Exempt API blueprints from CSRF — mobile app uses JWT, not cookies
    csrf.exempt(api_auth_bp)
    csrf.exempt(api_orders_bp)
    csrf.exempt(api_clients_bp)
    csrf.exempt(api_invoices_bp)
    csrf.exempt(api_dashboard_bp)
    csrf.exempt(api_quotations_bp)
    csrf.exempt(api_challans_bp)
    csrf.exempt(api_notifications_bp)
    csrf.exempt(api_tasks_bp)
    csrf.exempt(api_hr_bp)
    csrf.exempt(api_accounts_bp)
    csrf.exempt(api_companies_bp)
    csrf.exempt(api_catalog_bp)
    csrf.exempt(api_projects_bp)
    csrf.exempt(api_todos_bp)
    init_jwt(app)

    @app.before_request
    def log_request():
        g.start_time = time.time()
        # Removed per-request INFO log — too noisy in production

    @app.after_request
    def log_response(response):
        elapsed_ms = (time.time() - getattr(g, 'start_time', time.time())) * 1000
        if elapsed_ms > 500:
            app.logger.warning(f"SLOW: {request.method} {request.path} -> {response.status_code} [{elapsed_ms:.0f}ms]")
        return response
        return response

    @app.before_request
    def require_login():
        allowed_endpoints = {
            "auth.login", "static",
            "hr.qr_landing", "hr.qr_scan",
            "app_update.get_app_version", "app_update.download_page", "app_update.download_file", "app_update.download_qr",
            "api_auth.api_login", "api_auth.api_refresh", "api_auth.api_me",
            "api_auth.api_select_company",
        }
        if request.endpoint and request.endpoint not in allowed_endpoints and not current_user.is_authenticated:
            # Skip session auth for API endpoints — they use JWT via @jwt_required
            if request.endpoint and request.endpoint.startswith("api_"):
                return
            return redirect(url_for("auth.login", next=request.path))

    with app.app_context():
        # Defer heavy startup work (db.create_all, migrations) to first request
        # This speeds up cold starts behind Cloudflare Tunnel
        _db_initialized = False

        @app.before_request
        def _init_db_on_first_request():
            nonlocal _db_initialized
            if _db_initialized:
                return None
            _db_initialized = True
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
        # Skip heavy queries for API endpoints (they use JWT, not templates)
        if request.endpoint and request.endpoint.startswith("api_"):
            return {
                "all_companies": [],
                "active_company_obj": None,
                "overdue_count": 0,
                "maintenance_mode_on": False,
                "unread_notifications": 0,
                "page_id": "api",
                "today_line": "",
                "section_meta": {},
                "gmail_connected": False,
            }

        # Use cached queries (keyed by company_id) to avoid repeated DB hits
        cache_key = f"ctx_{active_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Updated from Company.query.get() for SQLAlchemy 2.0 compatibility
        active_company_obj = db.session.get(Company, active_id) if active_id else None

        overdue_count = 0
        if active_id:
            from sqlalchemy import and_
            overdue_count = db.session.query(db.func.count(Invoice.id)).join(Order).filter(
                and_(
                    Order.company_id == active_id,
                    Invoice.is_current.is_(True),
                    Invoice.status != "cancelled",
                    Invoice.invoice_date < date.today(),
                )
            ).scalar() or 0

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

        gmail_connected = False
        if active_id:
            try:
                from gmail_utils import is_connected as gmail_is_connected
                gmail_connected = gmail_is_connected(active_id)
            except Exception:
                pass

        result = {
            "all_companies": Company.query.all(),
            "active_company_obj": active_company_obj,
            "overdue_count": overdue_count,
            "maintenance_mode_on": is_maintenance_mode_on(app),
            "unread_notifications": unread_notifs,
            "page_id": page_id,
            "today_line": today_line,
            "section_meta": section_meta,
            "gmail_connected": gmail_connected,
        }
        cache.set(cache_key, result, timeout=120)  # cache for 2 minutes
        return result

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
            # --- SQL aggregates instead of loading all orders ---
            # Order status counts (single query)
            status_counts = db.session.query(
                Order.status, db.func.count(Order.id)
            ).filter_by(company_id=company_id).group_by(Order.status).all()
            status_map = {s: c for s, c in status_counts}
            stats["total_orders"] = sum(status_map.values())
            stats["won_count"] = status_map.get("PO Received", 0)
            stats["not_received_count"] = status_map.get("Not Received", 0)
            stats["pending_count"] = status_map.get("Pending", 0)
            decided = stats["won_count"] + stats["not_received_count"]
            stats["win_rate"] = round((stats["won_count"] / decided) * 100, 1) if decided > 0 else None

            # PO-based revenue: SQL SUM with date filter
            po_q = db.session.query(db.func.coalesce(db.func.sum(PurchaseOrder.total_amount), 0)).join(Order).filter(
                Order.company_id == company_id,
                PurchaseOrder.status.in_(["Received", "Delivered", "Partially Delivered"])
            )
            if date_from:
                po_q = po_q.filter(PurchaseOrder.po_date >= date_from)
            if date_to:
                po_q = po_q.filter(PurchaseOrder.po_date <= date_to)
            stats["total_invoiced"] = po_q.scalar()
            stats["outstanding"] = 0

            # PO status counts (SQL GROUP BY)
            po_status_counts = db.session.query(
                PurchaseOrder.status, db.func.count(PurchaseOrder.id)
            ).join(Order).filter(
                Order.company_id == company_id
            ).group_by(PurchaseOrder.status).all()
            _status_key_map = {
                "Pending": "po_pending",
                "Received": "po_received",
                "Delivered": "po_delivered",
                "Partially Delivered": "po_partially_delivered",
                "Cancelled": "po_cancelled",
            }
            for status, count in po_status_counts:
                key = _status_key_map.get(status)
                if key:
                    stats[key] = count
            # Count orders with no PO
            stats["po_none"] = db.session.query(db.func.count(Order.id)).filter(
                Order.company_id == company_id,
                ~Order.purchase_orders.any()
            ).scalar()

            # Expenses (already SQL)
            stats["total_expenses"] = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0)).filter(
                Expense.company_id == company_id,
                Expense.expense_date >= date_from if date_from else True,
                Expense.expense_date <= date_to if date_to else True,
            ).scalar()
            stats["estimated_profit"] = stats["total_invoiced"] - stats["total_expenses"]

            # --- Prior-period deltas ---
            deltas = {
                "revenue": None, "receivables": None, "expenses": None, "profit": None,
                "orders": None,
            }
            if compare and prior_from is not None:
                prior_rev = db.session.query(db.func.coalesce(db.func.sum(PurchaseOrder.total_amount), 0)).join(Order).filter(
                    Order.company_id == company_id,
                    PurchaseOrder.status.in_(["Received", "Delivered", "Partially Delivered"]),
                    PurchaseOrder.po_date >= prior_from,
                    PurchaseOrder.po_date <= prior_to,
                ).scalar()
                prior_exp = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0)).filter(
                    Expense.company_id == company_id,
                    Expense.expense_date >= prior_from,
                    Expense.expense_date <= prior_to,
                ).scalar()
                prior_profit = prior_rev - prior_exp
                prior_orders = db.session.query(db.func.count(Order.id)).filter(
                    Order.company_id == company_id,
                    Order.created_at >= datetime.combine(prior_from, datetime.min.time()),
                    Order.created_at <= datetime.combine(prior_to, datetime.max.time()),
                ).scalar() if prior_from and prior_to else 0

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

            # Recent orders (only 5, not all)
            recent_orders = Order.query.filter_by(company_id=company_id).order_by(
                Order.created_at.desc()
            ).limit(5).all()

            # Load pending + no-quotation orders for build_actions (small lists)
            pending = Order.query.filter_by(company_id=company_id, status="Pending").all()
            no_quotation_orders = Order.query.filter(
                Order.company_id == company_id,
                Order.status == "Pending",
                ~Order.quotations.any()
            ).all()

            # --- Chart: SQL GROUP BY for revenue bucketing ---
            chart_labels, chart_revenue = [], []
            po_date_col = PurchaseOrder.po_date
            if period == "daily":
                rows = db.session.query(
                    po_date_col, db.func.sum(PurchaseOrder.total_amount)
                ).join(Order).filter(
                    Order.company_id == company_id,
                    PurchaseOrder.status.in_(["Received", "Delivered", "Partially Delivered"]),
                    po_date_col >= date_from if date_from else True,
                    po_date_col <= date_to if date_to else True,
                ).group_by(po_date_col).order_by(po_date_col).all()
                rev_map = {str(d): float(s) for d, s in rows}
                if date_from and date_to:
                    cur = date_from
                    while cur <= date_to and len(chart_labels) <= 120:
                        chart_labels.append(cur.strftime("%b %d"))
                        chart_revenue.append(round(rev_map.get(str(cur), 0), 2))
                        cur += timedelta(days=1)
            elif period == "yearly":
                year_col = db.func.to_char(po_date_col, "YYYY")
                rows = db.session.query(
                    year_col, db.func.sum(PurchaseOrder.total_amount)
                ).join(Order).filter(
                    Order.company_id == company_id,
                    PurchaseOrder.status.in_(["Received", "Delivered", "Partially Delivered"]),
                    po_date_col >= date_from if date_from else True,
                    po_date_col <= date_to if date_to else True,
                ).group_by(year_col).order_by(year_col).all()
                rev_map = {str(y): float(s) for y, s in rows}
                c_start = date_from or today.replace(month=1, day=1)
                c_end = date_to or today
                for yy in range(c_start.year, c_end.year + 1):
                    chart_labels.append(str(yy))
                    chart_revenue.append(round(rev_map.get(str(yy), 0), 2))
            else:  # monthly
                month_col = db.func.to_char(po_date_col, "YYYY-MM")
                rows = db.session.query(
                    month_col, db.func.sum(PurchaseOrder.total_amount)
                ).join(Order).filter(
                    Order.company_id == company_id,
                    PurchaseOrder.status.in_(["Received", "Delivered", "Partially Delivered"]),
                    po_date_col >= date_from if date_from else True,
                    po_date_col <= date_to if date_to else True,
                ).group_by(month_col).order_by(month_col).all()
                rev_map = {str(m): float(s) for m, s in rows}
                c_start = date_from or today.replace(day=1)
                c_end = date_to or today
                cur = date(c_start.year, c_start.month, 1)
                end = date(c_end.year, c_end.month, 1)
                while cur <= end and len(chart_labels) <= 120:
                    key = cur.strftime("%Y-%m")
                    chart_labels.append(cur.strftime("%b %Y"))
                    chart_revenue.append(round(rev_map.get(key, 0), 2))
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
            if stats["pending_count"]:
                warnings.append({"text": f"{stats['pending_count']} order(s) still awaiting PO",
                                 "link": url_for("orders.list_orders", status="Pending"), "critical": False})
            # Count orders with pending status and no quotation (SQL)
            no_quotation_count = db.session.query(db.func.count(Order.id)).filter(
                Order.company_id == company_id,
                Order.status == "Pending",
                ~Order.quotations.any()
            ).scalar()
            if no_quotation_count:
                warnings.append({"text": f"{no_quotation_count} order(s) have no quotation yet",
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
        client_emails = []
        gmail_connected = False
        if company_id:
            try:
                from gmail_utils import is_connected as gmail_is_connected, get_client_emails
                gmail_connected = gmail_is_connected(company_id)
                if gmail_connected:
                    client_emails = get_client_emails(company_id)[:5]
            except Exception:
                pass

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
            client_emails=client_emails, gmail_connected=gmail_connected,
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

        from ml.tender_extractor import extract_items_from_file
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

        from ml.tender_extractor import extract_items_from_file
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
    if debug_mode:
        print(" * Dev server on http://127.0.0.1:5003")
        app.run(debug=True, port=5003, use_reloader=False)
    else:
        from waitress import serve
        print(" * Serving on http://0.0.0.0:8080")
        serve(app, host="0.0.0.0", port=8080, threads=6, channel_timeout=300)