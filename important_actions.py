"""Computed Important Actions queue for the dashboard hero.

Actions are derived on each page load from live subsystem data (no stored
queue). A snoozed action is filtered out via the `ActionSnooze` table: each
action carries a stable (source, source_id) key that dismissal endpoints use
to hide it until its snooze window passes.
"""

from datetime import date, datetime, timedelta
from flask import url_for

# Team tasks assigned to the current user are surfaced as deadlines when they
# are due within this many days (or are already overdue).
TASK_DUE_WINDOW_DAYS = 1

# Default snooze window for the dismiss endpoint.
DEFAULT_SNOOZE_HOURS = 24


def _issue_time_label(age_days):
    if age_days <= 0:
        return "just now"
    return f"{age_days} day(s) ago"


def _deadline_time_label(days_until):
    if days_until < 0:
        return f"overdue by {-days_until} day(s)"
    if days_until == 0:
        return "due today"
    return f"due in {days_until} day(s)"


def build_actions(*, company_id, overdue_invoices, pending, no_quotation_orders,
                  team_tasks, snooze_keys, today=None, now=None):
    """Assemble + sort the Important Actions list.

    `snooze_keys` is a set of (source, source_id) tuples still inside their
    snooze window; those actions are excluded. `team_tasks` are open tasks
    assigned to the current user's employee (status to_do/in_progress, not
    archived) — filtered here to the due window.
    """
    today = today or date.today()
    actions = []

    # --- Critical issue: invoices overdue 30+ days ---
    if overdue_invoices:
        total_overdue = sum(inv.balance_due() for inv in overdue_invoices)
        oldest_days = max(inv.days_overdue() for inv in overdue_invoices)
        actions.append({
            "type": "issue", "severity": "critical", "source": "overdue_invoices",
            "source_id": None, "overdue": True,
            "title": f"{len(overdue_invoices)} invoice(s) overdue 30+ days — {total_overdue:,.2f} outstanding",
            "link": url_for("payments.list_payments"),
            "time_label": f"oldest {oldest_days} day(s) overdue",
            "_sort": (0, 0, 0),
        })

    # --- Normal issues ---
    if pending:
        oldest_days = max(((today - (o.inquiry_date or today)).days, 0)[0]
                          for o in pending)
        actions.append({
            "type": "issue", "severity": "normal", "source": "pending_po",
            "source_id": None, "overdue": False,
            "title": f"{len(pending)} order(s) still awaiting PO",
            "link": url_for("orders.list_orders", status="Pending"),
            "time_label": _issue_time_label(oldest_days),
            "_sort": (1, 1, -oldest_days),
        })
    if no_quotation_orders:
        oldest_days = max(((today - (o.inquiry_date or today)).days, 0)[0]
                          for o in no_quotation_orders)
        actions.append({
            "type": "issue", "severity": "normal", "source": "no_quotation",
            "source_id": None, "overdue": False,
            "title": f"{len(no_quotation_orders)} order(s) have no quotation yet",
            "link": url_for("orders.list_orders", status="Pending"),
            "time_label": _issue_time_label(oldest_days),
            "_sort": (1, 1, -oldest_days),
        })

    # --- Deadlines: open assigned team tasks due within the window ---
    for task in team_tasks:
        due = task.due_date
        if not due:
            continue
        days_until = (due - today).days
        if days_until > TASK_DUE_WINDOW_DAYS:
            continue
        key = ("team_task", task.id)
        if key in snooze_keys:
            continue
        actions.append({
            "type": "deadline", "severity": "critical" if days_until < 0 else "normal",
            "source": "team_task", "source_id": task.id, "overdue": days_until < 0,
            "title": f"Task due: {task.title}",
            "link": url_for("tasks.team_tasks"),
            "time_label": _deadline_time_label(days_until),
            "_sort": (0 if days_until < 0 else 1, 0, (due - today).days),
        })

    # Filter snoozed issues (deadlines already checked above).
    for key in ("overdue_invoices", "pending_po", "no_quotation"):
        if (key, None) in snooze_keys:
            actions = [a for a in actions if not (a["source"] == key and a["source_id"] is None)]

    actions.sort(key=lambda a: a["_sort"])
    for a in actions:
        a.pop("_sort", None)
    return actions
