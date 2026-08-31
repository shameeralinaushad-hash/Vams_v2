"""
Server-Sent Events (SSE) manager for VAMS live updates.

Routes call push_event() to broadcast to all connected clients in a company.
Generators yield SSE-formatted messages for connected clients.
"""
import json
import asyncio
import threading
from queue import Queue, Empty

_connections = {}   # {company_id: [{queue, user_id}]}
_lock = threading.Lock()
_event_id = 0
_flask_app = None  # Set by asgi.py after creating the Flask app


def register(company_id, user_id):
    """Register a new SSE client connection. Returns its entry dict."""
    q = Queue()
    entry = {"queue": q, "user_id": user_id}
    with _lock:
        _connections.setdefault(company_id, []).append(entry)
    return entry


def unregister(company_id, entry):
    """Remove a client connection on disconnect."""
    with _lock:
        conns = _connections.get(company_id, [])
        try:
            conns.remove(entry)
        except ValueError:
            pass


def push_event(company_id, event_type, data=None):
    """Push an event to all connected clients in a company."""
    global _event_id
    _event_id += 1
    payload = json.dumps({"type": event_type, "data": data or {}})
    msg = f"id: {_event_id}\nevent: {event_type}\ndata: {payload}\n\n"
    with _lock:
        for entry in _connections.get(company_id, []):
            try:
                entry["queue"].put_nowait(msg)
            except Exception:
                pass


def _get_unread_count(user_id):
    """Query unread notification count for a user."""
    from models import Notification
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()


def event_stream(company_id, user_id):
    """Generator that yields SSE-formatted messages for a connected client."""
    entry = register(company_id, user_id)
    q = entry["queue"]
    last_count = None
    try:
        # Send current unread count immediately on connect
        count = _get_unread_count(user_id)
        last_count = count
        yield f"event: notification\ndata: {json.dumps({'count': count})}\n\n"

        while True:
            try:
                msg = q.get(timeout=5)
                yield msg
            except Empty:
                # Keepalive: check if notification count changed
                try:
                    count = _get_unread_count(user_id)
                except Exception:
                    count = last_count
                if count != last_count:
                    last_count = count
                    yield f"event: notification\ndata: {json.dumps({'count': count})}\n\n"
                else:
                    yield ": keepalive\n\n"
    except GeneratorExit:
        pass
    finally:
        unregister(company_id, entry)


async def async_event_stream(company_id, user_id, request=None):
    """Async SSE generator for FastAPI — no threads consumed."""
    global _flask_app
    entry = register(company_id, user_id)
    q = entry["queue"]
    last_count = None
    try:
        with _flask_app.app_context():
            count = _get_unread_count(user_id)
        last_count = count
        yield f"event: notification\ndata: {json.dumps({'count': count})}\n\n"

        while True:
            try:
                msg = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=5)
                )
                yield msg
            except Empty:
                try:
                    with _flask_app.app_context():
                        count = _get_unread_count(user_id)
                except Exception:
                    count = last_count
                if count != last_count:
                    last_count = count
                    yield f"event: notification\ndata: {json.dumps({'count': count})}\n\n"
                else:
                    yield ": keepalive\n\n"
    except GeneratorExit:
        pass
    finally:
        unregister(company_id, entry)
