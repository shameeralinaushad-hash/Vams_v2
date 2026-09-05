"""
Background task helpers for VAMS.
Run long-running tasks (PDF generation, API calls) in a bounded thread pool
so they don't block the request/response cycle and don't spawn unlimited threads.
"""
import threading
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Bounded pool: max 4 concurrent background tasks (PDF gen, ML extraction, etc.)
_pdf_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-worker")


def run_in_background(func, *args, _app=None, **kwargs):
    """Run a function in a bounded thread pool. Fire-and-forget.

    Usage:
        run_in_background(generate_quotation_pdf, company, client, quotation, items, path)
        run_in_background(fn, _app=current_app._get_current_object())
    """
    def wrapper():
        try:
            if _app:
                with _app.app_context():
                    func(*args, **kwargs)
            else:
                func(*args, **kwargs)
        except Exception:
            logger.exception("Background task failed: %s", func.__name__)

    return _pdf_pool.submit(wrapper)
