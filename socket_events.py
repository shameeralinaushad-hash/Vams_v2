"""
Live update helpers for VAMS.
Push SSE events to connected clients via sse.push_event().
"""
import sse


def emit_company(event, data, company_id):
    """Push a refresh event so SSE clients reload their list."""
    sse.push_event(company_id, "refresh", data)


def emit_user(event, data, user_id):
    pass


def emit_dashboard_update(company_id):
    """Push a refresh event so SSE clients reload the dashboard."""
    sse.push_event(company_id, "refresh", {"section": "dashboard"})


def emit_notification_update(user_id, count=0, company_id=None):
    """Push notification count to all clients in the user's company.

    If company_id is provided (caller already knows it), skip the DB query.
    """
    if not company_id:
        from models import User, db
        user = db.session.get(User, user_id)
        if user:
            company_id = None
            if user.employee:
                company_id = user.employee.company_id
            if not company_id:
                from flask import session
                company_id = session.get("active_company_id")
    if company_id:
        sse.push_event(company_id, "notification", {"count": count})


def emit_toast(message, type_="info", user_id=None):
    pass
