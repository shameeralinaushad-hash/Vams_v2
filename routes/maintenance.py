import os
from flask import Blueprint, current_app, redirect, url_for, flash, request
from flask_login import login_required, current_user
from routes.auth import admin_required
from audit import log_action

maintenance_bp = Blueprint("maintenance", __name__, url_prefix="/admin/maintenance")

def is_maintenance_mode_on(app):
    return os.path.exists(app.config["MAINTENANCE_FLAG_PATH"])

# --- NEW ROUTE ---
@maintenance_bp.route("/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_maintenance():
    # 'on' is the value sent by the checkbox when checked
    is_on = request.form.get("maintenance_on") == "on"
    message = request.form.get("message", "").strip()
    flag_path = current_app.config["MAINTENANCE_FLAG_PATH"]

    if is_on:
        # Enable Logic
        os.makedirs(os.path.dirname(flag_path), exist_ok=True)
        with open(flag_path, "w", encoding="utf-8") as f:
            f.write(message or "We'll be back online shortly.")
        log_action("enable_maintenance", "System", None, f"Maintenance mode enabled by {current_user.email}")
        flash("Maintenance mode is ON. Users will see the maintenance page.")
    else:
        # Disable Logic
        if os.path.exists(flag_path):
            os.remove(flag_path)
        log_action("disable_maintenance", "System", None, f"Maintenance mode disabled by {current_user.email}")
        flash("Maintenance mode is OFF. The app is live for everyone again.")

    return redirect(url_for("settings.view_settings"))