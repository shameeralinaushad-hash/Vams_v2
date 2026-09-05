import uvicorn
import os

if __name__ == "__main__":
    workers = int(os.environ.get("UVICORN_WORKERS", 4))
    print(f" * Serving on http://0.0.0.0:8080 (FastAPI + uvicorn, {workers} workers)")
    uvicorn.run("asgi:app", host="0.0.0.0", port=8080, reload=False, workers=workers)
