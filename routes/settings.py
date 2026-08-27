from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_required
from routes.auth import admin_required
from routes.maintenance import is_maintenance_mode_on
from models import db, MailConfig, CustomField, Company
from email_utils import send_email

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

QUOTATION_COLUMNS = [
    {"key": "sr", "label": "Sr. No"},
    {"key": "part_no", "label": "Part No/Code"},
    {"key": "nomenclature", "label": "Nomenclature"},
    {"key": "unit", "label": "A/U (Unit)"},
    {"key": "qty", "label": "Qty"},
    {"key": "price", "label": "Unit Price"},
    {"key": "gst", "label": "GST"},
    {"key": "total", "label": "Total"},
]


def get_active_company_or_flash():
    company_id = session.get("active_company_id")
    company = db.session.get(Company, company_id) if company_id else None
    if not company:
        flash("Select an active company first.")
    return company


@settings_bp.route("/")
@login_required
@admin_required
def view_settings():
    maintenance_on = is_maintenance_mode_on(current_app)
    current_message = None
    if maintenance_on:
        try:
            with open(current_app.config["MAINTENANCE_FLAG_PATH"], "r", encoding="utf-8") as f:
                current_message = f.read().strip()
        except OSError:
            current_message = None

    # Mail config
    mail_cfg = MailConfig.query.first()
    if not mail_cfg:
        mail_cfg = MailConfig(is_enabled=False)
        db.session.add(mail_cfg)
        db.session.commit()

    # Custom fields + PDF columns
    company_id = session.get("active_company_id")
    company = db.session.get(Company, company_id) if company_id else None
    custom_fields = []
    current_columns = None
    if company:
        custom_fields = CustomField.query.filter_by(
            company_id=company.id, doc_type="quotation"
        ).order_by(CustomField.sort_order.asc(), CustomField.id.asc()).all()
        if company.pdf_columns:
            current_columns = company.pdf_columns.get("quotation")

    return render_template(
        "settings/index.html",
        maintenance_on=maintenance_on,
        current_message=current_message,
        mail_cfg=mail_cfg,
        company=company,
        custom_fields=custom_fields,
        all_columns=QUOTATION_COLUMNS,
        current_columns=current_columns,
    )


@settings_bp.route("/mail", methods=["GET", "POST"])
@login_required
@admin_required
def mail_settings():
    cfg = MailConfig.query.first()
    if not cfg:
        cfg = MailConfig(is_enabled=False)
        db.session.add(cfg)
        db.session.commit()

    if request.method == "POST":
        cfg.smtp_server = request.form.get("smtp_server", "").strip()
        cfg.smtp_port = int(request.form.get("smtp_port", 587))
        cfg.smtp_username = request.form.get("smtp_username", "").strip()
        pwd = request.form.get("smtp_password", "")
        if pwd:
            cfg.smtp_password = pwd
        cfg.use_tls = request.form.get("use_tls") == "on"
        cfg.from_email = request.form.get("from_email", "").strip()
        cfg.from_name = request.form.get("from_name", "").strip()
        cfg.is_enabled = request.form.get("is_enabled") == "on"

        # Google OAuth credentials
        cfg.google_client_id = request.form.get("google_client_id", "").strip()
        gsecret = request.form.get("google_client_secret", "")
        if gsecret:
            cfg.google_client_secret = gsecret

        db.session.commit()
        flash("Mail settings saved.")
        return redirect(url_for("settings.view_settings") + "#mail")

    return render_template("settings/mail.html", cfg=cfg)


@settings_bp.route("/mail/test", methods=["POST"])
@login_required
@admin_required
def test_mail():
    to_email = request.form.get("test_email", "").strip()
    if not to_email:
        flash("Enter a test email address.")
        return redirect(url_for("settings.mail_settings"))
    ok = send_email("Test from VAMS", "This is a test email from VAMS Business System. If you see this, SMTP is working.", [to_email])
    if ok:
        flash(f"Test email sent to {to_email}.")
    else:
        flash("Failed to send test email. Check your SMTP settings.", "error")
    return redirect(url_for("settings.view_settings") + "#mail")


@settings_bp.route("/custom-fields", methods=["GET", "POST"])
@login_required
@admin_required
def custom_fields():
    company = get_active_company_or_flash()
    if not company:
        return redirect(url_for("companies.list_companies"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        field_type = request.form.get("field_type", "text")
        if name:
            max_order = db.session.query(db.func.max(CustomField.sort_order)).filter_by(
                company_id=company.id, doc_type="quotation"
            ).scalar() or 0
            field = CustomField(
                company_id=company.id, doc_type="quotation",
                name=name, field_type=field_type,
                is_active=True, sort_order=max_order + 1,
            )
            db.session.add(field)
            db.session.commit()
            flash(f"Custom field '{name}' added.")
        else:
            flash("Field name is required.", "error")
        return redirect(url_for("settings.view_settings") + "#custom-fields")

    fields = CustomField.query.filter_by(company_id=company.id, doc_type="quotation").order_by(
        CustomField.sort_order.asc(), CustomField.id.asc()
    ).all()
    return render_template("settings/custom_fields.html", company=company, fields=fields)


@settings_bp.route("/custom-fields/<int:field_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_custom_field(field_id):
    field = CustomField.query.get_or_404(field_id)
    company = db.session.get(Company, session.get("active_company_id")) if session.get("active_company_id") else None
    if not company or field.company_id != company.id:
        flash("Field not found in the active company.", "error")
        return redirect(url_for("settings.custom_fields"))
    db.session.delete(field)
    db.session.commit()
    flash(f"Custom field '{field.name}' deleted.")
    return redirect(url_for("settings.view_settings") + "#custom-fields")


@settings_bp.route("/custom-fields/<int:field_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_custom_field(field_id):
    field = CustomField.query.get_or_404(field_id)
    company = db.session.get(Company, session.get("active_company_id")) if session.get("active_company_id") else None
    if not company or field.company_id != company.id:
        flash("Field not found in the active company.", "error")
        return redirect(url_for("settings.custom_fields"))
    field.is_active = not field.is_active
    db.session.commit()
    flash(f"Custom field '{field.name}' is now {'active' if field.is_active else 'inactive'}.")
    return redirect(url_for("settings.view_settings") + "#custom-fields")


@settings_bp.route("/pdf-builder", methods=["GET", "POST"])
@login_required
@admin_required
def pdf_builder():
    company = get_active_company_or_flash()
    if not company:
        return redirect(url_for("companies.list_companies"))

    if request.method == "POST":
        selected = request.form.getlist("column")
        ordered = request.form.getlist("column_order")
        valid_keys = {c["key"] for c in QUOTATION_COLUMNS}
        selected = [k for k in selected if k in valid_keys]
        if ordered:
            ordered = [k for k in ordered if k in valid_keys and k in selected]
            ordered += [k for k in selected if k not in ordered]
            selected = ordered

        if not selected:
            company.pdf_columns = None
        else:
            config = company.pdf_columns or {}
            config["quotation"] = selected
            company.pdf_columns = config
        db.session.commit()
        flash("PDF column layout saved for the active company.")
        return redirect(url_for("settings.view_settings") + "#pdf-builder")

    current_columns = None
    if company.pdf_columns:
        current_columns = company.pdf_columns.get("quotation")
    return render_template(
        "settings/pdf_builder.html",
        company=company, all_columns=QUOTATION_COLUMNS, current_columns=current_columns,
    )