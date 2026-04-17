# -*- coding: utf-8 -*-
"""
Transparent prescription engine for Stock Analysis.

Produces a Buy / Hold / Avoid verdict with:
  - Four component scores (Valuation, Quality, Momentum, Macro), each 0-100
  - Investor-profile weighting (Value / Growth / Income / Balanced)
  - Human-readable rationales for each component
  - A composite score and confidence level
  - A one-sentence thesis

The scoring is deliberately rule-based and transparent. A user clicking into
the verdict card should be able to understand exactly why the engine reached
its conclusion — no black box.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Investor profiles — weights for (valuation, quality, momentum, macro)
# ---------------------------------------------------------------------------
# Weights sum to 1.0 within each profile.
# Rationale:
#   Balanced — even split, slight skew away from macro (context not thesis).
#   Value     — valuation dominates; momentum ignored (value investors wait).
#   Growth    — momentum + quality lead; valuation de-emphasised.
#   Income    — quality (sustainability) + macro (rate regime) matter most.

INVESTOR_PROFILES: dict[str, dict[str, float]] = {
    "Balanced": {"valuation": 0.30, "quality": 0.30, "momentum": 0.25, "macro": 0.15},
    "Value":    {"valuation": 0.45, "quality": 0.30, "momentum": 0.10, "macro": 0.15},
    "Growth":   {"valuation": 0.15, "quality": 0.30, "momentum": 0.40, "macro": 0.15},
    "Income":   {"valuation": 0.25, "quality": 0.40, "momentum": 0.10, "macro": 0.25},
}


PROFILE_DESCRIPTIONS: dict[str, str] = {
    "Balanced": "Weighs fundamentals and momentum roughly evenly. A good default.",
    "Value":    "Emphasises cheapness and quality; patient with momentum.",
    "Growth":   "Rewards momentum and earnings growth; tolerates premium multiples.",
    "Income":   "Prioritises stable cash flow and dividend sustainability.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _score_linear(value: float | None, good: float, bad: float) -> float | None:
    """Linearly map a raw metric to 0-100 using anchor points.

    `good` is the value that maps to 100; `bad` maps to 0. Works in both
    directions (good can be lower or higher than bad). Returns None if the
    input is missing so callers can exclude it from averaging.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(v):
        return None
    if good == bad:
        return 50.0
    if good > bad:
        return _clip((v - bad) / (good - bad) * 100)
    return _clip((bad - v) / (bad - good) * 100)


def _avg(xs: list[float | None]) -> float:
    """Average non-None values; return 50 (neutral) if all None."""
    vals = [x for x in xs if x is not None]
    return sum(vals) / len(vals) if vals else 50.0


# ---------------------------------------------------------------------------
# Component scores
# ---------------------------------------------------------------------------

def score_valuation(info: dict) -> tuple[float, list[str]]:
    """Score 0-100 where 100 = deeply undervalued. Based on P/E, P/B, EV/EBITDA, PEG."""
    rationale: list[str] = []
    subs: list[float | None] = []

    pe = info.get("trailingPE")
    if pe is not None and pe > 0:
        s = _score_linear(pe, good=10, bad=35)
        subs.append(s)
        label = "attractive" if s and s > 60 else "expensive" if s and s < 40 else "fair"
        rationale.append(f"P/E {pe:.1f} — {label}")

    pb = info.get("priceToBook")
    if pb is not None and pb > 0:
        s = _score_linear(pb, good=1.0, bad=8.0)
        subs.append(s)
        rationale.append(f"P/B {pb:.1f}")

    ev_ebitda = info.get("enterpriseToEbitda")
    if ev_ebitda is not None and ev_ebitda > 0:
        s = _score_linear(ev_ebitda, good=6, bad=25)
        subs.append(s)
        rationale.append(f"EV/EBITDA {ev_ebitda:.1f}")

    peg = info.get("pegRatio")
    if peg is not None and peg > 0:
        s = _score_linear(peg, good=0.5, bad=3.0)
        subs.append(s)
        rationale.append(f"PEG {peg:.2f}")

    if not rationale:
        return 50.0, ["No valuation data available"]
    return _avg(subs), rationale


def score_quality(info: dict) -> tuple[float, list[str]]:
    """Score 0-100 based on profitability, leverage, and liquidity."""
    rationale: list[str] = []
    subs: list[float | None] = []

    roe = info.get("returnOnEquity")
    if roe is not None:
        # ROE above 25% = 100; zero or negative = 0
        s = _score_linear(roe * 100, good=25, bad=0)
        subs.append(s)
        rationale.append(f"ROE {roe*100:.1f}%")

    margin = info.get("profitMargins")
    if margin is not None:
        s = _score_linear(margin * 100, good=25, bad=0)
        subs.append(s)
        rationale.append(f"Profit margin {margin*100:.1f}%")

    de = info.get("debtToEquity")
    if de is not None:
        # yfinance returns D/E as a percentage — lower = better
        s = _score_linear(de, good=50, bad=300)
        subs.append(s)
        rationale.append(f"D/E {de:.0f}")

    current_ratio = info.get("currentRatio")
    if current_ratio is not None:
        s = _score_linear(current_ratio, good=2.5, bad=0.8)
        subs.append(s)
        rationale.append(f"Current ratio {current_ratio:.1f}")

    fcf = info.get("freeCashflow")
    if fcf is not None:
        # Binary-ish: positive FCF = 80; negative = 20
        subs.append(80.0 if fcf > 0 else 20.0)
        rationale.append("FCF positive" if fcf > 0 else "FCF negative")

    if not rationale:
        return 50.0, ["No quality data available"]
    return _avg(subs), rationale


def score_momentum(signals: dict) -> tuple[float, list[str]]:
    """Score 0-100 from the technical-signal summary."""
    direction = signals.get("direction", "Neutral")
    strength = signals.get("strength", 50)

    if direction == "Bullish":
        score = 50 + strength * 0.5   # 50-100
    elif direction == "Bearish":
        score = 50 - strength * 0.5   # 0-50
    else:
        score = 50

    rsi_val = signals.get("rsi")
    rationale = []
    if rsi_val is not None:
        rationale.append(f"{direction} overall — RSI {rsi_val:.0f}")
    else:
        rationale.append(f"{direction} overall")

    # Surface the top 2 most-informative signal lines
    for _name, _dir, text in signals.get("signals", [])[:2]:
        rationale.append(text)

    return _clip(score), rationale


def score_macro(macro: dict) -> tuple[float, list[str]]:
    """Score based on VIX (fear) and 10Y yield (liquidity backdrop).

    Higher = more supportive of equity risk-taking.
    """
    rationale: list[str] = []
    subs: list[float | None] = []

    vix = macro.get("^VIX", {}).get("current") if macro else None
    if vix is not None:
        # VIX 12 = 100 (calm), VIX 35 = 0 (fearful)
        vix_score = _score_linear(vix, good=12, bad=35)
        subs.append(vix_score)
        if vix < 15:
            rationale.append(f"VIX {vix:.1f} — calm, risk-on")
        elif vix > 25:
            rationale.append(f"VIX {vix:.1f} — elevated, risk-off")
        else:
            rationale.append(f"VIX {vix:.1f} — moderate")

    tnx = macro.get("^TNX", {}).get("current") if macro else None
    if tnx is not None:
        # 10Y: 2% = 100 (accommodative), 6% = 0 (restrictive)
        tnx_score = _score_linear(tnx, good=2.5, bad=6.0)
        subs.append(tnx_score)
        if tnx > 5.0:
            rationale.append(f"10Y {tnx:.2f}% — elevated, headwind for growth")
        elif tnx < 3.0:
            rationale.append(f"10Y {tnx:.2f}% — accommodative")
        else:
            rationale.append(f"10Y {tnx:.2f}% — neutral")

    if not rationale:
        return 50.0, ["No macro data available"]
    return _avg(subs), rationale


# ---------------------------------------------------------------------------
# Verdict mapping
# ---------------------------------------------------------------------------

def verdict_from_score(score: float) -> tuple[str, str]:
    """Map composite 0-100 score to (verdict, confidence)."""
    if score >= 72:
        return "Buy", "High"
    if score >= 60:
        return "Buy", "Medium"
    if score >= 48:
        return "Hold", "Medium"
    if score >= 35:
        return "Avoid", "Medium"
    return "Avoid", "High"


def _build_thesis(
    verdict: str,
    profile: str,
    sorted_components: list[tuple[str, float]],
    signals: dict,
    info: dict,
) -> str:
    """Generate a one-sentence thesis stitching the strongest & weakest legs together."""
    strong_name, strong_score = sorted_components[0]
    weak_name, weak_score = sorted_components[-1]
    direction = signals.get("direction", "neutral").lower()

    pretty = {
        "valuation": "valuation",
        "quality":   "quality",
        "momentum":  "momentum",
        "macro":     "macro backdrop",
    }

    if verdict == "Buy":
        lead = f"Attractive setup for {profile.lower()} investors:"
        body = f"strong {pretty[strong_name]} ({strong_score:.0f}/100)"
        if weak_score < 40:
            body += f", though {pretty[weak_name]} ({weak_score:.0f}) is the key risk."
        elif direction == "bullish":
            body += f" confirmed by bullish momentum."
        else:
            body += " with balanced fundamentals."
        return f"{lead} {body}"

    if verdict == "Hold":
        return (
            f"Mixed picture — {pretty[strong_name]} ({strong_score:.0f}/100) supports the thesis, "
            f"{pretty[weak_name]} ({weak_score:.0f}/100) holds it back. "
            f"{'Wait for a cleaner signal.' if direction == 'neutral' else f'Momentum is {direction}.'}"
        )

    # Avoid
    lead = f"Unattractive at current levels for {profile.lower()} investors:"
    body = f"weak {pretty[weak_name]} ({weak_score:.0f}/100)"
    if strong_score > 60:
        body += f" despite reasonable {pretty[strong_name]} ({strong_score:.0f})."
    else:
        body += " across the board."
    return f"{lead} {body}"


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def generate_prescription(
    info: dict,
    signals: dict,
    macro: dict,
    profile: str = "Balanced",
) -> dict:
    """Produce a full prescription for a stock given fundamentals, technicals, macro.

    Returns a dict with:
      - verdict: "Buy" | "Hold" | "Avoid"
      - confidence: "High" | "Medium"
      - composite_score: 0-100
      - {valuation,quality,momentum,macro}_score: 0-100
      - {valuation,quality,momentum,macro}_rationale: list[str]
      - weights: {component: weight}
      - profile: str
      - thesis: str (one-sentence summary)
    """
    weights = INVESTOR_PROFILES.get(profile, INVESTOR_PROFILES["Balanced"])

    val_score, val_rat = score_valuation(info)
    qual_score, qual_rat = score_quality(info)
    mom_score, mom_rat = score_momentum(signals)
    mac_score, mac_rat = score_macro(macro)

    composite = (
        val_score * weights["valuation"]
        + qual_score * weights["quality"]
        + mom_score * weights["momentum"]
        + mac_score * weights["macro"]
    )

    verdict, confidence = verdict_from_score(composite)

    components = [
        ("valuation", val_score),
        ("quality", qual_score),
        ("momentum", mom_score),
        ("macro", mac_score),
    ]
    components_sorted = sorted(components, key=lambda x: x[1], reverse=True)

    thesis = _build_thesis(verdict, profile, components_sorted, signals, info)

    return {
        "verdict": verdict,
        "confidence": confidence,
        "composite_score": composite,
        "valuation_score": val_score,
        "quality_score": qual_score,
        "momentum_score": mom_score,
        "macro_score": mac_score,
        "valuation_rationale": val_rat,
        "quality_rationale": qual_rat,
        "momentum_rationale": mom_rat,
        "macro_rationale": mac_rat,
        "weights": weights,
        "profile": profile,
        "thesis": thesis,
    }
