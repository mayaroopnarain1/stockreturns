# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.datasource import data
from api.deps import MAX_WATCHLIST, clean_ticker
from api.serialize import to_jsonable
from api.services.watchlist import build_status

router = APIRouter()


class WatchItem(BaseModel):
    ticker: str
    target_price: Optional[float] = None
    added_date: Optional[str] = None
    notes: str = Field(default="", max_length=500)


class StatusRequest(BaseModel):
    items: list[WatchItem] = Field(default_factory=list, max_length=MAX_WATCHLIST)


class ValidateRequest(BaseModel):
    ticker: str


@router.post("/watchlist/status")
def status(req: StatusRequest) -> JSONResponse:
    items = []
    for it in req.items:
        d = it.model_dump()
        d["ticker"] = clean_ticker(it.ticker)
        items.append(d)
    return JSONResponse(to_jsonable(build_status(items, data)))


@router.post("/watchlist/validate")
def validate(req: ValidateRequest) -> JSONResponse:
    """Same check the Streamlit page uses: the ticker must resolve to a real company/ETF."""
    t = clean_ticker(req.ticker)
    info = data.get_ticker_info(t) or {}
    ok = bool(info) and bool(info.get("symbol") or info.get("shortName"))
    return JSONResponse({"ticker": t, "valid": ok,
                         "name": info.get("shortName") or info.get("longName")})
