# -*- coding: utf-8 -*-
"""Turn pandas/numpy results into plain JSON-safe structures (NaN/inf -> None)."""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

import numpy as np
import pandas as pd


def _num(v: float) -> float | None:
    f = float(v)
    return None if (math.isnan(f) or math.isinf(f)) else f


def iso(ts: Any) -> str:
    """ISO date (YYYY-MM-DD) for timestamps; timezone dropped."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_localize(None)
    return t.strftime("%Y-%m-%d")


def series_xy(s: pd.Series) -> dict:
    """Series -> {"x": [labels], "y": [values]} (index rendered as dates when datetime-like)."""
    if s is None or len(s) == 0:
        return {"x": [], "y": []}
    if isinstance(s.index, pd.DatetimeIndex):
        xs = [iso(i) for i in s.index]
    else:
        xs = [str(i) for i in s.index]
    return {"x": xs, "y": [None if pd.isna(v) else _num(v) for v in s.astype(float).values]}


def frame_records(df: pd.DataFrame, index_name: str | None = None) -> list[dict]:
    """DataFrame -> list of row dicts; the index is included when ``index_name`` is given."""
    if df is None or df.empty:
        return []
    out = []
    for idx, row in df.iterrows():
        rec = {} if index_name is None else {index_name: to_jsonable(idx)}
        for k, v in row.items():
            rec[str(k)] = to_jsonable(v)
        out.append(rec)
    return out


def to_jsonable(obj: Any) -> Any:
    """Recursively convert to JSON-safe types."""
    if obj is None:
        return None
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return _num(obj)
    if isinstance(obj, str):
        return obj
    if obj is pd.NaT:
        return None
    if isinstance(obj, (pd.Timestamp, dt.datetime, dt.date)):
        return iso(obj)
    if isinstance(obj, pd.Series):
        return series_xy(obj)
    if isinstance(obj, pd.DataFrame):
        return {
            "index": [to_jsonable(i) for i in obj.index],
            "columns": [str(c) for c in obj.columns],
            "data": [[to_jsonable(v) for v in row] for row in obj.itertuples(index=False)],
        }
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return str(obj)
