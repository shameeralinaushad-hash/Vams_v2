from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import current_user

# (permission_key, human-readable label shown as a checkbox on the Edit User page)
AVAILABLE_PERMISSIONS = [
    ("delete_orders", "Delete Orders"),
    ("delete_documents", "Delete Quotations, Invoices & Delivery Challans"),
    ("cancel_invoices", "Cancel / Reactivate Invoices"),
    ("issue_credit_notes", "Issue Credit Notes"),
    ("delete_payments", "Delete Logged Payments"),
    ("manage_companies", "Edit / Delete Companies"),
    ("delete_clients", "Delete Clients"),
    ("manage_expenses", "Delete Expenses"),
    ("manage_numbering", "Edit Client Document Numbering"),
]


def permission_required(perm_key):
    """Gate a route behind a specific permission. Admins always pass (they
    implicitly have every permission); staff need it explicitly granted via
    the Edit User page. Managing users themselves is intentionally NOT
    delegable through this system -- that stays admin-only via
    @admin_required, so a staff member can never grant themselves more
    access than they were given."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if not current_user.has_permission(perm_key):
                flash("You don't have permission to do that. Ask an admin if you need access.")
                return redirect(request.referrer or url_for("home"))
            return f(*args, **kwargs)
        return decorated
    return decorator