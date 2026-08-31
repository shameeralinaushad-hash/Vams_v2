"""
VAMS ASGI entry point.

FastAPI serves as the outer shell. Flask is mounted inside via WSGIMiddleware.
SSE endpoints are native async — no threads consumed.
"""
from fastapi import FastAPI, Request, Query
from fastapi.responses import StreamingResponse
from a2wsgi import WSGIMiddleware
import logging

from app import create_app
import sse

logger = logging.getLogger(__name__)

flask_app = create_app()
sse._flask_app = flask_app  # Give SSE module access to Flask app context
app = FastAPI(title="VAMS", docs_url=None, redoc_url=None)

# FastAPI routes FIRST — they take precedence over the Flask mount below


@app.get("/api/events")
async def web_sse(
    request: Request,
    company: int = Query(None),
    user: int = Query(None),
):
    """SSE endpoint for web clients (auth via query params)."""
    if not company or not user:
        from fastapi.responses import JSONResponse
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
