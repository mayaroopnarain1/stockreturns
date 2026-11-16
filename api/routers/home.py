# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.datasource import data
from api.deps import MAX_WATCHLIST, clean_tickers
from api.serialize import to_jsonable
from api.services.home import build_home

router = APIRouter()


@router.get("/home")
def home() -> JSONResponse:
    return JSONResponse(to_jsonable(build_home(data)))


class QuotesRequest(BaseModel):
    tickers: list[str]


@router.post("/quotes")
def quotes(req: QuotesRequest) -> JSONResponse:
    tickers = clean_tickers(req.tickers, limit=MAX_WATCHLIST)
    df = data.get_daily_changes(tuple(tickers)) if tickers else None
    rows = []
    if df is not None and not df.empty:
        for t in tickers:
            if t in df.index:
                r = df.loc[t]
                rows.append({"ticker": t, "price": float(r["price"]),
                             "change_pct": float(r["change_pct"])})
    return JSONResponse(to_jsonable({"quotes": rows}))
