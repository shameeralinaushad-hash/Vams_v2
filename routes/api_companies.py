from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt
from models import db, Company

api_companies_bp = Blueprint("api_companies", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


@api_companies_bp.route("/api/v1/companies")
@jwt_required()
def list_companies():
    companies = Company.query.all()
    return jsonify({
        "success": True,
        "companies": [
            {
                "id": c.id,
                "name": c.name,
                "short_name": c.short_name,
                "location_code": c.location_code,
            }
            for c in companies
        ],
    })


@api_companies_bp.route("/api/v1/companies/<int:company_id>")
@jwt_required()
def get_company(company_id):
    company = db.session.get(Company, company_id)
    if not company:
        return jsonify({"success": False, "error": "not_found", "message": "Company not found."}), 404

    return jsonify({
        "success": True,
        "company": {
            "id": company.id,
            "name": company.name,
            "short_name": company.short_name,
            "address": company.address,
            "phone": company.phone,
            "email": company.email,
            "tax_number": company.tax_number,
            "bank_details": company.bank_details,
            "authorized_name": company.authorized_name,
            "designation": company.designation,
            "entity_type": company.entity_type,
            "ein": company.ein,
            "registered_agent": company.registered_agent,
            "terms_conditions": company.terms_conditions,
            "location_code": company.location_code,
            "logo_filename": company.logo_filename,
            "signature_filename": company.signature_filename,
            "letterhead_filename": company.letterhead_filename,
        },
    })


@api_companies_bp.route("/api/v1/companies", methods=["POST"])
@jwt_required()
def create_company():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "validation_error", "message": "Company name is required."}), 400

    company = Company(
        name=name,
        short_name=(data.get("short_name") or "").strip() or None,
        address=(data.get("address") or "").strip() or None,
        phone=(data.get("phone") or "").strip() or None,
        email=(data.get("email") or "").strip() or None,
        tax_number=(data.get("tax_number") or "").strip() or None,
        location_code=(data.get("location_code") or "").strip() or None,
    )
    db.session.add(company)
    db.session.commit()

    return jsonify({
        "success": True,
        "company": {
            "id": company.id,
            "name": company.name,
            "short_name": company.short_name,
            "address": company.address,
            "phone": company.phone,
            "email": company.email,
            "tax_number": company.tax_number,
            "location_code": company.location_code,
        },
    }), 201


@api_companies_bp.route("/api/v1/companies/<int:company_id>", methods=["PUT"])
@jwt_required()
def edit_company(company_id):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403

    company = db.session.get(Company, company_id)
    if not company:
        return jsonify({"success": False, "error": "not_found", "message": "Company not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    if "name" in data:
        company.name = data["name"].strip() if data["name"] else company.name
    if "short_name" in data:
        company.short_name = data["short_name"].strip() or None
    if "address" in data:
        company.address = data["address"].strip() or None
    if "phone" in data:
        company.phone = data["phone"].strip() or None
    if "email" in data:
        company.email = data["email"].strip() or None
    if "tax_number" in data:
        company.tax_number = data["tax_number"].strip() or None
    if "bank_details" in data:
        company.bank_details = data["bank_details"].strip() or None
    if "authorized_name" in data:
        company.authorized_name = data["authorized_name"].strip() or None
    if "designation" in data:
        company.designation = data["designation"].strip() or None
    if "location_code" in data:
        company.location_code = data["location_code"].strip() or None
    if "terms_conditions" in data:
        company.terms_conditions = data["terms_conditions"].strip() or None

    db.session.commit()

    return jsonify({
        "success": True,
        "company": {
            "id": company.id,
            "name": company.name,
            "short_name": company.short_name,
            "address": company.address,
            "phone": company.phone,
            "email": company.email,
            "tax_number": company.tax_number,
            "location_code": company.location_code,
        },
    })
