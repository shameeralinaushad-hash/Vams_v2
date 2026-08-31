import uvicorn

if __name__ == "__main__":
    print(" * Serving on http://0.0.0.0:8080 (FastAPI + uvicorn)")
    uvicorn.run("asgi:app", host="0.0.0.0", port=8080, reload=False)
