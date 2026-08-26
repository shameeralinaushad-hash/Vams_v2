import os
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
from werkzeug.utils import secure_filename
from models import db, CompanyDocument
from utils import validate_upload, ALLOWED_COMPANY_DOC_EXTENSIONS
from audit import log_action

company_documents_bp = Blueprint("company_documents", __name__, url_prefix="/company-documents")


@company_documents_bp.route("/")
def list_documents():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    documents = CompanyDocument.query.filter_by(company_id=company_id).order_by(CompanyDocument.uploaded_at.desc()).all()
    return render_template("company_documents/list.html", documents=documents)


@company_documents_bp.route("/add", methods=["POST"])
def add_document():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    title = request.form.get("title", "").strip()
    file = request.files.get("document_file")

    if not title or not file or not file.filename:
        flash("Please provide a title and select a file.")
        return redirect(url_for("company_documents.list_documents"))

    if not validate_upload(file, ALLOWED_COMPANY_DOC_EXTENSIONS):
        flash("File must be a PDF, Word document, or image (JPG/PNG).")
        return redirect(url_for("company_documents.list_documents"))

    os.makedirs(current_app.config["COMPANY_DOCS_FOLDER"], exist_ok=True)
    filename = secure_filename(f"company{company_id}_{title}_{file.filename}")
    file.save(os.path.join(current_app.config["COMPANY_DOCS_FOLDER"], filename))

    doc = CompanyDocument(company_id=company_id, title=title, filename=filename)
    db.session.add(doc)
    db.session.commit()

    log_action("add_company_document", "CompanyDocument", doc.id, f"Uploaded document '{title}'")

    flash("Document uploaded.")
    return redirect(url_for("company_documents.list_documents"))


@company_documents_bp.route("/delete/<int:doc_id>", methods=["POST"])
def delete_document(doc_id):
    doc = CompanyDocument.query.get_or_404(doc_id)
    title = doc.title

    full_path = os.path.join(current_app.config["COMPANY_DOCS_FOLDER"], doc.filename)
    if os.path.exists(full_path):
        os.remove(full_path)

    db.session.delete(doc)
    db.session.commit()

    log_action("delete_company_document", "CompanyDocument", doc_id, f"Deleted document '{title}'")

    flash("Document deleted.")
    return redirect(url_for("company_documents.list_documents"))