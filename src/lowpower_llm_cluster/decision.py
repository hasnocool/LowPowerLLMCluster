# src/lowpower_llm_cluster/decision.py
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .catalog import load_catalog, project_root
from .evidence import memory_basis, verified_memory_gb
from .market import load_fx

MODEL_FIT_PRESETS = (
    {"name": "7B Q4", "params_b": 7.0, "bits": 4.0, "weight": 0.25},
    {"name": "14B Q4", "params_b": 14.0, "bits": 4.0, "weight": 0.25},
    {"name": "32B Q4", "params_b": 32.0, "bits": 4.0, "weight": 0.30},
    {"name": "70B Q4", "params_b": 70.0, "bits": 4.0, "weight": 0.20},
)

EXPERIMENTAL_CATEGORIES = {
    "fpga_accelerator",
    "adaptive_soc",
    "ai_asic_accelerator",
    "decommissioned_accelerator",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _listing_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("source") or ""), str(row.get("source_id") or "")


def _state_map(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for state in payload.get("states", {}).values():
        result[(str(state.get("source") or ""), str(state.get("source_id") or ""))] = state
    return result


def _confidence(row: dict[str, Any] | None) -> float:
    if not row:
        return 0.30
    sku = float((row.get("configuration_confidence") or {}).get("score", 0.0))
    seller = float((row.get("seller_confidence") or {}).get("score", 0.0))
    if sku == 0.0 and seller == 0.0:
        return 0.30
    return max(0.0, min(1.0, (sku * 0.70) + (seller * 0.30)))


def _cad_value(row: dict[str, Any], fx: dict[str, float], *, include_shipping: bool = True, tax_rate: float = 0.0) -> float | None:
    currency = str(row.get("currency") or "").upper()
    shipping_currency = str(row.get("shipping_currency") or currency).upper()
    if currency not in fx or (include_shipping and shipping_currency not in fx):
        return None
    value = float(row.get("price") or 0.0) * fx[currency]
    if include_shipping:
        value += float(row.get("shipping") or 0.0) * fx[shipping_currency]
    return round(value * (1.0 + tax_rate), 2)


def model_fit_summary(part: dict[str, Any], *, headroom: float = 1.40) -> dict[str, Any]:
    memory, basis, memory_confidence = memory_basis(part)
    fits: list[dict[str, Any]] = []
    score = 0.0
    for preset in MODEL_FIT_PRESETS:
        required = (preset["params_b"] * preset["bits"] / 8.0) * headroom
        fits_model = memory is not None and memory >= required
        if fits_model:
            score += float(preset["weight"])
        fits.append({
            "name": preset["name"],
            "required_gb": round(required, 2),
            "fits": bool(fits_model),
        })
    return {
        "memory_gb": memory,
        "memory_basis": basis,
        "memory_confidence": round(memory_confidence, 3),
        "fit_score": round(min(1.0, score), 3),
        "fits": fits,
        "largest_fit": next((row["name"] for row in reversed(fits) if row["fits"]), None),
        "notes": "Capacity screen only; does not predict runtime overhead or tokens/sec.",
    }


def price_statistics(
    part_id: str,
    observations: list[dict[str, Any]],
    listing_state: dict[str, Any],
    fx: dict[str, float],
    *,
    tax_rate: float = 0.12,
    minimum_match_confidence: float = 0.35,
) -> dict[str, Any]:
    rows = [
        row for row in observations
        if str(row.get("part_id") or "") == part_id
        and float((row.get("configuration_confidence") or {}).get("score", minimum_match_confidence)) >= minimum_match_confidence
    ]
    rows.sort(key=lambda row: str(row.get("observed_at") or ""))
    states = _state_map(listing_state)

    latest_by_listing: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        latest_by_listing[_listing_key(row)] = row
    active_latest: list[dict[str, Any]] = []
    for key, row in latest_by_listing.items():
        state = states.get(key)
        if state is not None and not state.get("active", True):
            continue
        active_latest.append(row)

    current: dict[str, Any] | None = None
    current_cad: float | None = None
    for row in active_latest:
        value = _cad_value(row, fx, include_shipping=True, tax_rate=tax_rate)
        if value is not None and (current_cad is None or value < current_cad):
            current = row
            current_cad = value
    if current is None and active_latest:
        current = max(active_latest, key=lambda row: str(row.get("observed_at") or ""))

    normalized = [(row, _cad_value(row, fx, include_shipping=True, tax_rate=tax_rate)) for row in rows]
    normalized = [(row, value) for row, value in normalized if value is not None]
    values = [float(value) for _, value in normalized]

    percentile = None
    trend_pct = None
    volatility_pct = None
    historical_low_cad = min(values) if values else None
    if current_cad is not None and values:
        percentile = sum(1 for value in values if value <= current_cad) / len(values)
    if len(values) >= 3:
        recent = values[-30:]
        half = max(1, len(recent) // 2)
        first = statistics.median(recent[:half])
        second = statistics.median(recent[half:])
        if first > 0:
            trend_pct = ((second - first) / first) * 100.0
        mean = statistics.fmean(recent)
        if mean > 0:
            volatility_pct = (statistics.pstdev(recent) / mean) * 100.0

    new_all_time_low = False
    native_all_time_low = None
    if current is not None:
        current_time = _time(current.get("observed_at"))
        currency = str(current.get("currency") or "").upper()
        current_native = float(current.get("price") or 0.0)
        prior = []
        for row in rows:
            if str(row.get("currency") or "").upper() != currency:
                continue
            when = _time(row.get("observed_at"))
            if current_time is not None and when is not None and when >= current_time:
                continue
            price = float(row.get("price") or 0.0)
            if price > 0:
                prior.append(price)
        if prior:
            native_all_time_low = min(prior + [current_native])
            new_all_time_low = current_native < (min(prior) - 0.005)
        elif current_native > 0:
            native_all_time_low = current_native

    return {
        "history_count": len(rows),
        "listing_count": len(latest_by_listing),
        "current_observation": current,
        "current_cad": round(current_cad, 2) if current_cad is not None else None,
        "historical_low_cad_current_fx": round(historical_low_cad, 2) if historical_low_cad is not None else None,
        "price_percentile": round(percentile, 3) if percentile is not None else None,
        "trend_pct": round(trend_pct, 2) if trend_pct is not None else None,
        "volatility_pct": round(volatility_pct, 2) if volatility_pct is not None else None,
        "native_all_time_low": native_all_time_low,
        "native_currency": str(current.get("currency") or "").upper() if current else None,
        "new_all_time_low": new_all_time_low,
        "normalization": "historical CAD comparisons apply the current sourced FX snapshot to all observations; all-time-low detection is native-currency based",
    }


def opportunity_status(current: dict[str, Any] | None, listing_state: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    if not current:
        return {"active": False, "expires_at": None, "expires_in_hours": None, "expired": False, "freshness_score": 0.30, "basis": "no_live_listing"}
    state = _state_map(listing_state).get(_listing_key(current))
    active = bool(state.get("active", True)) if state else True
    observed = _time(current.get("observed_at")) or now
    source_kind = str(current.get("source_kind") or "")
    ttl_hours = {
        "structured_marketplace": 36.0,
        "authorized_distributor": 96.0,
        "manufacturer": 168.0,
    }.get(source_kind, 72.0)
    expiry = observed + timedelta(hours=ttl_hours)
    actual_end = _time(current.get("availability"))
    if actual_end is not None and actual_end > observed:
        expiry = min(expiry, actual_end)
    expires_h = (expiry - now).total_seconds() / 3600.0
    expired = (not active) or expires_h <= 0
    if expired:
        freshness = 0.0
    elif expires_h <= 6:
        freshness = 0.45
    elif expires_h <= 24:
        freshness = 0.72
    else:
        freshness = 1.0
    return {
        "active": active,
        "expires_at": expiry.isoformat(),
        "expires_in_hours": round(expires_h, 1),
        "expired": expired,
        "freshness_score": freshness,
        "basis": "listing freshness TTL; actual seller end time used when parseable",
    }


def _software_score(part: dict[str, Any]) -> float:
    value = str(part.get("software_maturity") or "unknown").casefold()
    if value in {"high", "mature"}:
        return 1.0
    if value in {"medium", "moderate"}:
        return 0.70
    if "research" in value or "experimental" in value:
        return 0.35
    if value in {"low", "poor"}:
        return 0.25
    return 0.45


def _risk_score(part: dict[str, Any]) -> float:
    return {"low": 1.0, "medium": 0.65, "high": 0.25}.get(str(part.get("risk_level") or "unknown"), 0.45)


def evaluate_candidate(
    part: dict[str, Any],
    observations: list[dict[str, Any]],
    listing_state: dict[str, Any],
    fx: dict[str, float],
    *,
    tax_rate: float = 0.12,
    now: datetime | None = None,
) -> dict[str, Any]:
    price = price_statistics(str(part["id"]), observations, listing_state, fx, tax_rate=tax_rate)
    fit = model_fit_summary(part)
    opportunity = opportunity_status(price.get("current_observation"), listing_state, now=now)
    market_confidence = _confidence(price.get("current_observation"))
    _, _, memory_confidence = memory_basis(part)
    software = _software_score(part)
    risk = _risk_score(part)
    confidence_score = (market_confidence * 0.45) + (memory_confidence * 0.25) + (software * 0.20) + (risk * 0.10)

    percentile = price.get("price_percentile")
    if percentile is None:
        price_score = 0.15
    else:
        price_score = 1.0 - float(percentile)
        if price.get("new_all_time_low"):
            price_score += 0.15
        trend = price.get("trend_pct")
        if trend is not None:
            if trend <= -10:
                price_score += 0.06
            elif trend >= 10:
                price_score -= 0.06
        volatility = price.get("volatility_pct")
        if volatility is not None:
            if volatility >= 30:
                price_score -= 0.10
            elif volatility >= 15:
                price_score -= 0.05
        price_score = max(0.0, min(1.0, price_score))

    volatility = price.get("volatility_pct")
    stability_score = 0.55 if volatility is None else max(0.15, 1.0 - min(0.85, float(volatility) / 50.0))
    raw_score = 100.0 * (
        price_score * 0.35
        + float(fit["fit_score"]) * 0.25
        + confidence_score * 0.20
        + float(opportunity["freshness_score"]) * 0.10
        + stability_score * 0.10
    )
    if price.get("current_cad") is None:
        raw_score = min(raw_score, 59.0)
    score = round(max(0.0, min(100.0, raw_score)), 1)

    experimental = (
        part.get("category") in EXPERIMENTAL_CATEGORIES
        or str(part.get("risk_level")) == "high"
        or any(word in str(part.get("software_maturity") or "").casefold() for word in ("research", "experimental"))
    )
    if experimental:
        recommendation = "Experimental"
    elif (
        score >= 72
        and price.get("current_cad") is not None
        and not opportunity["expired"]
        and confidence_score >= 0.50
        and float(fit["fit_score"]) >= 0.25
        and (price.get("new_all_time_low") or percentile is None or float(percentile) <= 0.35)
    ):
        recommendation = "Buy"
    elif score >= 45 or (float(fit["fit_score"]) >= 0.50 and confidence_score >= 0.55):
        recommendation = "Watch"
    else:
        recommendation = "Ignore"

    reasons: list[str] = []
    if price.get("new_all_time_low"):
        reasons.append("new native-currency all-time low")
    if percentile is not None:
        reasons.append(f"price percentile {float(percentile) * 100:.0f}% (lower is better)")
    if fit.get("largest_fit"):
        reasons.append(f"capacity screen fits {fit['largest_fit']}")
    else:
        reasons.append("does not clear the smallest model-fit preset")
    if price.get("trend_pct") is not None:
        reasons.append(f"recent price trend {float(price['trend_pct']):+.1f}%")
    if price.get("volatility_pct") is not None:
        reasons.append(f"price volatility {float(price['volatility_pct']):.1f}%")
    if opportunity.get("expired"):
        reasons.append("current opportunity freshness window expired")
    if experimental:
        reasons.append("research/high-risk platform")

    return {
        "id": part["id"],
        "name": part["name"],
        "category": part.get("category"),
        "hardware_class": part.get("hardware_class"),
        "recommendation": recommendation,
        "deal_score": score,
        "current_cad": price.get("current_cad"),
        "new_all_time_low": bool(price.get("new_all_time_low")),
        "price_percentile": percentile,
        "trend_pct": price.get("trend_pct"),
        "volatility_pct": price.get("volatility_pct"),
        "history_count": price.get("history_count"),
        "model_fit": fit,
        "market_confidence": round(market_confidence, 3),
        "decision_confidence": round(confidence_score, 3),
        "opportunity": opportunity,
        "risk_level": part.get("risk_level"),
        "software_maturity": part.get("software_maturity"),
        "verified_memory_gb": verified_memory_gb(part),
        "power_target_w": part.get("power_target_w"),
        "power_scope": part.get("power_scope"),
        "reasons": reasons,
        "current_observation": price.get("current_observation"),
    }


def prioritize_alerts(alerts: list[dict[str, Any]], recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_part = {str(row.get("id")): row for row in recommendations}
    output: list[dict[str, Any]] = []
    for raw in alerts:
        alert = dict(raw)
        score = {"high": 55.0, "medium": 35.0, "low": 20.0}.get(str(alert.get("severity")), 25.0)
        kind = str(alert.get("type") or "")
        score += {
            "all_time_low": 25.0,
            "stock_return": 20.0,
            "price_drop": 15.0,
            "landed_cost_change": 10.0,
            "benchmark_regression": 12.0,
            "benchmark_improvement": 8.0,
            "new_product": 10.0,
        }.get(kind, 0.0)
        change = alert.get("change_pct")
        if change is not None:
            score += min(15.0, abs(float(change)) * 0.5)
        recommendation = by_part.get(str(alert.get("part_id") or ""))
        if recommendation:
            if recommendation.get("recommendation") == "Buy":
                score += 15.0
            elif recommendation.get("recommendation") == "Watch":
                score += 5.0
            score += float(recommendation.get("market_confidence") or 0.0) * 10.0
            expires = (recommendation.get("opportunity") or {}).get("expires_in_hours")
            if expires is not None and 0 < float(expires) <= 24:
                score += 10.0
        score = round(min(100.0, score), 1)
        alert["priority_score"] = score
        alert["priority"] = "P1" if score >= 75 else "P2" if score >= 55 else "P3" if score >= 35 else "P4"
        output.append(alert)
    output.sort(key=lambda row: (-float(row["priority_score"]), str(row.get("type") or "")))
    return output


def generate_daily_recommendations(
    *,
    price_path: Path | None = None,
    listing_state_path: Path | None = None,
    changes_path: Path | None = None,
    fx_path: Path | None = None,
    output_path: Path | None = None,
    tax_rate: float = 0.12,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = project_root()
    price_path = price_path or root / "data" / "market" / "price-history.json"
    listing_state_path = listing_state_path or root / "data" / "market" / "listing-state.json"
    changes_path = changes_path or root / "reports" / "current" / "daily-changes.json"
    output_path = output_path or root / "reports" / "current" / "daily-recommendations.json"
    observations = _load(price_path, {"observations": []}).get("observations", [])
    listing_state = _load(listing_state_path, {"states": {}, "events": []})
    fx = load_fx(fx_path)
    parts = load_catalog()["parts"]
    recommendations = [
        evaluate_candidate(part, observations, listing_state, fx, tax_rate=tax_rate, now=now)
        for part in parts
        if part.get("llm_candidate", part.get("category") == "compute_node")
    ]
    order = {"Buy": 0, "Watch": 1, "Experimental": 2, "Ignore": 3}
    recommendations.sort(key=lambda row: (order.get(str(row["recommendation"]), 9), -float(row["deal_score"]), str(row["name"])))

    changes = _load(changes_path, {"alerts": []}).get("alerts", [])
    all_time_alerts = []
    for row in recommendations:
        if not row.get("new_all_time_low"):
            continue
        current = row.get("current_observation") or {}
        all_time_alerts.append({
            "type": "all_time_low",
            "severity": "high",
            "part_id": row["id"],
            "source": current.get("source"),
            "source_id": current.get("source_id"),
            "title": row["name"],
            "observed_at": current.get("observed_at"),
            "reason": "new lowest observed native-currency seller price for this matched catalog product",
        })
    prioritized = prioritize_alerts(list(changes) + all_time_alerts, recommendations)
    counts = {name: sum(1 for row in recommendations if row["recommendation"] == name) for name in ("Buy", "Watch", "Experimental", "Ignore")}
    summary = {
        "generated_at": (now or _now()).isoformat(),
        "tax_rate": tax_rate,
        "model_fit_presets": [{key: value for key, value in preset.items() if key != "weight"} for preset in MODEL_FIT_PRESETS],
        "counts": counts,
        "recommendations": recommendations,
        "priority_alerts": prioritized,
        "all_time_low_count": len(all_time_alerts),
        "method_notes": [
            "Deal score weights price-history position most heavily and never converts TOPS/TFLOPS into tokens/sec.",
            "Model-fit score is a transparent memory-capacity screen with 40% planning headroom.",
            "GPU power fields are board TGP/TBP deployment inputs, not complete-node energy-efficiency measurements.",
            "Opportunity expiry is a freshness TTL unless a parseable seller end time is available; it is not a prediction that a listing will actually disappear.",
        ],
    }
    _write(output_path, summary)
    return summary


def render_daily_recommendations(summary: dict[str, Any], *, per_section: int = 12, alert_limit: int = 12) -> str:
    lines = [
        "# Daily Buy / Watch / Ignore / Experimental",
        "",
        f"Generated: **{summary.get('generated_at')}**",
        "",
        "This report ranks decision quality from sourced price history, model-capacity fit, confidence, risk and opportunity freshness. It is not a synthetic performance benchmark.",
        "",
        "## Priority alerts",
        "",
    ]
    alerts = list(summary.get("priority_alerts", []))
    if not alerts:
        lines.append("No prioritized change alerts are active.")
    else:
        for alert in alerts[:alert_limit]:
            subject = alert.get("title") or alert.get("part_id") or "unknown item"
            lines.append(f"- **{alert.get('priority')} · {alert.get('type', 'change').replace('_', ' ').title()}** — {subject}: {alert.get('reason', '')}")
    lines.append("")

    rows = list(summary.get("recommendations", []))
    for section in ("Buy", "Watch", "Experimental", "Ignore"):
        selected = [row for row in rows if row.get("recommendation") == section][:per_section]
        lines.extend([
            f"## {section}",
            "",
            "Score | CAD | Fit | Confidence | Trend | Volatility | Opportunity | Candidate",
            "---: | ---: | --- | ---: | ---: | ---: | --- | ---",
        ])
        if not selected:
            lines.append("— | — | — | — | — | — | — | No candidates in this class")
        for row in selected:
            cad = f"CA${row['current_cad']:,.2f}" if row.get("current_cad") is not None else "unpriced"
            fit = (row.get("model_fit") or {}).get("largest_fit") or "<7B Q4"
            trend = f"{row['trend_pct']:+.1f}%" if row.get("trend_pct") is not None else "—"
            volatility = f"{row['volatility_pct']:.1f}%" if row.get("volatility_pct") is not None else "—"
            opportunity = row.get("opportunity") or {}
            if opportunity.get("expired"):
                expiry = "expired/stale"
            elif opportunity.get("expires_in_hours") is not None:
                expiry = f"~{float(opportunity['expires_in_hours']):.0f}h"
            else:
                expiry = "static"
            all_time = " ★ATL" if row.get("new_all_time_low") else ""
            lines.append(f"{row['deal_score']:.1f} | {cad}{all_time} | {fit} | {row['decision_confidence']:.2f} | {trend} | {volatility} | {expiry} | {row['name']}")
        lines.append("")

    lines.extend([
        "## Interpretation",
        "",
        "- **Buy** requires a sufficiently strong score, usable model-fit evidence, confidence, a non-expired live opportunity and a favorable observed price position.",
        "- **Watch** is promising but price, confidence, fit or freshness is not strong enough for Buy.",
        "- **Experimental** is intentionally separated for research/high-risk platforms even when the price looks attractive.",
        "- **Ignore** means the current evidence does not justify attention; it can move categories when price or evidence changes.",
        "",
    ])
    return "\n".join(lines)
