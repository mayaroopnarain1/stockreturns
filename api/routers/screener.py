# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.datasource import data
from api.serialize import to_jsonable
from api.services import screener

router = APIRouter()


@router.get("/screener")
def get_screener() -> JSONResponse:
    """Full universe when ready; otherwise starts the build and reports progress."""
    snap = screener.snapshot()
    if snap["status"] in ("idle", "error"):
        screener.start(data)
        snap = screener.snapshot()
    return JSONResponse(to_jsonable(snap))


@router.get("/screener/status")
def status() -> JSONResponse:
    return JSONResponse(to_jsonable(screener.snapshot(include_rows=False)))


@router.post("/screener/refresh")
def refresh() -> JSONResponse:
    started = screener.start(data, force=True)
    return JSONResponse(to_jsonable({"started": started, **screener.snapshot(include_rows=False)}))
