# -*- coding: utf-8 -*-
"""
EDGAR-backed implementations of the fetchers that ``utils/data.py`` exposes.

The return shapes mirror the yfinance versions exactly so downstream pages
and ``utils/financials.py`` work without modification.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from . import edgar_client, ticker_cik, xbrl_concepts
from .errors import ProviderNotCovered
from .xbrl_concepts import YFINANCE_ROW_LABEL


# Canonical fields to surface on each statement. Keep limited to what
# ``utils/financials.py`` knows how to consume plus a couple of raw lines
# useful to the Stock Analysis statements viewer.

INCOME_FIELDS = (
    "revenue", "cost_of_revenue", "gross_profit", "operating_income",
    "pretax_income", "tax_expense", "interest_expense", "net_income",
    "diluted_eps",
)
BALANCE_FIELDS = (
    "total_assets", "current_assets", "cash", "accounts_receivable", "inventory",
    "total_liabilities", "current_liabilities", "long_term_debt", "short_term_debt",
    "equity", "shares_outstanding",
)
CASHFLOW_FIELDS = ("operating_cf", "capex")


def _fetch_companyfacts(symbol: str) -> dict[str, Any]:
    cik = ticker_cik.ticker_to_cik(symbol)
    url = edgar_client.companyfacts_url(cik)
    payload = edgar_client.get_json(url, ttl_seconds=edgar_client.COMPANYFACTS_TTL_SECONDS)
    if not isinstance(payload, dict) or "facts" not in payload:
        raise ProviderNotCovered(f"No XBRL facts for {symbol} (CIK {cik})")
    return payload


def _series_to_frame(
    facts: dict[str, Any],
    fields: tuple[str, ...],
    freq: str,
) -> pd.DataFrame:
    """Build a DataFrame with yfinance-style row labels and period-end columns.

    Columns are period-end Timestamps, sorted oldest → newest. Missing
    line items get an all-NaN row so downstream alias lookups behave the
    same way they do with yfinance data.
    """
    # Collect per-field series keyed by period end.
    series_by_field: dict[str, dict[pd.Timestamp, float]] = {}
    all_ends: set[pd.Timestamp] = set()
    for field in fields:
        rows = xbrl_concepts.resolve_series(facts, field, freq=freq)
        if not rows:
            series_by_field[field] = {}
            continue
        per_end: dict[pd.Timestamp, float] = {}
        for r in rows:
            end = r.get("end")
            val = r.get("val")
            if end is None or val is None:
                continue
            try:
                ts = pd.Timestamp(end)
            except Exception:
                continue
            per_end[ts] = float(val)
            all_ends.add(ts)
        series_by_field[field] = per_end

    if not all_ends:
        return pd.DataFrame()

    ordered_ends = sorted(all_ends)
    index = [YFINANCE_ROW_LABEL.get(f, f) for f in fields]
    data = {ts: [] for ts in ordered_ends}
    for field in fields:
        per_end = series_by_field[field]
        for ts in ordered_ends:
            data[ts].append(per_end.get(ts))

    df = pd.DataFrame(data, index=index)
    return df


def get_financials(symbol: str, freq: str = "annual") -> dict:
    """EDGAR-backed ``get_financials``. Shape matches the yfinance version."""
    facts_payload = _fetch_companyfacts(symbol)
    facts = facts_payload.get("facts", {})

    income = _series_to_frame(facts, INCOME_FIELDS, freq)
    balance = _series_to_frame(facts, BALANCE_FIELDS, freq)
    cashflow = _series_to_frame(facts, CASHFLOW_FIELDS, freq)

    # yfinance reports CapEx as a negative cash outflow; XBRL reports the
    # payment as a positive number. Flip sign so ``utils/financials.py``'s
    # FCF = OCF + CapEx arithmetic stays correct.
    capex_label = YFINANCE_ROW_LABEL["capex"]
    if capex_label in cashflow.index:
        cashflow.loc[capex_label] = -cashflow.loc[capex_label].astype(float)

    # Derive Free Cash Flow so downstream code's "Free Cash Flow" alias hits.
    ocf_label = YFINANCE_ROW_LABEL["operating_cf"]
    if ocf_label in cashflow.index and capex_label in cashflow.index:
        ocf = pd.to_numeric(cashflow.loc[ocf_label], errors="coerce")
        cap = pd.to_numeric(cashflow.loc[capex_label], errors="coerce").fillna(0)
        cashflow.loc["Free Cash Flow"] = ocf + cap

    # Derive Total Debt if the filer tags only the short/long components.
    lt_label = YFINANCE_ROW_LABEL["long_term_debt"]
    st_label = YFINANCE_ROW_LABEL["short_term_debt"]
    if lt_label in balance.index or st_label in balance.index:
        lt = (pd.to_numeric(balance.loc[lt_label], errors="coerce")
              if lt_label in balance.index else pd.Series(0, index=balance.columns))
        st = (pd.to_numeric(balance.loc[st_label], errors="coerce")
              if st_label in balance.index else pd.Series(0, index=balance.columns))
        balance.loc["Total Debt"] = lt.fillna(0) + st.fillna(0)

    if income.empty and balance.empty and cashflow.empty:
        # No usable XBRL — let the chain fall through.
        raise ProviderNotCovered(f"No resolvable statement concepts for {symbol}")

    return {"income": income, "balance": balance, "cashflow": cashflow}


def get_dividends(symbol: str, period: str = "5y") -> pd.Series:
    """Return declared dividends per share, indexed by declaration period end."""
    facts_payload = _fetch_companyfacts(symbol)
    facts = facts_payload.get("facts", {})

    rows = xbrl_concepts.resolve_series(facts, "dividends_per_share_declared", freq="annual")
    if not rows:
        rows = xbrl_concepts.resolve_series(facts, "dividends_per_share_cash_paid", freq="annual")
    if not rows:
        raise ProviderNotCovered(f"No dividend concept tagged for {symbol}")

    idx = []
    vals = []
    for r in rows:
        end = r.get("end")
        val = r.get("val")
        if end is None or val is None or float(val) <= 0:
            continue
        try:
            idx.append(pd.Timestamp(end))
            vals.append(float(val))
        except Exception:
            continue

    if not idx:
        raise ProviderNotCovered(f"Dividend facts present but empty for {symbol}")

    s = pd.Series(vals, index=pd.DatetimeIndex(idx).tz_localize(None)).sort_index()

    # Apply period filter to match the yfinance API's semantics loosely.
    if period and period.endswith("y"):
        try:
            years = int(period[:-1])
            cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.DateOffset(years=years)
            s = s[s.index >= cutoff]
        except Exception:
            pass
    return s


def get_earnings_dates(symbol: str) -> pd.DataFrame:
    """Return historical earnings-release dates inferred from 10-K/10-Q filings.

    Only the ``Reported EPS`` column is populated (from ``EarningsPerShareDiluted``);
    the ``EPS Estimate`` and ``Surprise(%)`` columns are emitted as NaN since
    EDGAR doesn't carry consensus estimates.
    """
    facts_payload = _fetch_companyfacts(symbol)
    facts = facts_payload.get("facts", {})

    submissions_url = edgar_client.submissions_url(
        ticker_cik.ticker_to_cik(symbol)
    )
    submissions = edgar_client.get_json(submissions_url, ttl_seconds=edgar_client.SUBMISSIONS_TTL_SECONDS)

    # Map accession number -> filing date from the submissions "recent" table.
    recent = (submissions.get("filings", {}) or {}).get("recent", {})
    accns = recent.get("accessionNumber", []) or []
    filing_dates = recent.get("filingDate", []) or []
    forms = recent.get("form", []) or []
    accn_to_filed: dict[str, str] = {}
    for accn, fd, form in zip(accns, filing_dates, forms):
        if form in ("10-K", "10-Q"):
            accn_to_filed[str(accn)] = str(fd)

    rows = xbrl_concepts.resolve_series(facts, "diluted_eps", freq="quarterly")
    if not rows:
        rows = xbrl_concepts.resolve_series(facts, "net_income", freq="quarterly")
    if not rows:
        raise ProviderNotCovered(f"No EPS/NI facts for {symbol}")

    records = []
    for r in rows:
        filed = r.get("filed") or accn_to_filed.get(str(r.get("accn", "")))
        if not filed:
            continue
        try:
            dt = pd.Timestamp(filed)
        except Exception:
            continue
        records.append({
            "date": dt,
            "Reported EPS": float(r["val"]) if "val" in r and r["val"] is not None else float("nan"),
            "period_end": pd.Timestamp(r.get("end")) if r.get("end") else pd.NaT,
        })

    if not records:
        raise ProviderNotCovered(f"No filing dates for {symbol} earnings")

    df = pd.DataFrame(records).drop_duplicates(subset=["period_end"]).set_index("date")
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    df["EPS Estimate"] = float("nan")
    df["Surprise(%)"] = float("nan")
    df = df[["EPS Estimate", "Reported EPS", "Surprise(%)"]].sort_index()
    return df
