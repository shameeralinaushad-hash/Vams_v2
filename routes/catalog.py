from flask import Blueprint, render_template, request, jsonify, session, current_app
from models import db, CatalogItem, PriceHistory
from market_price import check_market_price

catalog_bp = Blueprint("catalog", __name__, url_prefix="/catalog")


@catalog_bp.route("/")
def list_catalog():
    # 1. Fetch all items
    items = CatalogItem.query.order_by(CatalogItem.description).all()

    # 2. Capture highlight ID for the "shine" effect
    highlight_id = request.args.get("highlight", type=int)

    # 3. Calculate Metrics
    total_items = len(items)
    total_history_count = PriceHistory.query.count()

    # 4. Prepare Chart Data (Top 5 most frequently quoted items)
    # Sort by history length descending
    top_items = sorted(items, key=lambda x: len(x.price_history), reverse=True)[:5]

    chart_labels = [i.description for i in top_items]
    chart_data = [len(i.price_history) for i in top_items]

    return render_template(
        "catalog/list.html",
        items=items,
        highlight_id=highlight_id,
        total_items=total_items,
        total_history_count=total_history_count,
        chart_labels=chart_labels,
        chart_data=chart_data
    )

@catalog_bp.route("/market_price/<int:item_id>")
def market_price(item_id):
    """Free, self-built market price check: searches Google's free-tier
    Custom Search API for this item, then extracts and aggregates price
    mentions from the results ourselves (no paid AI). Returns the raw
    sources alongside the suggestion so the result can be verified, not
    just trusted blindly."""
    item = CatalogItem.query.get_or_404(item_id)
    result = check_market_price(
        item.description,
        api_key=current_app.config.get("TAVILY_API_KEY"),
    )
    return jsonify(result)


@catalog_bp.route("/search")
def search_items():
    from utils import find_fuzzy_matches
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])

    substring_matches = CatalogItem.query.filter(CatalogItem.description.ilike(f"%{q}%")).limit(8).all()
    seen_ids = {item.id for item in substring_matches}

    all_items = CatalogItem.query.limit(500).all()
    fuzzy_results = find_fuzzy_matches(q, all_items, lambda i: i.description, threshold=0.65, limit=8)
    fuzzy_matches = [item for item, score in fuzzy_results if item.id not in seen_ids]

    combined = substring_matches + fuzzy_matches
    return jsonify([{"id": item.id, "description": item.description} for item in combined[:8]])


@catalog_bp.route("/suggest_price")
def suggest_price():
    item_id = request.args.get("item_id", type=int)
    client_id = request.args.get("client_id", type=int)
    company_id = session.get("active_company_id")

    if not item_id:
        return jsonify({"price": None, "source": None})

    if client_id:
        client_entry = (
            PriceHistory.query.filter_by(catalog_item_id=item_id, client_id=client_id)
            .order_by(PriceHistory.quoted_date.desc(), PriceHistory.id.desc())
            .first()
        )
        if client_entry:
            return jsonify({"price": client_entry.price, "source": "this client"})

    query = PriceHistory.query.filter_by(catalog_item_id=item_id)
    if company_id:
        query = query.filter_by(company_id=company_id)
    general_entry = query.order_by(PriceHistory.quoted_date.desc(), PriceHistory.id.desc()).first()

    if general_entry:
        return jsonify({"price": general_entry.price, "source": "most recent overall"})

    return jsonify({"price": None, "source": None})


@catalog_bp.route("/duplicates")
def review_duplicates():
    from utils import fuzzy_similarity
    all_items = CatalogItem.query.order_by(CatalogItem.description).all()
    checked_pairs = set()
    duplicate_groups = []

    for i, item_a in enumerate(all_items):
        for item_b in all_items[i + 1:]:
            pair_key = tuple(sorted([item_a.id, item_b.id]))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)

            score = fuzzy_similarity(item_a.description, item_b.description)
            if score >= 0.72:
                duplicate_groups.append({"a": item_a, "b": item_b, "score": round(score * 100)})

    duplicate_groups.sort(key=lambda g: g["score"], reverse=True)
    return render_template("catalog/duplicates.html", duplicate_groups=duplicate_groups)