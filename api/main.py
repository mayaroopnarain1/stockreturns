# -*- coding: utf-8 -*-
"""
StockLens API + static front end.

Run locally:   STOCKLENS_BACKEND=api uvicorn api.main:app --reload
Fake data:     STOCKLENS_FAKE_DATA=1 STOCKLENS_BACKEND=api uvicorn api.main:app
"""

from __future__ import annotations

import os

# The API never needs Streamlit; make utils.* pick the framework-free cache.
os.environ.setdefault("STOCKLENS_BACKEND", "api")

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.deps import RateLimiter
from api.serialize import to_jsonable
from api.services.meta import build_meta

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="StockLens API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
_limiter = RateLimiter(limit=int(os.environ.get("STOCKLENS_RATE_LIMIT", "240")), window=60.0)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path != "/api/health" and not _limiter.allow(client_ip(request)):
        return JSONResponse({"detail": "Too many requests — slow down."}, status_code=429)
    response = await call_next(request)
    if path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "fake_data": os.environ.get("STOCKLENS_FAKE_DATA") == "1"}


@app.get("/api/meta")
def meta() -> JSONResponse:
    return JSONResponse(to_jsonable(build_meta()))


def _include_routers() -> None:
    """Routers are registered as they are implemented."""
    import importlib

    for name in ("home", "watchlist", "analysis", "screener", "compare", "portfolio"):
        try:
            mod = importlib.import_module(f"api.routers.{name}")
        except ModuleNotFoundError as exc:
            if exc.name == f"api.routers.{name}":
                continue
            raise
        app.include_router(mod.router, prefix="/api")


_include_routers()

if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
