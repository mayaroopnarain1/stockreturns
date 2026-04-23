# -*- coding: utf-8 -*-
"""
Financial-statement-derived analytics.

Each public function takes the ``get_financials`` dict (``income``, ``balance``,
``cashflow`` DataFrames, oldest → newest columns) and returns a small
structured result that the Stock Analysis page renders. All functions are
resilient to missing line items — they return NaN in the per-period series
and flag missing inputs via the ``interpretation`` string rather than raising.

Analyses:
  1. DuPont ROE (3-step)
  2. Margin decomposition (gross / operating / pretax / net)
  3. ROIC — indirect NOPAT: (NI + Tax + Interest − NonOpIncome) × (1 − t)
  4. Revenue quality (growth, AR-to-revenue drift)
  5. Earnings quality (NI vs OCF divergence, effective tax stability)
  6. Accruals (Sloan ratio)
  7. FCF conversion (FCF / NI)
  8. Leverage & liquidity (ratios snapshot, latest period)

The quality_scorecard() function rolls the analyses into three pillar scores
(Profitability / Earnings Quality / Balance Sheet) for the tab-top banner.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Line-item lookup with aliases
# ---------------------------------------------------------------------------
# yfinance row labels drift between releases ("Total Revenue" vs "TotalRevenue";
# "Stockholders Equity" vs "Common Stock Equity"). We try each candidate in
# order and return the first match (case/space insensitive).

INCOME_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue":          ("Total Revenue", "TotalRevenue", "Revenue"),
    "cost_of_revenue":  ("Cost Of Revenue", "CostOfRevenue", "Reconciled Cost Of Revenue"),
    "gross_profit":     ("Gross Profit", "GrossProfit"),
    "operating_income": ("Operating Income", "OperatingIncome", "EBIT"),
    "ebitda":           ("EBITDA", "Normalized EBITDA"),
    "pretax_income":    ("Pretax Income", "PretaxIncome", "Income Before Tax"),
    "tax_expense":      ("Tax Provision", "Income Tax Expense", "TaxProvision"),
    "interest_expense": ("Interest Expense", "InterestExpense", "Interest Expense Non Operating"),
    "net_income":       ("Net Income", "NetIncome", "Net Income Common Stockholders"),
    "diluted_eps":      ("Diluted EPS", "DilutedEPS"),
}

BALANCE_ALIASES: dict[str, tuple[str, ...]] = {
    "total_assets":         ("Total Assets", "TotalAssets"),
    "current_assets":       ("Current Assets", "Total Current Assets"),
    "cash":                 ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments",
                             "Cash And Short Term Investments"),
    "accounts_receivable":  ("Accounts Receivable", "Receivables", "Net Receivables"),
    "inventory":            ("Inventory", "Inventories"),
    "total_liabilities":    ("Total Liabilities Net Minority Interest", "Total Liab", "Total Liabilities"),
    "current_liabilities":  ("Current Liabilities", "Total Current Liabilities"),
    "long_term_debt":       ("Long Term Debt", "LongTermDebt"),
    "short_term_debt":      ("Current Debt", "Short Long Term Debt", "ShortTermDebt", "Short Term Debt"),
    "total_debt":           ("Total Debt", "TotalDebt"),
    "equity":               ("Stockholders Equity", "Common Stock Equity", "Total Stockholder Equity"),
    "shares":               ("Share Issued", "Ordinary Shares Number", "Common Stock Shares Outstanding"),
}

CASHFLOW_ALIASES: dict[str, tuple[str, ...]] = {
    "operating_cf":  ("Operating Cash Flow", "Total Cash From Operating Activities",
                      "Cash Flow From Continuing Operating Activities"),
    "capex":         ("Capital Expenditure", "CapitalExpenditures", "Capital Expenditures"),
    "free_cf":       ("Free Cash Flow", "FreeCashFlow"),
}


def _series(df: pd.DataFrame, aliases: Iterable[str]) -> pd.Series:
    """Return the row matching any alias as a Series indexed by period.

    Match is case/whitespace-insensitive. Returns an all-NaN series shaped like
    ``df.columns`` if no alias matches, so downstream arithmetic never raises.
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    norm = {str(i).strip().lower(): i for i in df.index}
    for name in aliases:
        key = name.strip().lower()
        if key in norm:
            row = df.loc[norm[key]]
            return pd.to_numeric(row, errors="coerce")
    return pd.Series(np.nan, index=df.columns, dtype=float)


def _get(stmts: dict, statement: str, alias_key: str) -> pd.Series:
    aliases = {
        "income": INCOME_ALIASES,
        "balance": BALANCE_ALIASES,
        "cashflow": CASHFLOW_ALIASES,
    }[statement]
    return _series(stmts.get(statement, pd.DataFrame()), aliases[alias_key])


def _period_labels(stmts: dict) -> list[str]:
    """Return column labels (as strings) from whichever statement is populated."""
    for key in ("income", "balance", "cashflow"):
        df = stmts.get(key)
        if df is not None and not df.empty:
            return [pd.Timestamp(c).strftime("%Y-%m-%d") if not isinstance(c, str) else str(c)
                    for c in df.columns]
    return []


def _format_cols(cols) -> list[str]:
    """Stringify period-end values for use as DataFrame column labels."""
    return [
        pd.Timestamp(c).strftime("%Y-%m-%d") if not isinstance(c, str) else str(c)
        for c in cols
    ]


def _apply_labels(df: pd.DataFrame, stmts: dict) -> None:
    """Set ``df.columns`` using the statements' period-end labels.

    When all three statements share the same period axis (yfinance default,
    and the contract we now enforce in edgar_provider), this matches the
    prior behaviour. If a caller somehow produces a DataFrame whose columns
    diverge from the statements' axis (cross-statement arithmetic broadening
    the index), fall back to stringifying the DataFrame's own columns so we
    never crash on a ValueError.
    """
    stmt_labels = _period_labels(stmts)
    if len(stmt_labels) == df.shape[1]:
        df.columns = stmt_labels
    else:
        df.columns = _format_cols(df.columns)


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    """Element-wise division that returns NaN wherever the denominator is 0 or NaN."""
    num = num.astype(float)
    den = den.astype(float)
    out = num / den.replace(0, np.nan)
    return out


def _avg_two(series: pd.Series) -> pd.Series:
    """Rolling 2-period average — convention for denominators on flow/stock ratios."""
    return series.rolling(window=2, min_periods=1).mean()


def _latest(s: pd.Series):
    """Most recent non-NaN value, or NaN if none."""
    s = s.dropna()
    return s.iloc[-1] if len(s) else np.nan


def _pp(v: float) -> str:
    return f"{v*100:+.1f}pp" if pd.notna(v) else "—"


# ---------------------------------------------------------------------------
# 1. DuPont ROE (3-step)
# ---------------------------------------------------------------------------

def dupont_roe(stmts: dict) -> dict:
    """ROE = NetMargin × AssetTurnover × EquityMultiplier.

    Uses 2-period average assets and equity for the turnover and multiplier
    denominators to better match the flow-vs-stock mismatch.
    """
    rev = _get(stmts, "income", "revenue")
    ni = _get(stmts, "income", "net_income")
    assets = _get(stmts, "balance", "total_assets")
    equity = _get(stmts, "balance", "equity")

    avg_assets = _avg_two(assets)
    avg_equity = _avg_two(equity)

    net_margin = _safe_div(ni, rev)
    asset_turnover = _safe_div(rev, avg_assets)
    equity_multiplier = _safe_div(avg_assets, avg_equity)
    roe = net_margin * asset_turnover * equity_multiplier

    df = pd.DataFrame({
        "Net Margin":        net_margin,
        "Asset Turnover":    asset_turnover,
        "Equity Multiplier": equity_multiplier,
        "ROE":               roe,
    }).T
    _apply_labels(df, stmts)

    # Identify which factor explains latest ROE most.
    last = df.iloc[:, -1] if not df.empty else pd.Series(dtype=float)
    driver = "—"
    if pd.notna(last.get("ROE")):
        # Compare each component to its cross-firm neutral baseline:
        # margin 8%, turnover 0.6, leverage 2.0 (rough large-cap means).
        baselines = {"Net Margin": 0.08, "Asset Turnover": 0.6, "Equity Multiplier": 2.0}
        ratios = {k: (last[k] / v) if (pd.notna(last.get(k)) and v) else np.nan for k, v in baselines.items()}
        valid = {k: v for k, v in ratios.items() if pd.notna(v)}
        if valid:
            driver = max(valid, key=valid.get)

    return {
        "df": df,
        "latest_roe": last.get("ROE", np.nan),
        "driver": driver,
    }


# ---------------------------------------------------------------------------
# 2. Margin decomposition
# ---------------------------------------------------------------------------

def margin_decomposition(stmts: dict) -> dict:
    rev = _get(stmts, "income", "revenue")
    gp = _get(stmts, "income", "gross_profit")
    op = _get(stmts, "income", "operating_income")
    pre = _get(stmts, "income", "pretax_income")
    ni = _get(stmts, "income", "net_income")

    gm = _safe_div(gp, rev)
    om = _safe_div(op, rev)
    pm = _safe_div(pre, rev)
    nm = _safe_div(ni, rev)

    df = pd.DataFrame({
        "Gross margin":   gm,
        "Operating margin": om,
        "Pretax margin":  pm,
        "Net margin":     nm,
    }).T
    _apply_labels(df, stmts)

    # Biggest drop between consecutive stages in the latest period.
    biggest_leak = "—"
    if not df.empty:
        last = df.iloc[:, -1]
        stages = ["Gross margin", "Operating margin", "Pretax margin", "Net margin"]
        drops = {}
        for a, b in zip(stages, stages[1:]):
            if pd.notna(last.get(a)) and pd.notna(last.get(b)):
                drops[f"{a} → {b}"] = last[a] - last[b]
        if drops:
            biggest_leak = max(drops, key=drops.get)

    return {"df": df, "biggest_leak": biggest_leak}


# ---------------------------------------------------------------------------
# 3. ROIC — indirect NOPAT
# ---------------------------------------------------------------------------

def roic_analysis(stmts: dict, wacc_proxy: float = 0.09) -> dict:
    """ROIC = NOPAT / Invested Capital.

    NOPAT (indirect): (NetIncome + TaxExpense + InterestExpense − NonOperatingIncome)
                      × (1 − effectiveTaxRate)

    NonOperatingIncome is approximated as: PretaxIncome − OperatingIncome + InterestExpense
    (i.e. whatever sits between operating income and pretax income, stripped of
    the interest line we already added back). This lets us isolate operating
    profit even when yfinance doesn't carry a clean non-operating row.

    Invested Capital = TotalDebt + Equity − Cash, using 2-period averages.
    """
    ni = _get(stmts, "income", "net_income")
    tax = _get(stmts, "income", "tax_expense")
    interest = _get(stmts, "income", "interest_expense").fillna(0)
    pretax = _get(stmts, "income", "pretax_income")
    op = _get(stmts, "income", "operating_income")

    # NonOperatingIncome ≈ Pretax − Operating + Interest (interest already netted in)
    non_op = (pretax - op + interest).astype(float)

    eff_tax = _safe_div(tax, pretax).clip(lower=0, upper=0.6)
    nopat = (ni + tax + interest - non_op) * (1 - eff_tax)

    equity = _get(stmts, "balance", "equity")
    cash = _get(stmts, "balance", "cash").fillna(0)
    debt = _get(stmts, "balance", "total_debt")
    # Fallback: sum short + long if total not present
    if debt.isna().all():
        lt = _get(stmts, "balance", "long_term_debt").fillna(0)
        st = _get(stmts, "balance", "short_term_debt").fillna(0)
        debt = lt + st

    invested = debt + equity - cash
    avg_invested = _avg_two(invested)

    roic = _safe_div(nopat, avg_invested)

    df = pd.DataFrame({
        "NOPAT":             nopat,
        "Invested Capital":  avg_invested,
        "Effective tax rate": eff_tax,
        "ROIC":              roic,
    }).T
    _apply_labels(df, stmts)

    latest = _latest(roic)
    creates_value = None
    if pd.notna(latest):
        creates_value = bool(latest > wacc_proxy)

    return {
        "df": df,
        "latest_roic": latest,
        "wacc_proxy": wacc_proxy,
        "creates_value": creates_value,
    }


# ---------------------------------------------------------------------------
# 4. Revenue quality
# ---------------------------------------------------------------------------

def revenue_quality(stmts: dict) -> dict:
    rev = _get(stmts, "income", "revenue")
    ar = _get(stmts, "balance", "accounts_receivable")

    yoy = rev.pct_change()
    ar_to_rev = _safe_div(ar, rev)
    ar_growth = ar.pct_change()

    df = pd.DataFrame({
        "Revenue":           rev,
        "Revenue YoY":       yoy,
        "AR / Revenue":      ar_to_rev,
        "AR YoY":            ar_growth,
    }).T
    _apply_labels(df, stmts)

    # 3y CAGR if ≥4 periods of revenue
    cagr = np.nan
    rev_clean = rev.dropna()
    if len(rev_clean) >= 4 and rev_clean.iloc[-4] > 0:
        cagr = (rev_clean.iloc[-1] / rev_clean.iloc[-4]) ** (1/3) - 1

    # Warning: AR growing materially faster than revenue in the latest period
    ar_flag = False
    if len(yoy.dropna()) and len(ar_growth.dropna()):
        latest_rev_g = _latest(yoy)
        latest_ar_g = _latest(ar_growth)
        if pd.notna(latest_rev_g) and pd.notna(latest_ar_g):
            ar_flag = bool(latest_ar_g > latest_rev_g + 0.10)  # >10pp faster

    return {
        "df": df,
        "cagr_3y": cagr,
        "ar_outpacing_revenue": ar_flag,
        "latest_yoy": _latest(yoy),
    }


# ---------------------------------------------------------------------------
# 5. Earnings quality — NI vs OCF divergence
# ---------------------------------------------------------------------------

def earnings_quality(stmts: dict) -> dict:
    ni = _get(stmts, "income", "net_income")
    ocf = _get(stmts, "cashflow", "operating_cf")
    tax = _get(stmts, "income", "tax_expense")
    pretax = _get(stmts, "income", "pretax_income")

    gap_ratio = _safe_div(ocf - ni, ni.abs())
    eff_tax = _safe_div(tax, pretax).clip(lower=-0.5, upper=1.0)

    df = pd.DataFrame({
        "Net Income":        ni,
        "Operating Cash Flow": ocf,
        "(OCF − NI) / |NI|": gap_ratio,
        "Effective tax rate": eff_tax,
    }).T
    _apply_labels(df, stmts)

    tax_std = eff_tax.dropna().std() if eff_tax.dropna().size >= 2 else np.nan
    tax_unstable = bool(pd.notna(tax_std) and tax_std > 0.05)

    return {
        "df": df,
        "latest_gap": _latest(gap_ratio),
        "tax_std": tax_std,
        "tax_unstable": tax_unstable,
    }


# ---------------------------------------------------------------------------
# 6. Accruals — Sloan ratio
# ---------------------------------------------------------------------------

def accruals_analysis(stmts: dict) -> dict:
    """Sloan accrual ratio: (NI − OCF) / AvgAssets.

    High positive values suggest earnings are flattered by non-cash items —
    a documented negative predictor of future returns.
    """
    ni = _get(stmts, "income", "net_income")
    ocf = _get(stmts, "cashflow", "operating_cf")
    assets = _get(stmts, "balance", "total_assets")

    avg_assets = _avg_two(assets)
    sloan = _safe_div(ni - ocf, avg_assets)

    df = pd.DataFrame({"Sloan accrual ratio": sloan}).T
    _apply_labels(df, stmts)

    latest = _latest(sloan)
    band = "—"
    if pd.notna(latest):
        if latest < 0.05:
            band = "Clean"
        elif latest < 0.10:
            band = "Watch"
        else:
            band = "Red flag"

    return {"df": df, "latest": latest, "band": band}


# ---------------------------------------------------------------------------
# 7. FCF conversion
# ---------------------------------------------------------------------------

def fcf_conversion(stmts: dict) -> dict:
    ni = _get(stmts, "income", "net_income")
    ocf = _get(stmts, "cashflow", "operating_cf")
    capex = _get(stmts, "cashflow", "capex").fillna(0)
    fcf_reported = _get(stmts, "cashflow", "free_cf")

    # yfinance CapEx is typically negative (cash outflow); adding gives OCF−|CapEx|
    fcf_calc = ocf + capex
    fcf = fcf_reported.where(~fcf_reported.isna(), fcf_calc)

    ratio = _safe_div(fcf, ni)

    df = pd.DataFrame({
        "Net Income":  ni,
        "FCF":         fcf,
        "FCF / NI":    ratio,
    }).T
    _apply_labels(df, stmts)

    latest = _latest(ratio)
    return {"df": df, "latest": latest}


# ---------------------------------------------------------------------------
# 8. Leverage & liquidity (snapshot — latest period)
# ---------------------------------------------------------------------------

def leverage_liquidity(stmts: dict) -> dict:
    assets = _get(stmts, "balance", "total_assets")
    current_assets = _get(stmts, "balance", "current_assets")
    cash = _get(stmts, "balance", "cash")
    inventory = _get(stmts, "balance", "inventory").fillna(0)
    current_liab = _get(stmts, "balance", "current_liabilities")
    equity = _get(stmts, "balance", "equity")
    debt = _get(stmts, "balance", "total_debt")
    if debt.isna().all():
        lt = _get(stmts, "balance", "long_term_debt").fillna(0)
        st = _get(stmts, "balance", "short_term_debt").fillna(0)
        debt = lt + st

    ebitda = _get(stmts, "income", "ebitda")
    ebit = _get(stmts, "income", "operating_income")
    interest = _get(stmts, "income", "interest_expense").abs()

    d_to_e = _safe_div(debt, equity)
    d_to_a = _safe_div(debt, assets)
    net_debt = debt - cash.fillna(0)
    nd_to_ebitda = _safe_div(net_debt, ebitda)
    interest_cov = _safe_div(ebit, interest)

    current_ratio = _safe_div(current_assets, current_liab)
    quick_ratio = _safe_div(current_assets - inventory, current_liab)
    cash_ratio = _safe_div(cash, current_liab)

    metrics = {
        "Debt / Equity":       _latest(d_to_e),
        "Debt / Assets":       _latest(d_to_a),
        "Net Debt / EBITDA":   _latest(nd_to_ebitda),
        "Interest Coverage":   _latest(interest_cov),
        "Current Ratio":       _latest(current_ratio),
        "Quick Ratio":         _latest(quick_ratio),
        "Cash Ratio":          _latest(cash_ratio),
    }

    # Color bands (lower = better unless noted)
    bands = {
        "Debt / Equity":     _band_lower(metrics["Debt / Equity"], good=0.5, bad=1.5),
        "Debt / Assets":     _band_lower(metrics["Debt / Assets"], good=0.3, bad=0.6),
        "Net Debt / EBITDA": _band_lower(metrics["Net Debt / EBITDA"], good=2.0, bad=4.0),
        "Interest Coverage": _band_higher(metrics["Interest Coverage"], good=8.0, bad=3.0),
        "Current Ratio":     _band_higher(metrics["Current Ratio"], good=1.5, bad=1.0),
        "Quick Ratio":       _band_higher(metrics["Quick Ratio"], good=1.0, bad=0.5),
        "Cash Ratio":        _band_higher(metrics["Cash Ratio"], good=0.5, bad=0.2),
    }

    return {"metrics": metrics, "bands": bands}


def _band_lower(v, good, bad):
    if pd.isna(v):
        return "—"
    if v <= good:
        return "good"
    if v <= bad:
        return "fair"
    return "poor"


def _band_higher(v, good, bad):
    if pd.isna(v):
        return "—"
    if v >= good:
        return "good"
    if v >= bad:
        return "fair"
    return "poor"


# ---------------------------------------------------------------------------
# Rollup scorecard — three pillars
# ---------------------------------------------------------------------------

def _score_roic(v):
    if pd.isna(v):
        return np.nan
    # 0 → 0, 0.09 → 50, 0.20 → 100, clipped
    return float(np.clip(v / 0.20 * 100, 0, 100))


def _score_roe(v):
    if pd.isna(v):
        return np.nan
    return float(np.clip(v / 0.25 * 100, 0, 100))


def _score_net_margin(v):
    if pd.isna(v):
        return np.nan
    return float(np.clip(v / 0.20 * 100, 0, 100))


def _score_accruals(v):
    if pd.isna(v):
        return np.nan
    # Lower is better; 0 → 100, 0.10 → 50, 0.20 → 0
    return float(np.clip(100 - abs(v) / 0.20 * 100, 0, 100))


def _score_fcf_conv(v):
    if pd.isna(v):
        return np.nan
    # 0 → 0, 1.0 → 100; anything above 1.0 pins at 100
    return float(np.clip(v * 100, 0, 100))


def _score_gap(v):
    if pd.isna(v):
        return np.nan
    # OCF − NI / |NI|; 0 → 50, 0.25+ → 100, −0.25 → 0
    return float(np.clip(50 + v * 200, 0, 100))


def _score_leverage(metrics: dict):
    # Combine Net Debt / EBITDA + Interest Coverage into a 0-100
    nd = metrics.get("Net Debt / EBITDA")
    ic = metrics.get("Interest Coverage")
    parts = []
    if pd.notna(nd):
        parts.append(float(np.clip(100 - nd / 6.0 * 100, 0, 100)))
    if pd.notna(ic):
        parts.append(float(np.clip(ic / 10.0 * 100, 0, 100)))
    return float(np.mean(parts)) if parts else np.nan


def _score_liquidity(metrics: dict):
    cr = metrics.get("Current Ratio")
    if pd.isna(cr):
        return np.nan
    return float(np.clip((cr - 0.5) / 1.5 * 100, 0, 100))


def _avg_defined(values: list) -> float:
    vs = [v for v in values if pd.notna(v)]
    return float(np.mean(vs)) if vs else np.nan


def quality_scorecard(
    dupont: dict, margins: dict, roic: dict,
    earnings: dict, accruals: dict, fcf: dict,
    leverage: dict,
) -> dict:
    """Roll the 8 analyses into 3 pillars (Profitability / Earnings Quality / Balance Sheet)."""
    profitability = _avg_defined([
        _score_roic(roic.get("latest_roic")),
        _score_roe(dupont.get("latest_roe")),
        _score_net_margin(_latest(margins["df"].loc["Net margin"])) if "Net margin" in margins["df"].index else np.nan,
    ])
    eq = _avg_defined([
        _score_accruals(accruals.get("latest")),
        _score_fcf_conv(fcf.get("latest")),
        _score_gap(earnings.get("latest_gap")),
    ])
    bs = _avg_defined([
        _score_leverage(leverage.get("metrics", {})),
        _score_liquidity(leverage.get("metrics", {})),
    ])

    def _label(score):
        if pd.isna(score):
            return "—"
        if score >= 70:
            return "Strong"
        if score >= 55:
            return "Solid"
        if score >= 40:
            return "Fair"
        return "Weak"

    return {
        "profitability":   {"score": profitability, "label": _label(profitability)},
        "earnings_quality":{"score": eq,            "label": _label(eq)},
        "balance_sheet":   {"score": bs,            "label": _label(bs)},
    }
