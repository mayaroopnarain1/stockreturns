# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.datasource import data
from api.deps import MAX_PORTFOLIO, clean_horizon, clean_rf, clean_ticker
from api.serialize import to_jsonable
from api.services.common import ServiceError
from api.services.portfolio import build_portfolio

router = APIRouter()


class PortfolioRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=MAX_PORTFOLIO)
    weights: list[float] = Field(min_length=2, max_length=MAX_PORTFOLIO)
    horizon: str = "1y"
    rf: float = 0.05


@router.post("/portfolio")
def portfolio(req: PortfolioRequest) -> JSONResponse:
    tickers = [clean_ticker(t) for t in req.tickers]
    if len(set(tickers)) != len(tickers):
        raise HTTPException(status_code=422, detail="Duplicate tickers are not allowed.")
    try:
        result = build_portfolio(tickers, req.weights, clean_horizon(req.horizon), clean_rf(req.rf), data)
    except ServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return JSONResponse(to_jsonable(result))
