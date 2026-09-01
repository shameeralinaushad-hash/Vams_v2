import os
from datetime import timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt,
)
from models import db, User, Company

api_auth_bp = Blueprint("api_auth", __name__)

jwt = JWTManager()


def init_jwt(app):
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", app.config["SECRET_KEY"])
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=15)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=7)
    app.config["JWT_TOKEN_LOCATION"] = ["headers"]
    app.config["JWT_HEADER_NAME"] = "Authorization"
    app.config["JWT_HEADER_TYPE"] = "Bearer"
    jwt.init_app(app)


@api_auth_bp.route("/api/v1/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True)
    if not data:
        print(f"[AUTH_API] login: no JSON body")
        return jsonify({"success": False, "error": "invalid_request", "message": "Request body must be JSON."}), 400

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    print(f"[AUTH_API] login: email='{email}', password_len={len(password)}")

    if not email or not password:
        print(f"[AUTH_API] login: empty email or password")
        return jsonify({"success": False, "error": "validation_error", "message": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        print(f"[AUTH_API] login: user NOT found for email='{email}'")
        return jsonify({"success": False, "error": "invalid_credentials", "message": "Invalid email or password."}), 401
    
    pw_ok = user.check_password(password)
    print(f"[AUTH_API] login: user found id={user.id}, password_ok={pw_ok}")
    if not pw_ok:
        return jsonify({"success": False, "error": "invalid_credentials", "message": "Invalid email or password."}), 401

    if not user.is_active_user:
        return jsonify({"success": False, "error": "account_disabled", "message": "This account has been deactivated."}), 403

    companies = Company.query.all()
    company_list = [{"id": c.id, "name": c.name} for c in companies]

    company_id = None
    company_name = None
    requested_company_id = data.get("company_id")
    if requested_company_id:
        company = db.session.get(Company, int(requested_company_id))
        if company:
            company_id = company.id
            company_name = company.name
    elif user.employee and user.employee.company_id:
        company_id = user.employee.company_id
        company = db.session.get(Company, company_id)
        company_name = company.name if company else None

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "company_id": company_id},
    )
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "needs_company": company_id is None,
        "companies": company_list,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "company_id": company_id,
            "company_name": company_name,
        },
    })


@api_auth_bp.route("/api/v1/auth/refresh", methods=["POST"])
@jwt_required(refresh=True)
def api_refresh():
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity))
    if not user or not user.is_active_user:
        return jsonify({"success": False, "error": "unauthorized", "message": "User not found or inactive."}), 401

    company_id = None
    if user.employee and user.employee.company_id:
        company_id = user.employee.company_id
    else:
        claims = get_jwt()
        company_id = claims.get("company_id")

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "company_id": company_id},
    )

    return jsonify({"success": True, "access_token": access_token})


@api_auth_bp.route("/api/v1/auth/select-company", methods=["POST"])
@jwt_required()
def api_select_company():
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity))
    if not user:
        return jsonify({"success": False, "error": "not_found", "message": "User not found."}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("company_id"):
        return jsonify({"success": False, "error": "validation_error", "message": "company_id is required."}), 400

    company = db.session.get(Company, int(data["company_id"]))
    if not company:
        return jsonify({"success": False, "error": "not_found", "message": "Company not found."}), 404

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "company_id": company.id},
    )

    return jsonify({
        "success": True,
        "access_token": access_token,
        "company": {"id": company.id, "name": company.name},
    })


@api_auth_bp.route("/api/v1/auth/me", methods=["GET"])
@jwt_required()
def api_me():
    identity = get_jwt_identity()
    claims = get_jwt()
    print(f"[AUTH_API] /me called: identity={identity}, claims={claims}")
    user = db.session.get(User, int(identity))
    if not user:
        print(f"[AUTH_API] /me: user not found for identity={identity}")
        return jsonify({"success": False, "error": "not_found", "message": "User not found."}), 404

    company_id = claims.get("company_id")
    company_name = None
    if company_id:
        company = db.session.get(Company, company_id)
        company_name = company.name if company else None
    elif user.employee and user.employee.company_id:
        company_id = user.employee.company_id
        company = db.session.get(Company, company_id)
        company_name = company.name if company else None

    companies = Company.query.all()

    print(f"[AUTH_API] /me: user={user.name}, company_id={company_id}")
    return jsonify({
        "success": True,
        "needs_company": company_id is None,
        "companies": [{"id": c.id, "name": c.name} for c in companies],
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "company_id": company_id,
            "company_name": company_name,
        },
    })


@api_auth_bp.route("/api/v1/auth/profile", methods=["PUT"])
@jwt_required()
def api_update_profile():
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity))
    if not user:
        return jsonify({"success": False, "error": "not_found", "message": "User not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    if "name" in data:
        user.name = data["name"].strip() if data["name"] else user.name

    if "email" in data:
        new_email = data["email"].strip().lower()
        if new_email and new_email != user.email:
            existing = User.query.filter_by(email=new_email).first()
            if existing and existing.id != user.id:
                return jsonify({"success": False, "error": "validation_error", "message": "Email already in use."}), 400
            user.email = new_email

    db.session.commit()

    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
        },
    })


@api_auth_bp.route("/api/v1/auth/change-password", methods=["POST"])
@jwt_required()
def api_change_password():
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity))
    if not user:
        return jsonify({"success": False, "error": "not_found", "message": "User not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if not current_password or not new_password:
        return jsonify({"success": False, "error": "validation_error", "message": "Current and new password are required."}), 400

    if len(new_password) < 6:
        return jsonify({"success": False, "error": "validation_error", "message": "New password must be at least 6 characters."}), 400

    if not user.check_password(current_password):
        return jsonify({"success": False, "error": "invalid_credentials", "message": "Current password is incorrect."}), 401

    user.set_password(new_password)
    db.session.commit()

    return jsonify({"success": True, "message": "Password changed successfully."})


@api_auth_bp.route("/api/v1/auth/users", methods=["GET"])
@jwt_required()
def api_list_users():
    identity = get_jwt_identity()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403

    users = User.query.all()
    return jsonify({
        "success": True,
        "users": [{
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_active_user": u.is_active_user,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        } for u in users],
    })


@api_auth_bp.route("/api/v1/auth/users", methods=["POST"])
@jwt_required()
def api_create_user():
    identity = get_jwt_identity()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role", "staff")

    if not name or not email or not password:
        return jsonify({"success": False, "error": "validation_error", "message": "Name, email, and password are required."}), 400

    if role not in ("admin", "staff"):
        role = "staff"

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"success": False, "error": "validation_error", "message": "Email already in use."}), 400

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_active_user": user.is_active_user,
        },
    }), 201


@api_auth_bp.route("/api/v1/auth/users/<int:user_id>", methods=["PUT"])
@jwt_required()
def api_edit_user(user_id):
    identity = get_jwt_identity()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"success": False, "error": "not_found", "message": "User not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    if "name" in data:
        user.name = data["name"].strip() if data["name"] else user.name

    if "email" in data:
        new_email = data["email"].strip().lower()
        if new_email and new_email != user.email:
            existing = User.query.filter_by(email=new_email).first()
            if existing and existing.id != user.id:
                return jsonify({"success": False, "error": "validation_error", "message": "Email already in use."}), 400
            user.email = new_email

    if "role" in data and data["role"] in ("admin", "staff"):
        user.role = data["role"]

    if "is_active_user" in data:
        user.is_active_user = bool(data["is_active_user"])

    if "password" in data and data["password"]:
        user.set_password(data["password"])

    db.session.commit()

    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_active_user": user.is_active_user,
        },
    })


@api_auth_bp.route("/api/v1/auth/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
def api_delete_user(user_id):
    identity = get_jwt_identity()
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"success": False, "error": "not_found", "message": "User not found."}), 404

    current_user_id = int(identity)
    if user.id == current_user_id:
        return jsonify({"success": False, "error": "validation_error", "message": "Cannot delete your own account."}), 400

    db.session.delete(user)
    db.session.commit()

    return jsonify({"success": True, "message": "User deleted."})


@api_auth_bp.route("/api/v1/audit-logs", methods=["GET"])
@jwt_required()
def get_audit_logs():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403
    from models import AuditLog
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    pagination = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    logs = []
    for log in pagination.items:
        logs.append({
            "id": log.id,
            "user_name": log.user_name if hasattr(log, 'user_name') else None,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "details": log.details if hasattr(log, 'details') else None,
            "ip_address": log.ip_address if hasattr(log, 'ip_address') else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return jsonify({"success": True, "logs": logs, "total": pagination.total})


@api_auth_bp.errorhandler(422)
def handle_unprocessable(e):
    return jsonify({"success": False, "error": "token_expired", "message": "Session expired. Please log in again."}), 401


@api_auth_bp.errorhandler(401)
def handle_unauthorized(e):
    return jsonify({"success": False, "error": "unauthorized", "message": "Authentication required."}), 401
