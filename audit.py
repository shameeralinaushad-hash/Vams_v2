from flask import session
from flask_login import current_user
from models import db, AuditLog


def log_action(action, entity_type, entity_id, details=""):
    """Records an audit trail entry. Call this right before or after the actual change."""
    try:
        user_id = current_user.id if current_user.is_authenticated else None
    except Exception:
        user_id = None

    entry = AuditLog(
        user_id=user_id,
        company_id=session.get("active_company_id"),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.session.add(entry)
    db.session.commit()