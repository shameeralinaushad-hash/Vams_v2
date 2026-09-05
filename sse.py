"""
Server-Sent Events (SSE) manager for VAMS live updates.

Supports two backends:
  - Redis Pub/Sub (default when REDIS_URL is set): cross-worker safe, required for multi-worker uvicorn.
  - In-memory (fallback): single-worker only, no external dependencies.

Routes call push_event() to broadcast to all connected clients in a company.
Generators yield SSE-formatted messages for connected clients.
"""
import json
import os
import asyncio
import itertools
import threading
from queue import Queue, Empty

import redis as _redis

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_redis_url = os.environ.get("REDIS_URL", "")
_max_queue_size = 50  # backpressure: drop stale events for slow clients
_keepalive_interval = 5  # seconds between keepalive checks

# ---------------------------------------------------------------------------
# Thread-safe event ID counter
# ---------------------------------------------------------------------------
_event_counter = itertools.count(1)

# ---------------------------------------------------------------------------
# Redis backend (cross-worker safe)
# ---------------------------------------------------------------------------
_redis_client = None
_redis_pubsub = None
_use_redis = False


def _get_redis():
    """Lazily initialize the Redis client (singleton)."""
    global _redis_client, _use_redis
    if _redis_client is not None:
        return _redis_client
    if not _redis_url:
        return None
    try:
        _redis_client = _redis.from_url(_redis_url, decode_responses=True)
        _redis_client.ping()
        _use_redis = True
        return _redis_client
    except Exception:
        _redis_client = None
        _use_redis = False
        return None


# ---------------------------------------------------------------------------
# In-memory backend (single-worker fallback)
# ---------------------------------------------------------------------------
_connections = {}  # {company_id: [{queue, user_id}]}
_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Redis subscriber thread (one per worker process)
# ---------------------------------------------------------------------------
_subscriber_thread = None
_local_queues = []  # list of (company_id, queue) for this worker


def _start_redis_subscriber():
    """Start a background thread that subscribes to Redis and forwards
    messages to local per-client queues."""
    global _subscriber_thread
    if _subscriber_thread is not None:
        return
    r = _get_redis()
    if r is None:
        return

    def _listener():
        pubsub = r.pubsub()
        pubsub.psubscribe("vams:sse:*")
        for msg in pubsub.listen():
            if msg["type"] != "pmessage":
                continue
            channel = msg["channel"]  # e.g. "vams:sse:42"
            try:
                company_id = int(channel.split(":")[-1])
            except (ValueError, IndexError):
                continue
            data = msg["data"]
            # Forward to all local queues for this company
            with _lock:
                for cid, q in _local_queues:
                    if cid == company_id:
                        try:
                            q.put_nowait(data)
                        except Exception:
                            pass

    _subscriber_thread = threading.Thread(target=_listener, daemon=True)
    _subscriber_thread.start()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register(company_id, user_id):
    """Register a new SSE client connection. Returns its entry dict."""
    q = Queue(maxsize=_max_queue_size)
    entry = {"queue": q, "user_id": user_id}

    if _use_redis or _get_redis():
        _start_redis_subscriber()
        with _lock:
            _local_queues.append((company_id, q))
    else:
        with _lock:
            _connections.setdefault(company_id, []).append(entry)

    return entry


def unregister(company_id, entry):
    """Remove a client connection on disconnect."""
    if _use_redis:
        q = entry["queue"]
        with _lock:
            try:
                _local_queues.remove((company_id, q))
            except ValueError:
                pass
    else:
        with _lock:
            conns = _connections.get(company_id, [])
            try:
                conns.remove(entry)
            except ValueError:
                pass


def push_event(company_id, event_type, data=None):
    """Push an event to all connected clients in a company."""
    event_id = next(_event_counter)
    payload = json.dumps({"type": event_type, "data": data or {}})
    msg = f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"

    if _use_redis or _get_redis():
        # Publish to Redis — all workers receive it
        try:
            r = _get_redis()
            if r:
                r.publish(f"vams:sse:{company_id}", msg)
                return
        except Exception:
            pass
    # Fallback: in-memory broadcast (single-worker only)
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
                msg = q.get(timeout=_keepalive_interval)
                yield msg
            except Empty:
                # Keepalive: only send comment, do NOT query DB on every timeout
                yield ": keepalive\n\n"
    except GeneratorExit:
        pass
    finally:
        unregister(company_id, entry)


async def async_event_stream(company_id, user_id, request=None):
    """Async SSE generator for FastAPI — uses asyncio.Queue for thread-free operation."""
    global _flask_app

    # Use an asyncio.Queue bridged from the sync Queue
    asyncio_q = asyncio.Queue(maxsize=_max_queue_size)
    entry = register(company_id, user_id)
    sync_q = entry["queue"]

    # Bridge thread → async: poll sync_q and put into asyncio_q
    async def _bridge():
        loop = asyncio.get_event_loop()
        while True:
            try:
                msg = await loop.run_in_executor(None, lambda: sync_q.get(timeout=1))
                await asyncio_q.put(msg)
            except Empty:
                pass
            except Exception:
                break

    bridge_task = asyncio.create_task(_bridge())

    last_count = None
    try:
        with _flask_app.app_context():
            count = _get_unread_count(user_id)
        last_count = count
        yield f"event: notification\ndata: {json.dumps({'count': count})}\n\n"

        while True:
            try:
                msg = await asyncio.wait_for(asyncio_q.get(), timeout=_keepalive_interval)
                yield msg
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except GeneratorExit:
        pass
    finally:
        bridge_task.cancel()
        unregister(company_id, entry)


# Flask app context holder (set by asgi.py)
_flask_app = None
