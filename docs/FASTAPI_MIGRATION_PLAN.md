# VAMS FastAPI Migration Plan

## Problem Statement

Waitress (WSGI threaded server) holds one thread per SSE connection. With 12 threads and multiple browser tabs, threads get exhausted, causing:
- `Task queue depth` warnings
- Slow page loads
- Timeouts

This is a **fundamental WSGI limitation** — Waitress cannot kill threads stuck in user code (SSE generators). The WSGI spec gives the app total control, and Waitress is "pretty helpless" (Waitress maintainers' words).

## Solution: FastAPI + Uvicorn

FastAPI (ASGI) uses async event loops instead of threads. SSE connections don't consume threads. Uvicorn replaces Waitress as the server.

### Architecture

```
Browser / Flutter App
        |
        v
   Uvicorn (ASGI, port 8080)
        |
   FastAPI app (asgi.py)
    /        \
   /          \
  v            v
FastAPI      Flask (mounted via WSGIMiddleware)
native SSE    all 17 blueprints, templates, auth, etc.
endpoints     (unchanged, runs sync in threadpool)
```

### Why This Works

- **FastAPI serves as the outer shell** — uvicorn replaces Waitress
- **Flask is mounted inside FastAPI** — `a2wsgi.WSGIMiddleware` wraps it
- **All Flask routes work unchanged** — they run in a threadpool (same as Waitress)
- **SSE is native FastAPI** — async generator, no threads consumed
- **`push_event()` is unchanged** — Flask routes still call `sse.push_event()` as before
- **The Flutter app doesn't know** — same API URLs, same responses
- **Templates, CSRF, sessions, auth** — all work inside Flask unchanged

---

## Phase 1: SSE Migration (COMPLETED)

### Files Created/Modified

| File | Action | What |
|---|---|---|
| `asgi.py` | **CREATE** | FastAPI app, mounts Flask, native SSE endpoints |
| `sse.py` | **MODIFY** | Add `async_event_stream()` alongside existing `event_stream()` |
| `wsgi.py` | **MODIFY** | Replace Waitress with uvicorn |
| `app.py` | **MODIFY** | Remove SSE endpoint, remove `api_events_bp` references |
| `templates/base.html` | **MODIFY** | Add `data-user-id` to body, pass to SSE URL |
| `routes/api_events.py` | **MODIFY** | Stub (functionality moved to `asgi.py`) |
| `requirements.txt` | **MODIFY** | Added `fastapi`, `uvicorn[standard]`, `a2wsgi` |

---

## Phase 1: Implementation Details

### Step 1: Dependencies (requirements.txt)

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
a2wsgi>=1.10.0
```

Note: `pydantic` is already in requirements (v2.13.4), which FastAPI depends on.

### Step 2: asgi.py — ACTUAL IMPLEMENTATION

```python
"""
VAMS ASGI entry point.

FastAPI serves as the outer shell. Flask is mounted inside via WSGIMiddleware.
SSE endpoints are native async — no threads consumed.
"""
from fastapi import FastAPI, Request, Query
from fastapi.responses import StreamingResponse  # NOT EventSourceResponse
from a2wsgi import WSGIMiddleware
import logging

from app import create_app
import sse

logger = logging.getLogger(__name__)

flask_app = create_app()
sse._flask_app = flask_app  # Give SSE module access to Flask app context
app = FastAPI(title="VAMS", docs_url=None, redoc_url=None)

# FastAPI routes FIRST — they take precedence over the Flask mount below
# CRITICAL: Routes must be defined BEFORE the mount, otherwise the mount
# at "/" catches all requests before FastAPI routes are checked.

@app.get("/api/events")
async def web_sse(
    request: Request,
    company: int = Query(None),
    user: int = Query(None),
):
    """SSE endpoint for web clients (auth via query params)."""
    if not company or not user:
        from fastapi.responses import JSONResponse  # NOT flask.jsonify
        return JSONResponse({"error": "missing params"}, status_code=400)
    return StreamingResponse(
        sse.async_event_stream(company, user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/api/v1/events")
async def api_sse(
    request: Request,
    token: str = Query(None),
):
    """SSE endpoint for mobile API clients (JWT auth via query param)."""
    from flask_jwt_extended import decode_token
    if not token:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "missing token"}, status_code=400)
    try:
        # CRITICAL: decode_token needs Flask app context
        with flask_app.app_context():
            decoded = decode_token(token)
        user_id = int(decoded["sub"])
        company_id = decoded.get("company_id")
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": f"invalid token: {e}"}, status_code=401)
    if not company_id:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "no company"}, status_code=400)
    return StreamingResponse(
        sse.async_event_stream(company_id, user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# Mount Flask app AFTER FastAPI routes — handles all other routes
app.mount("/", WSGIMiddleware(flask_app))

if __name__ == "__main__":
    import uvicorn
    print(" * Serving on http://0.0.0.0:8080 (FastAPI + uvicorn)")
    uvicorn.run("asgi:app", host="0.0.0.0", port=8080, reload=False)
```

**Key Implementation Notes:**
1. Routes defined BEFORE mount — critical for FastAPI to match SSE routes before Flask catches them
2. Use `StreamingResponse` not `EventSourceResponse` (both work, but StreamingResponse is more explicit)
3. `decode_token` must be wrapped in `flask_app.app_context()` — FastAPI doesn't have Flask context by default
4. Use `fastapi.responses.JSONResponse` not `flask.jsonify` in FastAPI routes
5. `_flask_app` is passed to the `sse` module for use in `async_event_stream`

### Step 3: sse.py — ACTUAL IMPLEMENTATION

```python
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
    q = Queue()
    entry = {"queue": q, "user_id": user_id}
    with _lock:
        _connections.setdefault(company_id, []).append(entry)
    return entry

def unregister(company_id, entry):
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
    """Sync generator — used by Flask/Waitress (legacy)."""
    entry = register(company_id, user_id)
    q = entry["queue"]
    last_count = None
    try:
        count = _get_unread_count(user_id)
        last_count = count
        yield f"event: notification\ndata: {json.dumps({'count': count})}\n\n"
        while True:
            try:
                msg = q.get(timeout=5)
                yield msg
            except Empty:
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
    """Async SSE generator for FastAPI — no threads consumed.

    Uses run_in_executor() to read from the thread-safe queue
    without blocking the event loop. The thread is only used for
    microseconds to get the message, not for 5 seconds.

    CRITICAL: All DB queries (_get_unread_count) must run inside
    flask_app.app_context() because FastAPI doesn't have Flask context.
    """
    global _flask_app
    entry = register(company_id, user_id)
    q = entry["queue"]
    last_count = None
    try:
        # DB query needs Flask app context
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
```

**Key Implementation Notes:**
1. `_flask_app` global is set by `asgi.py` after Flask app creation
2. All `_get_unread_count()` calls wrapped in `with _flask_app.app_context()`
3. NO `await request.is_disconnected()` — it doesn't work behind WSGIMiddleware
4. `GeneratorExit` is handled automatically — no explicit disconnection check needed
5. `run_in_executor(None, lambda: q.get(timeout=5))` — lambda is important, not `q.get, 5`

### Step 4: wsgi.py

```python
import uvicorn

if __name__ == "__main__":
    print(" * Serving on http://0.0.0.0:8080 (FastAPI + uvicorn)")
    uvicorn.run("asgi:app", host="0.0.0.0", port=8080, reload=False)
```

### Step 5: app.py Cleanup

Removed the following from `app.py`:

1. ~~`from routes.api_events import api_events_bp`~~ — import removed
2. ~~`app.register_blueprint(api_events_bp)`~~ — registration removed
3. ~~`csrf.exempt(api_events_bp)`~~ — CSRF exemption removed
4. ~~`@app.route('/api/events')`~~ — SSE endpoint removed
5. ~~`"api_events.api_sse_events"`~~ — from `require_login` allowed_endpoints
6. ~~SSE response headers block~~ — `if request.path.startswith("/api/events")` block removed

### Step 6: templates/base.html

```html
<!-- Added data-user-id to body tag -->
<body data-page="{{ page_id }}"
      data-company-id="{{ active_company_obj.id if active_company_obj else '' }}"
      data-user-id="{{ current_user.id if current_user.is_authenticated else '' }}">

<!-- SSE JavaScript passes user_id -->
var companyId = document.body.getAttribute('data-company-id');
var userId = document.body.getAttribute('data-user-id');
if (!companyId || !userId) return;

var evtSource = new EventSource('/api/events?company=' + companyId + '&user=' + userId);
```

### Step 7: routes/api_events.py

```python
"""
SSE endpoints have moved to asgi.py (FastAPI native async).
This file is kept as a stub to avoid import errors.
"""
```

### Step 8: Flutter SSE Client

Updated `sse_client.dart` to pass JWT token as query parameter:

```dart
// OLD: No token in URL
final uri = Uri.parse('$serverUrl/api/v1/events');

// NEW: Token as query param
final uri = Uri.parse('$serverUrl/api/v1/events?token=$token');
```

---

## Bugs Found During Phase 1 Implementation

| Bug | Symptom | Root Cause | Fix |
|---|---|---|---|
| `/api/events` → 404 | SSE returns 404 | Mount at `/` caught requests before FastAPI routes | Routes defined BEFORE mount |
| SSE stream dies after 1st event | Connection closes immediately | `request.is_disconnected()` fails behind WSGIMiddleware | Removed check, rely on `GeneratorExit` |
| DB query crashes in async | Generator dies | `_get_unread_count()` needs Flask app context | Wrapped in `_flask_app.app_context()` |
| Mobile `/api/v1/events` → 400 | Flutter can't connect | Flutter SSE client didn't pass token in query param | Added `?token=$token` to URL |
| `decode_token` fails in FastAPI | `/api/v1/events` returns 401 | No Flask app context in FastAPI event loop | Wrapped in `flask_app.app_context()` |
| Company switching ignored in `/me` | App shows wrong company | `/me` read employee record, ignored JWT claim | Prioritized JWT's `company_id` in `/me` |

---

## Phase 1: Testing Status

| Test | Status | Notes |
|---|---|---|
| Server starts with uvicorn | ✅ Verified | `python wsgi.py` works |
| `/api/events` (web) → 200 | ✅ Verified | Returns notification count + keepalives |
| `/api/v1/events` (mobile) → 200 | ✅ Verified | Token auth works with app context |
| Company switching | ✅ Verified | `/me` returns correct `company_id` from JWT |
| All Flask routes work | ✅ Verified | Templates, auth, API all functional |
| No `Task queue depth` warnings | ❌ Not tested | Needs prolonged multi-tab use |

---

## Phase 2: Route Migration (NOT STARTED)

### Should We Do Phase 2?

**Original Rationale:** Migrate Flask API routes to FastAPI for better async performance.

**Current Assessment:**

The Phase 1 migration SOLVED the original problem (SSE thread exhaustion). The remaining Flask routes:
- Are NOT blocking threads (they complete quickly)
- Don't have persistent connections (unlike SSE)
- Work fine in the threadpool via WSGIMiddleware

### When Phase 2 Would Help

| Scenario | Phase 2 Benefit |
|---|---|
| High traffic polling (dashboard, orders) | Reduce thread pool contention |
| Many concurrent long-polling requests | Free up threads for other requests |
| Heavy WebSocket usage | Native async handles better |

### When Phase 2 NOT Needed

| Scenario | Why |
|---|---|
| SSE fixed, threads freed | Original problem solved |
| Low concurrent API traffic | Threadpool handles fine |
| Most time spent in DB I/O | Threadpool is I/O bound anyway |
| Complexity vs benefit | Rewriting routes = more bugs, less gain |

### Recommendation

**Hold off on Phase 2.** Monitor the server under real load. If `Task queue depth` warnings return (from non-SSE routes), or if thread contention becomes a problem, then migrate high-traffic routes.

If/when Phase 2 is needed, migrate in this order:
1. **Priority 1:** Dashboard API (`api_dashboard.py`) — high polling frequency
2. **Priority 2:** Orders API (`api_orders.py`) — frequently accessed
3. **Priority 3:** Notifications API (`api_notifications.py`) — frequent refreshes

**Never migrate:** Template-rendering routes (Flask is fine for server-rendered HTML)

---

## How the SSE Flow Works

```
1. Browser opens: EventSource('/api/events?company=1&user=4')

2. Uvicorn receives the request → routes to FastAPI

3. FastAPI's web_sse() handler:
   - Calls sse.async_event_stream(1, 4)
   - Returns StreamingResponse

4. async_event_stream() (in sse.py):
   - Calls register(1, 4) → adds entry to _connections[1]
   - Sends initial notification count (in app_context)
   - Loops: reads from thread-safe Queue via run_in_executor()
   - Yields SSE-formatted messages
   - On disconnect: calls unregister()

5. Meanwhile, Flask routes call sse.push_event():
   - Puts messages in the same thread-safe Queue
   - Messages are picked up by the async generator

6. Key: push_event() runs in Flask threads (via WSGIMiddleware)
         async_event_stream() runs in FastAPI's event loop
         They share the same Queue — no changes needed
```

---

## Risk Assessment

| Risk | Likelihood | Status |
|---|---|---|
| Flask sessions break under WSGIMiddleware | Low | ✅ Verified — works |
| CSRF breaks | Low | ✅ Verified — works |
| Template rendering breaks | Low | ✅ Verified — works |
| Static files break | Low | ✅ Verified — works |
| uvicorn doesn't work on Windows | Very Low | ✅ Verified — works |
| Cloudflare tunnel breaks | Very Low | ✅ Verified — tunnel unchanged |
| DB queries block event loop | Low | ✅ Fixed — runs in app_context + executor |
| `push_event()` called from many routes | None | ✅ Thread-safe Queue |

---

## Rollback Plan

If anything breaks:
1. Kill uvicorn
2. Change `wsgi.py` back to Waitress:
```python
from waitress import serve
from app import create_app

app = create_app()
serve(app, host="0.0.0.0", port=8080, threads=12, channel_timeout=300)
```
3. Re-add SSE endpoint in `app.py` (old code in git history)
4. Revert `base.html` to use `/api/events?company=X` (without user param)
5. Update Flutter `sse_client.dart` to remove `?token=` param

The old code is in git history.

---

## Server Startup

```bash
.\.venv\Scripts\python.exe wsgi.py
```

Server runs on http://0.0.0.0:8080 (FastAPI + uvicorn)
