import os
from flask import Blueprint, send_file, abort, current_app
from flask_login import login_required

pdf_view_bp = Blueprint("pdf_view", __name__, url_prefix="/pdf")


@pdf_view_bp.route("/view/<path:relative_path>")
@login_required
def view_pdf(relative_path):
    static_root = os.path.join(current_app.root_path, "static")
    full_path = os.path.normpath(os.path.join(static_root, relative_path))

    # Prevent path traversal outside the static folder
    if not full_path.startswith(static_root) or not full_path.lower().endswith(".pdf"):
        abort(404)

    if not os.path.exists(full_path):
        abort(404)

    response = send_file(full_path, mimetype="application/pdf", as_attachment=False, conditional=True)
    response.headers["Content-Disposition"] = f'inline; filename="{os.path.basename(full_path)}"'
    return response