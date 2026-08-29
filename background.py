"""
Background task helpers for VAMS.
Run long-running tasks (PDF generation, API calls) in daemon threads
so they don't block the request/response cycle.
"""
import threading
import logging

logger = logging.getLogger(__name__)


def run_in_background(func, *args, **kwargs):
    """Run a function in a daemon thread. Fire-and-forget.

    Usage:
        run_in_background(generate_quotation_pdf, company, client, quotation, items, path)
    """
    def wrapper():
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception("Background task failed: %s", func.__name__)

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return t
