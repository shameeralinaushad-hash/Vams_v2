from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from flask_login import login_required
from models import Order, Client, Invoice, Quotation

search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.route("/api")
@login_required
def search_api():
    company_id = session.get("active_company_id")
    q = request.args.get("q", "").strip()
    if not company_id or not q:
        return jsonify([])
    like = f"%{q}%"
    out = []
    for o in Order.query.filter(Order.company_id == company_id, Order.title.ilike(like)).limit(6).all():
        out.append({
            "type": "Order", "label": o.title, "sub": o.order_number or "",
            "url": url_for("orders.view_order", order_id=o.id),
            "icon": "bi-clipboard-data", "color": "#2563eb",
        })
    for cl in Client.query.join(Client.company_links).filter_by(company_id=company_id).filter(Client.name.ilike(like)).limit(6).all():
        out.append({
            "type": "Client", "label": cl.name, "sub": "",
            "url": url_for("clients.view_profile", client_id=cl.id),
            "icon": "bi-people", "color": "#0ea5e9",
        })
    for inv in Invoice.query.join(Order).filter(Order.company_id == company_id).filter(Invoice.invoice_number.ilike(like)).limit(6).all():
        out.append({
            "type": "Invoice", "label": inv.invoice_number, "sub": getattr(inv, "title", "") or "",
            "url": url_for("invoices.edit_invoice", invoice_id=inv.id),
            "icon": "bi-receipt", "color": "#8b5cf6",
        })
    for qt in Quotation.query.join(Order).filter(Order.company_id == company_id).filter(Quotation.quote_number.ilike(like)).limit(6).all():
        out.append({
            "type": "Quotation", "label": qt.quote_number, "sub": getattr(qt, "title", "") or "",
            "url": url_for("quotations.edit_quotation", quotation_id=qt.id),
            "icon": "bi-file-earmark-text", "color": "#f59e0b",
        })
    return jsonify(out)


@search_bp.route("/")
def global_search():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    q = request.args.get("q", "").strip()
    results = {"orders": [], "clients": [], "invoices": [], "quotations": []}

    if q:
        like = f"%{q}%"

        results["orders"] = (
            Order.query.filter(Order.company_id == company_id)
            .filter(Order.title.ilike(like))
            .limit(15).all()
        )

        results["clients"] = (
            Client.query.join(Client.company_links)
            .filter_by(company_id=company_id)
            .filter(Client.name.ilike(like))
            .limit(15).all()
        )

        results["invoices"] = (
            Invoice.query.join(Order)
            .filter(Order.company_id == company_id)
            .filter(Invoice.invoice_number.ilike(like))
            .limit(15).all()
        )

        results["quotations"] = (
            Quotation.query.join(Order)
            .filter(Order.company_id == company_id)
            .filter(Quotation.quote_number.ilike(like))
            .limit(15).all()
        )

    return render_template("search/results.html", q=q, results=results)