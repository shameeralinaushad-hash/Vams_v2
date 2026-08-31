from math import ceil
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Notification

api_notifications_bp = Blueprint("api_notifications", __name__)


def _get_user_id():
    return int(get_jwt_identity())


@api_notifications_bp.route("/api/v1/notifications/unread-count", methods=["GET"])
@jwt_required()
def unread_count():
    user_id = _get_user_id()
    count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({"success": True, "unread_count": count})


@api_notifications_bp.route("/api/v1/notifications/read-all", methods=["POST"])
@jwt_required()
def read_all():
    user_id = _get_user_id()
    Notification.query.filter_by(user_id=user_id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"success": True})


@api_notifications_bp.route("/api/v1/notifications/clear-all", methods=["POST"])
@jwt_required()
def clear_all():
    user_id = _get_user_id()
    Notification.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    return jsonify({"success": True})


@api_notifications_bp.route("/api/v1/notifications/<int:nid>/read", methods=["POST"])
@jwt_required()
def mark_read(nid):
    user_id = _get_user_id()
    n = db.session.get(Notification, nid)
    if not n or n.user_id != user_id:
        return jsonify({"success": False, "error": "not_found", "message": "Notification not found."}), 404
    n.is_read = True
    db.session.commit()
    return jsonify({"success": True})


@api_notifications_bp.route("/api/v1/notifications", methods=["GET"])
@jwt_required()
def list_notifications():
    user_id = _get_user_id()
    page = request.args.get("page", 1, type=int)
    per_page = 20

    total = Notification.query.filter_by(user_id=user_id).count()
    notifications = (
        Notification.query.filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()

    return jsonify({
        "success": True,
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "total": total,
        "pages": ceil(total / per_page) if total > 0 else 0,
        "current_page": page,
        "per_page": per_page,
        "unread_count": unread_count,
    })
