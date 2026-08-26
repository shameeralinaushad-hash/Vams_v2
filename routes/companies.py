import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
from werkzeug.utils import secure_filename
from models import db, Company, DocSequence
from utils import validate_upload, ALLOWED_IMAGE_EXTENSIONS
from audit import log_action
from permissions import permission_required
from pdf_templates.theme_config import THEMES, THEME_DISPLAY_NAMES

companies_bp = Blueprint("companies", __name__, url_prefix="/companies")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _save_optional_image(file_storage, folder, filename_prefix, error_label):
    """Validates and saves an optional uploaded image. Returns the saved
    filename, or None if no file was submitted. Returns False (and flashes an
    error) if a file was submitted but failed validation, so the caller can
    bail out of the request."""
    if not file_storage or not file_storage.filename:
        return None
    if not validate_upload(file_storage, ALLOWED_IMAGE_EXTENSIONS):
        flash(f"{error_label} must be an image file (PNG, JPG, GIF, or WEBP).")
        return False
    filename = secure_filename(f"{filename_prefix}_{file_storage.filename}")
    file_storage.save(os.path.join(folder, filename))
    return filename


@companies_bp.route("/")
def list_companies():
    companies = Company.query.all()
    return render_template("companies/list.html", companies=companies)


@companies_bp.route("/<int:company_id>/profile")
def company_profile(company_id):
    company = Company.query.get_or_404(company_id)

    from models import Order, Invoice, Quotation, PurchaseOrder, DeliveryChallan
    order_count = Order.query.filter_by(company_id=company.id).count()
    invoice_count = Invoice.query.join(Order).filter(Order.company_id == company.id).count()
    quotation_count = Quotation.query.join(Order).filter(Order.company_id == company.id).count()
    po_count = PurchaseOrder.query.join(Order).filter(Order.company_id == company.id).count()
    challan_count = DeliveryChallan.query.join(Order).filter(Order.company_id == company.id).count()

    return render_template(
        "companies/profile.html", company=company,
        counts={
            "orders": order_count,
            "invoices": invoice_count,
            "quotations": quotation_count,
            "purchase_orders": po_count,
            "challans": challan_count,
        },
    )


@companies_bp.route("/add", methods=["GET", "POST"])
def add_company():
    if request.method == "POST":
        name = request.form["name"]
        address = request.form.get("address", "")
        tax_number = request.form.get("tax_number", "")
        bank_details = request.form.get("bank_details", "")
        phone = request.form.get("phone", "")
        email = request.form.get("email", "")
        designation = request.form.get("designation", "")
        short_name = request.form.get("short_name", "")
        location_code = request.form.get("location_code", "")
        authorized_name = request.form.get("authorized_name", "")
        pdf_theme = request.form.get("pdf_theme", "default")
        entity_type = request.form.get("entity_type", "")
        status = request.form.get("status", "")
        formation_date = _parse_date(request.form.get("formation_date", ""))
        ein = request.form.get("ein", "")
        registered_agent = request.form.get("registered_agent", "")

        letterhead_filename = _save_optional_image(
            request.files.get("letterhead"), current_app.config["LETTERHEAD_FOLDER"],
            f"{name}_letterhead", "Letterhead"
        )
        if letterhead_filename is False:
            return redirect(request.url)

        letterhead_footer_filename = _save_optional_image(
            request.files.get("letterhead_footer"), current_app.config["LETTERHEAD_FOLDER"],
            f"{name}_footer", "Letterhead footer"
        )
        if letterhead_footer_filename is False:
            return redirect(request.url)

        logo_filename = _save_optional_image(
            request.files.get("logo"), current_app.config["COMPANY_LOGO_FOLDER"],
            f"{name}_logo", "Company logo"
        )
        if logo_filename is False:
            return redirect(request.url)

        signature_filename = _save_optional_image(
            request.files.get("signature"), current_app.config["SIGNATURE_FOLDER"],
            f"{name}_signature", "Signature"
        )
        if signature_filename is False:
            return redirect(request.url)

        company = Company(
            name=name,
            address=address,
            tax_number=tax_number,
            bank_details=bank_details,
            letterhead_filename=letterhead_filename,
            letterhead_footer_filename=letterhead_footer_filename,
            logo_filename=logo_filename,
            authorized_name=authorized_name,
            signature_filename=signature_filename,
            short_name=short_name,
            location_code=location_code,
            pdf_theme=pdf_theme,
            phone=phone,
            email=email,
            designation=designation,
            entity_type=entity_type,
            status=status,
            formation_date=formation_date,
            ein=ein,
            registered_agent=registered_agent,
        )
        db.session.add(company)
        db.session.commit()

        for doc_type in ["quotation", "invoice", "challan"]:
            db.session.add(DocSequence(company_id=company.id, doc_type=doc_type))
        db.session.commit()

        return redirect(url_for("companies.list_companies"))

    return render_template("companies/add.html", theme_keys=list(THEMES.keys()), theme_names=THEME_DISPLAY_NAMES)


@companies_bp.route("/edit/<int:company_id>", methods=["GET", "POST"])
@permission_required("manage_companies")
def edit_company(company_id):
    company = Company.query.get_or_404(company_id)

    if request.method == "POST":
        company.name = request.form["name"]
        company.address = request.form.get("address", "")
        company.tax_number = request.form.get("tax_number", "")
        company.bank_details = request.form.get("bank_details", "")
        company.phone = request.form.get("phone", "")
        company.email = request.form.get("email", "")
        company.designation = request.form.get("designation", "")
        company.authorized_name = request.form.get("authorized_name", "")
        company.short_name = request.form.get("short_name", "")
        company.location_code = request.form.get("location_code", "")
        company.pdf_theme = request.form.get("pdf_theme", "default")
        company.entity_type = request.form.get("entity_type", "")
        company.status = request.form.get("status", "")
        company.formation_date = _parse_date(request.form.get("formation_date", ""))
        company.ein = request.form.get("ein", "")
        company.registered_agent = request.form.get("registered_agent", "")

        letterhead_filename = _save_optional_image(
            request.files.get("letterhead"), current_app.config["LETTERHEAD_FOLDER"],
            f"{company.name}_letterhead", "Letterhead"
        )
        if letterhead_filename is False:
            return redirect(request.url)
        if letterhead_filename:
            company.letterhead_filename = letterhead_filename

        letterhead_footer_filename = _save_optional_image(
            request.files.get("letterhead_footer"), current_app.config["LETTERHEAD_FOLDER"],
            f"{company.name}_footer", "Letterhead footer"
        )
        if letterhead_footer_filename is False:
            return redirect(request.url)
        if letterhead_footer_filename:
            company.letterhead_footer_filename = letterhead_footer_filename

        logo_filename = _save_optional_image(
            request.files.get("logo"), current_app.config["COMPANY_LOGO_FOLDER"],
            f"{company.name}_logo", "Company logo"
        )
        if logo_filename is False:
            return redirect(request.url)
        if logo_filename:
            company.logo_filename = logo_filename

        signature_filename = _save_optional_image(
            request.files.get("signature"), current_app.config["SIGNATURE_FOLDER"],
            f"{company.name}_signature", "Signature"
        )
        if signature_filename is False:
            return redirect(request.url)
        if signature_filename:
            company.signature_filename = signature_filename

        db.session.commit()
        flash("Company updated.")
        return redirect(url_for("companies.list_companies"))

    return render_template("companies/edit.html", company=company, theme_keys=list(THEMES.keys()), theme_names=THEME_DISPLAY_NAMES)


@companies_bp.route("/delete/<int:company_id>", methods=["POST"])
@permission_required("manage_companies")
def delete_company(company_id):
    company = Company.query.get_or_404(company_id)

    from models import Order
    order_count = Order.query.filter_by(company_id=company.id).count()
    if order_count > 0:
        flash(f"Cannot delete '{company.name}' — it has {order_count} order(s) linked to it. Remove or reassign those first.")
        return redirect(url_for("companies.list_companies"))

    if session.get("active_company_id") == company.id:
        session.pop("active_company_id", None)
        session.pop("active_company_name", None)

    company_name = company.name
    for seq in list(company.doc_sequences):
        db.session.delete(seq)
    db.session.delete(company)
    db.session.commit()

    log_action("delete_company", "Company", company_id, f"Deleted company {company_name}")

    flash("Company deleted.")
    return redirect(url_for("companies.list_companies"))

@companies_bp.route("/switch/<int:company_id>")
def switch_company(company_id):
    company = Company.query.get_or_404(company_id)
    session["active_company_id"] = company.id
    session["active_company_name"] = company.name
    return redirect(request.referrer or url_for("home"))