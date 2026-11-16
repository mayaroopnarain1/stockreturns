# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.datasource import data
from api.deps import MAX_COMPARE, clean_horizon, clean_rf, clean_tickers
from api.serialize import to_jsonable
from api.services.common import ServiceError
from api.services.compare import build_compare
from utils.prescription import INVESTOR_PROFILES

router = APIRouter()


class CompareRequest(BaseModel):
    tickers: list[str] = Field(min_length=2)
    horizon: str = "1y"
    rf: float = 0.05
    benchmark: bool = True
    profile: str = "Balanced"


@router.post("/compare")
def compare(req: CompareRequest) -> JSONResponse:
    tickers = clean_tickers(req.tickers, limit=MAX_COMPARE, minimum=2)
    if req.profile not in INVESTOR_PROFILES:
        raise HTTPException(status_code=422, detail=f"Unknown profile: {req.profile!r}")
    try:
        result = build_compare(tickers, clean_horizon(req.horizon), clean_rf(req.rf),
                               req.benchmark, req.profile, data)
    except ServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return JSONResponse(to_jsonable(result))
