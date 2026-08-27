import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, jsonify, send_file
from flask_login import login_required
from werkzeug.utils import secure_filename
from models import db, Client, ClientCompanyLink, Company, ClientDocSequence, Order
from utils import validate_upload, ALLOWED_IMAGE_EXTENSIONS, delete_file_if_exists, find_fuzzy_matches
from permissions import permission_required
from audit import log_action
from pdf_templates.statement_template import generate_statement_pdf

clients_bp = Blueprint("clients", __name__, url_prefix="/clients")


@clients_bp.route("/")
def list_clients():
    page = request.args.get("page", 1, type=int)
    pagination = (
        Client.query.options(db.selectinload(Client.company_links).joinedload(ClientCompanyLink.company))
        .order_by(Client.name)
        .paginate(page=page, per_page=25, error_out=False)
    )
    return render_template("clients/list.html", clients=pagination.items, pagination=pagination)


@clients_bp.route("/add", methods=["GET", "POST"])
def add_client():
    companies = Company.query.all()

    if request.method == "POST":
        name = request.form["name"]
        address = request.form.get("address", "")
        contact_info = request.form.get("contact_info", "")
        tax_number = request.form.get("tax_number", "")
        client_code = request.form.get("client_code", "")
        email = request.form.get("email", "").strip() or None

        logo_filename = None
        file = request.files.get("logo")
        if file and file.filename:
            if not validate_upload(file, ALLOWED_IMAGE_EXTENSIONS):
                flash("Client logo must be an image file (PNG, JPG, GIF, or WEBP).")
                return redirect(request.url)
            logo_filename = secure_filename(f"{name}_{file.filename}")
            file.save(os.path.join(current_app.config["CLIENT_LOGO_FOLDER"], logo_filename))

        client = Client(
            name=name,
            address=address,
            contact_info=contact_info,
            tax_number=tax_number,
            logo_filename=logo_filename,
            client_code=client_code,
            email=email,
        )
        db.session.add(client)
        db.session.commit()

        selected_company_ids = request.form.getlist("company_ids")
        for cid in selected_company_ids:
            db.session.add(ClientCompanyLink(client_id=client.id, company_id=int(cid)))
        db.session.commit()

        return redirect(url_for("clients.list_clients"))

    return render_template("clients/add.html", companies=companies)

@clients_bp.route("/edit/<int:client_id>", methods=["GET", "POST"])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    companies = Company.query.all()
    linked_company_ids = {link.company_id for link in client.company_links}

    if request.method == "POST":
        client.name = request.form["name"]
        client.address = request.form.get("address", "")
        client.contact_info = request.form.get("contact_info", "")
        client.tax_number = request.form.get("tax_number", "")
        client.client_code = request.form.get("client_code", "")
        client.email = request.form.get("email", "").strip() or None

        file = request.files.get("logo")
        if file and file.filename:
            if not validate_upload(file, ALLOWED_IMAGE_EXTENSIONS):
                flash("Client logo must be an image file (PNG, JPG, GIF, or WEBP).")
                return redirect(request.url)
            delete_file_if_exists(current_app.config["CLIENT_LOGO_FOLDER"], client.logo_filename)
            new_logo_filename = secure_filename(f"{client.name}_{file.filename}")
            file.save(os.path.join(current_app.config["CLIENT_LOGO_FOLDER"], new_logo_filename))
            client.logo_filename = new_logo_filename

        db.session.commit()

        selected_company_ids = {int(cid) for cid in request.form.getlist("company_ids")}
        for link in list(client.company_links):
            if link.company_id not in selected_company_ids:
                db.session.delete(link)
        existing_ids = {link.company_id for link in client.company_links}
        for cid in selected_company_ids - existing_ids:
            db.session.add(ClientCompanyLink(client_id=client.id, company_id=cid))
        db.session.commit()

        flash(f"Client '{client.name}' updated.")
        return redirect(url_for("clients.view_profile", client_id=client.id))

    return render_template("clients/edit.html", client=client, companies=companies, linked_company_ids=linked_company_ids)

@clients_bp.route("/delete/<int:client_id>", methods=["POST"])
@permission_required("delete_clients")
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)

    order_count = Order.query.filter_by(client_id=client.id).count()
    if order_count > 0:
        flash(f"Cannot delete '{client.name}' — it has {order_count} order(s) linked to it. Remove or reassign those first.")
        return redirect(url_for("clients.list_clients"))

    client_name = client.name
    db.session.delete(client)
    db.session.commit()

    log_action("delete_client", "Client", client_id, f"Deleted client {client_name}")

    flash(f"Client '{client_name}' deleted.")
    return redirect(url_for("clients.list_clients"))


@clients_bp.route("/<int:client_id>")
def view_profile(client_id):
    client = Client.query.get_or_404(client_id)
    all_clients = Client.query.order_by(Client.name).all()
    orders = Order.query.filter_by(client_id=client.id).order_by(Order.created_at.desc()).all()

    company_breakdown = []
    combined_revenue = 0
    combined_paid = 0
    combined_owed = 0

    for link in client.company_links:
        company = link.company
        company_orders = [o for o in orders if o.company_id == company.id]
        company_invoices = [o.invoice for o in company_orders if o.invoice]

        revenue = sum(inv.total_amount for inv in company_invoices)
        paid = sum(inv.total_paid() for inv in company_invoices)
        owed = sum(inv.balance_due() for inv in company_invoices)

        combined_revenue += revenue
        combined_paid += paid
        combined_owed += owed

        company_breakdown.append({
            "company": company,
            "revenue": revenue,
            "paid": paid,
            "owed": owed,
        })

    combined_stats = {
        "revenue": combined_revenue,
        "paid": combined_paid,
        "owed": combined_owed,
    }

    numbering_info = []
    for link in client.company_links:
        company = link.company
        row = {"company": company}
        for doc_type in ("quotation", "invoice", "challan"):
            seq = ClientDocSequence.get_or_create(company.id, client.id, doc_type)
            row[doc_type] = seq.peek_next_raw_number()
        numbering_info.append(row)

    return render_template(
        "clients/profile.html",
        client=client,
        all_clients=all_clients,
        orders=orders,
        company_breakdown=company_breakdown,
        combined_stats=combined_stats,
        numbering_info=numbering_info,
    )


@clients_bp.route("/<int:client_id>/numbering/update", methods=["POST"])
@permission_required("manage_numbering")
def update_client_numbering(client_id):
    client = Client.query.get_or_404(client_id)
    company_id = request.form.get("company_id", type=int)
    doc_type = request.form.get("doc_type", "")
    next_number = request.form.get("next_number", type=int)

    if doc_type not in ("quotation", "invoice", "challan") or not company_id or not next_number or next_number < 1:
        flash("Invalid numbering update.")
        return redirect(url_for("clients.view_profile", client_id=client.id))

    seq = ClientDocSequence.get_or_create(company_id, client.id, doc_type)
    seq.last_number = next_number - 1
    seq.last_reset_year = datetime.utcnow().year
    db.session.commit()

    flash(f"Next {doc_type} number for {client.name} set to {next_number}.")
    return redirect(url_for("clients.view_profile", client_id=client.id))

@clients_bp.route("/<int:client_id>/statement")
@login_required
def download_statement(client_id):
    client = Client.query.get_or_404(client_id)
    orders = Order.query.filter_by(client_id=client.id).order_by(Order.created_at.desc()).all()

    company_breakdown = []
    combined_revenue = combined_paid = combined_owed = 0
    for link in client.company_links:
        company = link.company
        company_orders = [o for o in orders if o.company_id == company.id]
        company_invoices = [o.invoice for o in company_orders if o.invoice]
        revenue = sum(inv.total_amount for inv in company_invoices)
        paid = sum(inv.total_paid() for inv in company_invoices)
        owed = sum(inv.balance_due() for inv in company_invoices)
        combined_revenue += revenue
        combined_paid += paid
        combined_owed += owed
        company_breakdown.append({"company": company, "revenue": revenue, "paid": paid, "owed": owed})

    combined_stats = {"revenue": combined_revenue, "paid": combined_paid, "owed": combined_owed}

    folder = os.path.join(current_app.root_path, "static", "statements")
    os.makedirs(folder, exist_ok=True)
    filename = f"Statement_{client.name.replace(' ', '_')}.pdf"
    output_path = os.path.join(folder, filename)

    generate_statement_pdf(client, company_breakdown, combined_stats, orders, output_path)

    view_only = request.args.get("view") == "1"
    return send_file(output_path, as_attachment=not view_only, download_name=filename)
@clients_bp.route("/check-duplicate")
@login_required
def check_duplicate_client():
    name = request.args.get("name", "").strip()
    if len(name) < 3:
        return jsonify([])

    all_clients = Client.query.all()
    matches = find_fuzzy_matches(name, all_clients, lambda c: c.name)

    return jsonify([{"id": c.id, "name": c.name, "score": round(score * 100)} for c, score in matches])

from models import ClientSubsidiary


@clients_bp.route("/<int:client_id>/subsidiaries/add", methods=["POST"])
def add_subsidiary(client_id):
    client = Client.query.get_or_404(client_id)

    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    contact_info = request.form.get("contact_info", "").strip()
    tax_number = request.form.get("tax_number", "").strip()
    client_code = request.form.get("client_code", "").strip()

    if not name:
        flash("Subsidiary name is required.")
        return redirect(url_for("clients.view_profile", client_id=client.id))

    sub = ClientSubsidiary(
        parent_client_id=client.id, name=name, address=address,
        contact_info=contact_info, tax_number=tax_number, client_code=client_code
    )
    db.session.add(sub)
    db.session.commit()

    flash(f"Subsidiary '{name}' added under {client.name}.")
    return redirect(url_for("clients.view_profile", client_id=client.id))


@clients_bp.route("/subsidiaries/delete/<int:subsidiary_id>", methods=["POST"])
def delete_subsidiary(subsidiary_id):
    sub = ClientSubsidiary.query.get_or_404(subsidiary_id)
    parent_id = sub.parent_client_id
    name = sub.name

    db.session.delete(sub)
    db.session.commit()

    flash(f"Subsidiary '{name}' removed.")
    return redirect(url_for("clients.view_profile", client_id=parent_id))


@clients_bp.route("/subsidiaries/<int:subsidiary_id>")
def view_subsidiary_profile(subsidiary_id):
    sub = ClientSubsidiary.query.get_or_404(subsidiary_id)
    parent = sub.parent_client

    orders = (
        Order.query.filter_by(subsidiary_id=sub.id)
        .options(db.selectinload(Order.invoices))
        .order_by(Order.created_at.desc())
        .all()
    )
    total_revenue = total_paid = total_owed = 0
    for o in orders:
        if o.invoice:
            total_revenue += o.invoice.net_revenue()
            total_paid += o.invoice.total_paid()
            total_owed += o.invoice.balance_due()

    return render_template(
        "clients/subsidiary_profile.html",
        subsidiary=sub, parent=parent, orders=orders,
        total_revenue=total_revenue, total_paid=total_paid, total_owed=total_owed
    )


@clients_bp.route("/<int:client_id>/subsidiaries.json")
def subsidiaries_json(client_id):
    subs = ClientSubsidiary.query.filter_by(parent_client_id=client_id).order_by(ClientSubsidiary.name).all()
    return jsonify([{"id": s.id, "name": s.name} for s in subs])

@clients_bp.route("/subsidiaries/edit/<int:subsidiary_id>", methods=["GET", "POST"])
def edit_subsidiary(subsidiary_id):
    sub = ClientSubsidiary.query.get_or_404(subsidiary_id)

    if request.method == "POST":
        sub.name = request.form.get("name", "").strip()
        sub.address = request.form.get("address", "").strip()
        sub.contact_info = request.form.get("contact_info", "").strip()
        sub.tax_number = request.form.get("tax_number", "").strip()
        sub.client_code = request.form.get("client_code", "").strip()

        if not sub.name:
            flash("Subsidiary name is required.")
            return redirect(url_for("clients.edit_subsidiary", subsidiary_id=sub.id))

        db.session.commit()
        flash(f"Subsidiary '{sub.name}' updated.")
        return redirect(url_for("clients.view_subsidiary_profile", subsidiary_id=sub.id))

    return render_template("clients/edit_subsidiary.html", subsidiary=sub)