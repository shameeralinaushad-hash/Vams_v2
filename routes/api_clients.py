from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt
from models import db, Client, ClientCompanyLink, ClientSubsidiary, Company, Order, Invoice

api_clients_bp = Blueprint("api_clients", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _serialize_client_list(client):
    return {
        "id": client.id,
        "name": client.name,
        "client_code": client.client_code,
        "email": client.email,
        "contact_info": client.contact_info,
        "logo_filename": client.logo_filename,
        "created_at": client.created_at.isoformat() if client.created_at else None,
    }


def _serialize_client_detail(client):
    companies = []
    for link in client.company_links:
        companies.append({
            "id": link.company.id if link.company else None,
            "name": link.company.name if link.company else None,
        })

    subsidiaries = []
    for sub in client.subsidiaries:
        subsidiaries.append({
            "id": sub.id,
            "name": sub.name,
            "address": sub.address,
            "contact_info": sub.contact_info,
            "client_code": sub.client_code,
        })

    order_count = Order.query.filter_by(client_id=client.id).count()

    return {
        "id": client.id,
        "name": client.name,
        "address": client.address,
        "contact_info": client.contact_info,
        "tax_number": client.tax_number,
        "client_code": client.client_code,
        "email": client.email,
        "emails": client.emails,
        "domain": client.domain,
        "logo_filename": client.logo_filename,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "gst_registration": client.gst_registration,
        "gst_registration_number": client.gst_registration_number,
        "companies": companies,
        "subsidiaries": subsidiaries,
        "order_count": order_count,
    }


@api_clients_bp.route("/api/v1/clients")
@jwt_required()
def list_clients():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(per_page, 100)

    search = request.args.get("search", "").strip()
    sort_by = request.args.get("sort_by", "name")
    sort_dir = request.args.get("sort_dir", "asc")

    query = (
        Client.query
        .join(ClientCompanyLink, Client.id == ClientCompanyLink.client_id)
        .filter(ClientCompanyLink.company_id == company_id)
        .options(db.selectinload(Client.company_links).joinedload(ClientCompanyLink.company))
        .distinct()
    )

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Client.name.ilike(like),
                Client.client_code.ilike(like),
                Client.email.ilike(like),
                Client.contact_info.ilike(like),
            )
        )

    sort_map = {
        "name": Client.name,
        "id": Client.id,
        "client_code": Client.client_code,
        "created_at": Client.created_at,
    }
    sort_col = sort_map.get(sort_by, Client.name)
    query = query.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "success": True,
        "clients": [_serialize_client_list(c) for c in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
        "per_page": per_page,
    })


@api_clients_bp.route("/api/v1/clients/<int:client_id>")
@jwt_required()
def get_client(client_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    client = db.session.get(Client, client_id)
    if not client:
        return jsonify({"success": False, "error": "not_found", "message": "Client not found."}), 404

    linked = any(link.company_id == company_id for link in client.company_links)
    if not linked:
        return jsonify({"success": False, "error": "not_found", "message": "Client not found."}), 404

    return jsonify({"success": True, "client": _serialize_client_detail(client)})


@api_clients_bp.route("/api/v1/clients/search")
@jwt_required()
def search_clients():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify({"success": True, "results": []})

    like = f"%{q}%"
    clients = (
        Client.query
        .join(ClientCompanyLink, Client.id == ClientCompanyLink.client_id)
        .filter(ClientCompanyLink.company_id == company_id)
        .filter(
            db.or_(
                Client.name.ilike(like),
                Client.client_code.ilike(like),
                Client.email.ilike(like),
            )
        )
        .order_by(Client.name)
        .limit(10)
        .all()
    )

    results = []
    seen = set()
    for c in clients:
        if c.id in seen:
            continue
        seen.add(c.id)
        results.append({
            "id": c.id,
            "name": c.name,
            "client_code": c.client_code,
            "email": c.email,
        })

    return jsonify({"success": True, "results": results})


@api_clients_bp.route("/api/v1/clients", methods=["POST"])
@jwt_required()
def create_client():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    data = request.get_json()
    if not data or not data.get("name", "").strip():
        return jsonify({"success": False, "error": "validation_error", "message": "Client name is required."}), 400

    client = Client(
        name=data["name"].strip(),
        address=data.get("address", ""),
        contact_info=data.get("contact_info", ""),
        tax_number=data.get("tax_number", ""),
        client_code=data.get("client_code", ""),
        email=data.get("email", "").strip() or None,
        emails=data.get("emails", "").strip() or None,
        domain=data.get("domain", "").strip() or None,
        gst_registration=data.get("gst_registration", False),
        gst_registration_number=data.get("gst_registration_number", ""),
    )
    db.session.add(client)
    db.session.flush()

    db.session.add(ClientCompanyLink(client_id=client.id, company_id=company_id))

    for sub_data in data.get("subsidiaries", []):
        if sub_data.get("name", "").strip():
            sub = ClientSubsidiary(
                parent_client_id=client.id,
                name=sub_data["name"].strip(),
                address=sub_data.get("address", ""),
                contact_info=sub_data.get("contact_info", ""),
                client_code=sub_data.get("client_code", ""),
            )
            db.session.add(sub)

    db.session.commit()

    return jsonify({"success": True, "client": _serialize_client_detail(client)}), 201


@api_clients_bp.route("/api/v1/clients/<int:client_id>", methods=["PUT"])
@jwt_required()
def update_client(client_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    client = db.session.get(Client, client_id)
    if not client:
        return jsonify({"success": False, "error": "not_found", "message": "Client not found."}), 404

    linked = any(link.company_id == company_id for link in client.company_links)
    if not linked:
        return jsonify({"success": False, "error": "not_found", "message": "Client not found."}), 404

    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "No data provided."}), 400

    if "name" in data:
        client.name = data["name"].strip()
    if "address" in data:
        client.address = data["address"]
    if "contact_info" in data:
        client.contact_info = data["contact_info"]
    if "tax_number" in data:
        client.tax_number = data["tax_number"]
    if "client_code" in data:
        client.client_code = data["client_code"]
    if "email" in data:
        client.email = data["email"].strip() or None
    if "emails" in data:
        client.emails = data["emails"].strip() or None
    if "domain" in data:
        client.domain = data["domain"].strip() or None
    if "gst_registration" in data:
        client.gst_registration = data["gst_registration"]
    if "gst_registration_number" in data:
        client.gst_registration_number = data["gst_registration_number"]

    db.session.commit()

    return jsonify({"success": True, "client": _serialize_client_detail(client)})


@api_clients_bp.route("/api/v1/clients/<int:client_id>/subsidiaries", methods=["POST"])
@jwt_required()
def add_subsidiary(client_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    client = db.session.get(Client, client_id)
    if not client:
        return jsonify({"success": False, "error": "not_found", "message": "Client not found."}), 404

    linked = any(link.company_id == company_id for link in client.company_links)
    if not linked:
        return jsonify({"success": False, "error": "not_found", "message": "Client not found."}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("name", "").strip():
        return jsonify({"success": False, "error": "validation_error", "message": "Subsidiary name is required."}), 400

    sub = ClientSubsidiary(
        parent_client_id=client.id,
        name=data["name"].strip(),
        address=data.get("address", ""),
        contact_info=data.get("contact_info", ""),
        tax_number=data.get("tax_number", ""),
        client_code=data.get("client_code", ""),
    )
    db.session.add(sub)
    db.session.commit()

    return jsonify({
        "success": True,
        "subsidiary": {
            "id": sub.id,
            "name": sub.name,
            "address": sub.address,
            "contact_info": sub.contact_info,
            "tax_number": sub.tax_number,
            "client_code": sub.client_code,
        },
    }), 201


@api_clients_bp.route("/api/v1/clients/subsidiaries/<int:sub_id>", methods=["DELETE"])
@jwt_required()
def delete_subsidiary(sub_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    sub = db.session.get(ClientSubsidiary, sub_id)
    if not sub:
        return jsonify({"success": False, "error": "not_found", "message": "Subsidiary not found."}), 404

    client = sub.parent_client
    linked = any(link.company_id == company_id for link in client.company_links)
    if not linked:
        return jsonify({"success": False, "error": "not_found", "message": "Subsidiary not found."}), 404

    db.session.delete(sub)
    db.session.commit()

    return jsonify({"success": True, "message": "Subsidiary deleted."})
