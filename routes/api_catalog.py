from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, CatalogItem, PriceHistory

api_catalog_bp = Blueprint("api_catalog", __name__)


@api_catalog_bp.route("/api/v1/catalog/search")
@jwt_required()
def search_catalog():
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify({"success": True, "results": []})

    like = f"%{q}%"
    items = CatalogItem.query.filter(
        CatalogItem.description.ilike(like)
    ).order_by(CatalogItem.description).limit(20).all()

    return jsonify({
        "success": True,
        "results": [
            {"id": i.id, "description": i.description, "unit": i.unit}
            for i in items
        ],
    })


@api_catalog_bp.route("/api/v1/catalog/suggest-price")
@jwt_required()
def suggest_price():
    item_id = request.args.get("item_id", type=int)
    client_id = request.args.get("client_id", type=int)

    if not item_id:
        return jsonify({"success": True, "price": 0})

    query = PriceHistory.query.filter_by(catalog_item_id=item_id)
    if client_id:
        query = query.filter_by(client_id=client_id)
    history = query.order_by(PriceHistory.quoted_date.desc()).first()

    return jsonify({
        "success": True,
        "price": history.price if history else 0,
        "source": "client" if history and history.client_id == client_id else "general",
    })
