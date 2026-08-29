import json
from datetime import datetime
from flask import Blueprint, redirect, url_for, session, flash, request, render_template, jsonify, current_app
from flask_login import login_required, current_user
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from models import db, GmailToken, Client, ClientCompanyLink, MailConfig
from gmail_utils import encrypt_token, decrypt_token, get_client_emails, get_single_message, is_connected
from audit import log_action

gmail_bp = Blueprint("gmail", __name__, url_prefix="/gmail")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_oauth_flow():
    from gmail_utils import get_google_oauth_credentials
    client_id, client_secret = get_google_oauth_credentials()
    if not client_id or not client_secret:
        client_id = current_app.config.get("GOOGLE_CLIENT_ID")
        client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        redirect_uri = url_for("gmail.oauth_callback", _external=True)

    return Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def _get_redirect_uri():
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI")
    if not redirect_uri:
        redirect_uri = url_for("gmail.oauth_callback", _external=True)
    return redirect_uri


@gmail_bp.route("/connect")
@login_required
def connect():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select a company workspace first.")
        return redirect(url_for("home"))

    flow = _get_oauth_flow()
    if not flow:
        flash("Google OAuth is not configured. Set credentials in Settings > Mail & Gmail.")
        return redirect(url_for("gmail.inbox"))

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=str(company_id),
    )
    session["gmail_oauth_state"] = state
    return redirect(authorization_url)


@gmail_bp.route("/callback")
@login_required
def oauth_callback():
    state_from_session = session.pop("gmail_oauth_state", None)
    state_from_url = request.args.get("state")

    if not state_from_url:
        flash("OAuth callback missing state parameter. Try again.")
        return redirect(url_for("gmail.inbox"))

    if state_from_session and state_from_session != state_from_url:
        flash("OAuth state mismatch — possible CSRF. Try again.")
        return redirect(url_for("gmail.inbox"))

    company_id = int(state_from_url) if state_from_url.isdigit() else None
    if not company_id:
        flash("Invalid OAuth state. Try again.")
        return redirect(url_for("gmail.inbox"))

    error = request.args.get("error")
    if error:
        flash(f"Google authorization failed: {error}")
        return redirect(url_for("gmail.inbox"))

    flow = _get_oauth_flow()
    if not flow:
        flash("Google OAuth is not configured.")
        return redirect(url_for("gmail.inbox"))

    # Reconstruct the full callback URL using the configured redirect_uri
    # so oauthlib sees HTTPS (the tunnel) instead of the local HTTP request.
    redirect_uri = _get_redirect_uri()
    callback_url = redirect_uri + "?" + request.query_string.decode("utf-8")

    flow.fetch_token(authorization_response=callback_url)
    creds = flow.credentials

    existing = GmailToken.query.filter_by(company_id=company_id).first()
    if existing:
        existing.access_token = encrypt_token(creds.token)
        existing.refresh_token = encrypt_token(creds.refresh_token) if creds.refresh_token else existing.refresh_token
        existing.expiry = creds.expiry
        existing.scopes = json.dumps(list(creds.scopes or SCOPES))
        existing.client_id = current_app.config.get("GOOGLE_CLIENT_ID", "")
        existing.client_secret = current_app.config.get("GOOGLE_CLIENT_SECRET", "")
    else:
        from gmail_utils import get_google_oauth_credentials
        cid, csec = get_google_oauth_credentials()
        if not cid or not csec:
            cid = current_app.config.get("GOOGLE_CLIENT_ID", "")
            csec = current_app.config.get("GOOGLE_CLIENT_SECRET", "")
        token = GmailToken(
            company_id=company_id,
            connected_by=current_user.id,
            access_token=encrypt_token(creds.token),
            refresh_token=encrypt_token(creds.refresh_token),
            client_id=cid,
            client_secret=csec,
            scopes=json.dumps(list(creds.scopes or SCOPES)),
            expiry=creds.expiry,
        )
        db.session.add(token)

    db.session.commit()
    log_action("connect_gmail", "GmailToken", company_id, f"Connected Gmail for company {company_id}")
    flash("Gmail connected successfully.")
    return redirect(url_for("gmail.inbox"))


@gmail_bp.route("/disconnect")
@login_required
def disconnect():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select a company workspace first.")
        return redirect(url_for("home"))

    token = GmailToken.query.filter_by(company_id=company_id).first()
    if token:
        # Try to revoke at Google
        try:
            import requests as req
            req.post("https://oauth2.googleapis.com/revoke",
                params={"token": decrypt_token(token.refresh_token)},
                headers={"Content-Type": "application/x-www-form-urlencoded"})
        except Exception:
            pass
        db.session.delete(token)
        db.session.commit()
        log_action("disconnect_gmail", "GmailToken", company_id, f"Disconnected Gmail for company {company_id}")
        flash("Gmail disconnected.")
    return redirect(url_for("gmail.inbox"))


@gmail_bp.route("/inbox")
@login_required
def inbox():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select a company workspace first.")
        return redirect(url_for("home"))

    connected = is_connected(company_id)
    emails = []
    if connected:
        emails = get_client_emails(company_id)

    return render_template("gmail/inbox.html",
        connected=connected, emails=emails, company_id=company_id)


@gmail_bp.route("/api/inbox")
@login_required
def api_inbox():
    company_id = session.get("active_company_id")
    if not company_id:
        return jsonify({"connected": False, "emails": []})

    connected = is_connected(company_id)
    if not connected:
        return jsonify({"connected": False, "emails": []})

    emails = get_client_emails(company_id)
    return jsonify({"connected": True, "emails": emails[:10]})


@gmail_bp.route("/api/message/<msg_id>")
@login_required
def api_message(msg_id):
    company_id = session.get("active_company_id")
    if not company_id:
        return jsonify({"error": "No company selected"}), 400

    msg = get_single_message(company_id, msg_id)
    if not msg:
        return jsonify({"error": "Message not found"}), 404
    return jsonify(msg)
