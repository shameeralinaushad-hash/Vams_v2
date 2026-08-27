import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]  # fails loudly if .env is missing/misconfigured

    # Postgres in production/dev when DATABASE_URL is set (see .env); falls
    # back to the original SQLite file if it isn't, so nothing breaks if the
    # env var is ever missing on some machine.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'database', 'business.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # cache static files (letterheads, PDFs, etc.) for 1 year

    # Upload paths
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    LETTERHEAD_FOLDER = os.path.join(BASE_DIR, "static", "letterheads")
    CLIENT_LOGO_FOLDER = os.path.join(BASE_DIR, "static", "client_logos")
    COMPANY_LOGO_FOLDER = os.path.join(BASE_DIR, "static", "company_logos")
    SIGNATURE_FOLDER = os.path.join(BASE_DIR, "static", "signatures")
    COMPANY_DOCS_FOLDER = os.path.join(BASE_DIR, "static", "company_documents")
    RECEIPTS_FOLDER = os.path.join(BASE_DIR, "static", "receipts")

    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "100")) * 1024 * 1024  # default 100MB max request body

    MAINTENANCE_FLAG_PATH = os.path.join(BASE_DIR, "database", "maintenance.flag")

    TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")

    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FORCE_HTTPS", "False").lower() in ("1", "true", "yes")
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 hours
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 30  # 30 days
    REMEMBER_COOKIE_SECURE = os.environ.get("FORCE_HTTPS", "False").lower() in ("1", "true", "yes")
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    # Password policy
    MIN_PASSWORD_LENGTH = 8

    # Rate limiting (Flask-Limiter)
    RATELIMIT_ENABLED = True
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_DEFAULT = "120 per minute"
    RATELIMIT_HEADERS_ENABLED = True

    # Cloudflare Turnstile (optional — leave unset to skip)
    TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "")
    TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")

    # Google OAuth (Gmail integration — per-company)
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")