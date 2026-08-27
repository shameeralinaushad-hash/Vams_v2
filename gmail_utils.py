import time
import base64
import json
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from flask import current_app
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from models import db, GmailToken, Client, ClientCompanyLink, User, Notification, MailConfig

# In-memory cache: {company_id: {"emails": [...], "fetched_at": float}}
_email_cache = {}
CACHE_TTL = 300  # 5 minutes


def get_google_oauth_credentials():
    """Get Google OAuth client ID and secret from MailConfig (Settings)."""
    mc = MailConfig.query.first()
    if mc and mc.google_client_id and mc.google_client_secret:
        return mc.google_client_id, mc.google_client_secret
    return None, None


def _get_fernet():
    key = current_app.config["SECRET_KEY"]
    key_bytes = key.encode()[:32].ljust(32, b"=")
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_token(value):
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_token(value):
    return _get_fernet().decrypt(value.encode()).decode()


def build_gmail_service(company_id):
    token_row = GmailToken.query.filter_by(company_id=company_id).first()
    if not token_row:
        return None

    client_id = token_row.client_id
    client_secret = token_row.client_secret
    # Fallback to MailConfig if token row doesn't have credentials
    if not client_id or not client_secret:
        client_id, client_secret = get_google_oauth_credentials()

    creds = Credentials(
        token=decrypt_token(token_row.access_token),
        refresh_token=decrypt_token(token_row.refresh_token),
        token_uri=token_row.token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=json.loads(token_row.scopes) if token_row.scopes else ["https://www.googleapis.com/auth/gmail.readonly"],
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_row.access_token = encrypt_token(creds.token)
            if creds.expiry:
                token_row.expiry = creds.expiry
            db.session.commit()
        except Exception:
            return None

    return build("gmail", "v1", credentials=creds)


def get_client_emails(company_id):
    now = time.time()
    cached = _email_cache.get(company_id)
    if cached and (now - cached["fetched_at"]) < CACHE_TTL:
        return cached["emails"]

    service = build_gmail_service(company_id)
    if not service:
        return []

    # Get all client email addresses for this company's linked clients
    link_ids = [cl.id for cl in ClientCompanyLink.query.filter_by(company_id=company_id).all()]
    if not link_ids:
        return []
    clients = Client.query.filter(Client.company_links.any(ClientCompanyLink.id.in_(link_ids)), Client.email.isnot(None), Client.email != "").all()
    client_emails = {c.email.lower().strip(): c.name for c in clients if c.email}
    if not client_emails:
        return []

    # Build Gmail query: from any client email
    from_clauses = " OR ".join(f"from:{email}" for email in client_emails.keys())
    query = f"({from_clauses}) -label:spam -label:trash"

    try:
        results = service.users().messages().list(userId="me", q=query, maxResults=30).execute()
        messages = results.get("messages", [])
    except Exception:
        return []

    emails = []
    for msg_stub in messages:
        try:
            msg = service.users().messages().get(userId="me", id=msg_stub["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            sender = headers.get("from", "")
            sender_lower = sender.lower()
            # Match client email from sender string
            matched_client = None
            for ce, cname in client_emails.items():
                if ce in sender_lower:
                    matched_client = cname
                    break

            emails.append({
                "id": msg["id"],
                "subject": headers.get("subject", "(no subject)"),
                "from": sender,
                "date": headers.get("date", ""),
                "snippet": msg.get("snippet", ""),
                "labels": msg.get("labelIds", []),
                "unread": "UNREAD" in msg.get("labelIds", []),
                "client_name": matched_client,
            })
        except Exception:
            continue

    # Sort by date descending
    emails.sort(key=lambda e: e["date"], reverse=True)

    # Check for new emails and notify admins
    token_row = GmailToken.query.filter_by(company_id=company_id).first()
    if token_row and emails:
        last_seen = token_row.last_seen_msg_id
        newest_id = emails[0]["id"]
        if last_seen and newest_id != last_seen:
            # Find new emails (those before the last seen in the list)
            new_emails = []
            for e in emails:
                if e["id"] == last_seen:
                    break
                new_emails.append(e)
            if new_emails:
                _notify_new_client_emails(company_id, new_emails)
        # Update last seen
        token_row.last_seen_msg_id = newest_id
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    _email_cache[company_id] = {"emails": emails, "fetched_at": now}
    return emails


def _notify_new_client_emails(company_id, new_emails):
    from flask import url_for
    admins = User.query.filter(User.role == "admin", User.is_active_user == True).all()
    link = url_for("gmail.inbox")
    for admin in admins:
        for e in new_emails[:3]:  # Max 3 notifications per fetch
            client_label = f" from {e['client_name']}" if e["client_name"] else ""
            msg = f"New client email{client_label}: {e['subject']}"
            existing = Notification.query.filter_by(user_id=admin.id, is_read=False, link=link).filter(
                Notification.message.like(f"%{e['subject'][:30]}%")
            ).first()
            if not existing:
                Notification.send(admin.id, msg, link=link)


def get_single_message(company_id, msg_id):
    service = build_gmail_service(company_id)
    if not service:
        return None
    try:
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = _extract_body(msg.get("payload", {}))
        return {
            "id": msg["id"],
            "subject": headers.get("subject", "(no subject)"),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "body": body,
            "labels": msg.get("labelIds", []),
        }
    except Exception:
        return None


def _extract_body(payload):
    """Recursively extract text body from Gmail message payload."""
    import base64 as b64
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return b64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""


def is_connected(company_id):
    return GmailToken.query.filter_by(company_id=company_id).first() is not None
