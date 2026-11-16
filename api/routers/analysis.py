# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.datasource import data
from api.deps import clean_rf, clean_ticker, VALID_HORIZONS
from api.serialize import to_jsonable
from api.services import analysis as A
from api.services import analysis_fund as F
from api.services.common import ServiceError

router = APIRouter(prefix="/analysis")


def _params(horizon: str, start: Optional[str], end: Optional[str], profile: str,
            rf: float, outlier_z: float, rolling: int) -> A.Params:
    if horizon != "custom" and horizon not in VALID_HORIZONS:
        raise HTTPException(status_code=422, detail=f"Invalid horizon: {horizon!r}")
    if rolling not in (21, 30, 60):
        raise HTTPException(status_code=422, detail="Rolling window must be 21, 30 or 60.")
    if not (2.0 <= outlier_z <= 4.0):
        raise HTTPException(status_code=422, detail="Outlier threshold must be between 2 and 4.")
    return A.Params(horizon=horizon, start=start, end=end, profile=profile,
                    rf=clean_rf(rf), outlier_z=outlier_z, rolling=rolling)


def _ctx(ticker, horizon, start, end, profile, rf, outlier_z, rolling) -> A.Context:
    p = _params(horizon, start, end, profile, rf, outlier_z, rolling)
    try:
        return A.load_context(data, clean_ticker(ticker), p)
    except A.TickerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _respond(payload) -> JSONResponse:
    return JSONResponse(to_jsonable(payload))


@router.get("/{ticker}/overview")
def overview(ticker: str, horizon: str = "1y", start: Optional[str] = None, end: Optional[str] = None,
             profile: str = "Balanced", rf: float = 0.05, outlier_z: float = 3.0, rolling: int = 30):
    return _respond(A.overview(_ctx(ticker, horizon, start, end, profile, rf, outlier_z, rolling)))


@router.get("/{ticker}/fundamentals")
def fundamentals(ticker: str, context: bool = False, horizon: str = "1y", start: Optional[str] = None,
                 end: Optional[str] = None, profile: str = "Balanced", rf: float = 0.05,
                 outlier_z: float = 3.0, rolling: int = 30):
    return _respond(F.fundamentals(_ctx(ticker, horizon, start, end, profile, rf, outlier_z, rolling), context))


@router.get("/{ticker}/financials")
def financials(ticker: str, freq: str = "annual", horizon: str = "1y", start: Optional[str] = None,
               end: Optional[str] = None, profile: str = "Balanced", rf: float = 0.05,
               outlier_z: float = 3.0, rolling: int = 30):
    if freq not in ("annual", "quarterly"):
        raise HTTPException(status_code=422, detail="freq must be annual or quarterly")
    return _respond(F.financials(_ctx(ticker, horizon, start, end, profile, rf, outlier_z, rolling), freq))


@router.get("/{ticker}/technicals")
def technicals(ticker: str, horizon: str = "1y", start: Optional[str] = None, end: Optional[str] = None,
               profile: str = "Balanced", rf: float = 0.05, outlier_z: float = 3.0, rolling: int = 30):
    return _respond(A.technicals(_ctx(ticker, horizon, start, end, profile, rf, outlier_z, rolling)))


@router.get("/{ticker}/risk")
def risk(ticker: str, horizon: str = "1y", start: Optional[str] = None, end: Optional[str] = None,
         profile: str = "Balanced", rf: float = 0.05, outlier_z: float = 3.0, rolling: int = 30):
    return _respond(A.risk(_ctx(ticker, horizon, start, end, profile, rf, outlier_z, rolling)))


@router.get("/{ticker}/events")
def events(ticker: str, relative: bool = False, horizon: str = "1y", start: Optional[str] = None,
           end: Optional[str] = None, profile: str = "Balanced", rf: float = 0.05,
           outlier_z: float = 3.0, rolling: int = 30):
    ctx = _ctx(ticker, horizon, start, end, profile, rf, outlier_z, rolling)
    return _respond({**A.events(ctx, relative), "seasonality": A.seasonality(ctx)})
