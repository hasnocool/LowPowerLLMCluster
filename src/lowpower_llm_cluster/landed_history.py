# src/lowpower_llm_cluster/landed_history.py
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .catalog import project_root
from .pricing import FxTable, LandedCostEstimate, estimate_canada_landed_cost


@dataclass(frozen=True, slots=True)
class ProvincePreset:
    code: str
    tax_rate: float
    label: str


PROVINCE_PRESETS: dict[str, ProvincePreset] = {
    "AB": ProvincePreset("AB", 0.05, "Alberta"),
    "BC": ProvincePreset("BC", 0.12, "British Columbia"),
    "MB": ProvincePreset("MB", 0.12, "Manitoba"),
    "NB": ProvincePreset("NB", 0.15, "New Brunswick"),
    "NL": ProvincePreset("NL", 0.15, "Newfoundland and Labrador"),
    "NS": ProvincePreset("NS", 0.14, "Nova Scotia"),
    "NT": ProvincePreset("NT", 0.05, "Northwest Territories"),
    "NU": ProvincePreset("NU", 0.05, "Nunavut"),
    "ON": ProvincePreset("ON", 0.13, "Ontario"),
    "PE": ProvincePreset("PE", 0.15, "Prince Edward Island"),
    "QC": ProvincePreset("QC", 0.14975, "Quebec"),
    "SK": ProvincePreset("SK", 0.11, "Saskatchewan"),
    "YT": ProvincePreset("YT", 0.05, "Yukon"),
}


@dataclass(frozen=True, slots=True)
class TariffEvidence:
    """Explicit planning evidence for a tariff assumption; never a universal customs claim."""

    hs_code: str
    duty_rate: float
    source_url: str
    verified_on: str
    origin_country: str | None = None
    description: str = ""
    confidence: str = "medium"

    def __post_init__(self) -> None:
        if not self.hs_code.strip():
            raise ValueError("hs_code is required")
        if not 0.0 <= float(self.duty_rate) <= 1.0:
            raise ValueError("duty_rate must be between 0 and 1")
        if not self.source_url.startswith("https://"):
            raise ValueError("tariff evidence requires an HTTPS source URL")
        if not self.verified_on.strip():
            raise ValueError("verified_on is required")


@dataclass(frozen=True, slots=True)
class LandedCostSnapshot:
    snapshot_id: str
    source: str
    source_id: str
    listing_url: str
    listing_observed_at: str
    recorded_at: str
    item_price: float
    source_currency: str
    shipping: float
    shipping_currency: str
    brokerage_cad: float
    province: str
    province_tax_rate: float
    fx_as_of: str
    fx_rates: dict[str, float]
    tariff_evidence: dict[str, Any] | None
    estimate: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def province_preset(code: str) -> ProvincePreset:
    try:
        return PROVINCE_PRESETS[code.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown province/territory code: {code}") from exc


def estimate_landed_with_evidence(
    *,
    item_price: float,
    source_currency: str,
    fx: FxTable,
    province: str = "BC",
    shipping: float = 0.0,
    shipping_currency: str | None = None,
    brokerage_cad: float = 0.0,
    tariff: TariffEvidence | None = None,
) -> LandedCostEstimate:
    preset = province_preset(province)
    return estimate_canada_landed_cost(
        item_price=item_price,
        source_currency=source_currency,
        fx=fx,
        province=preset.code,
        shipping=shipping,
        shipping_currency=shipping_currency,
        duty_rate=0.0 if tariff is None else tariff.duty_rate,
        brokerage_cad=brokerage_cad,
        tax_rate=preset.tax_rate,
    )


def _snapshot_id(payload: Mapping[str, Any]) -> str:
    stable = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def make_landed_snapshot(
    *,
    source: str,
    source_id: str,
    listing_url: str,
    listing_observed_at: str,
    item_price: float,
    source_currency: str,
    fx: FxTable,
    province: str = "BC",
    shipping: float = 0.0,
    shipping_currency: str | None = None,
    brokerage_cad: float = 0.0,
    tariff: TariffEvidence | None = None,
    recorded_at: str | None = None,
) -> LandedCostSnapshot:
    preset = province_preset(province)
    shipping_currency = (shipping_currency or source_currency).upper()
    estimate = estimate_landed_with_evidence(
        item_price=item_price,
        source_currency=source_currency,
        fx=fx,
        province=preset.code,
        shipping=shipping,
        shipping_currency=shipping_currency,
        brokerage_cad=brokerage_cad,
        tariff=tariff,
    )
    identity = {
        "source": source,
        "source_id": source_id,
        "listing_observed_at": listing_observed_at,
        "item_price": float(item_price),
        "source_currency": source_currency.upper(),
        "shipping": float(shipping),
        "shipping_currency": shipping_currency,
        "brokerage_cad": float(brokerage_cad),
        "province": preset.code,
        "fx_as_of": fx.as_of,
        "fx_rates": {str(key).upper(): float(value) for key, value in fx.rates.items()},
        "tariff_evidence": asdict(tariff) if tariff else None,
    }
    return LandedCostSnapshot(
        snapshot_id=_snapshot_id(identity),
        source=source,
        source_id=source_id,
        listing_url=listing_url,
        listing_observed_at=listing_observed_at,
        recorded_at=recorded_at or datetime.now(UTC).isoformat(),
        item_price=float(item_price),
        source_currency=source_currency.upper(),
        shipping=float(shipping),
        shipping_currency=shipping_currency,
        brokerage_cad=float(brokerage_cad),
        province=preset.code,
        province_tax_rate=preset.tax_rate,
        fx_as_of=fx.as_of,
        fx_rates={str(key).upper(): float(value) for key, value in fx.rates.items()},
        tariff_evidence=asdict(tariff) if tariff else None,
        estimate=estimate.to_dict(),
    )


def _read_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "snapshots": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_history(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


class LandedCostHistory:
    """Append-only landed-CAD history preserving the FX/tariff assumptions used at observation time."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or project_root() / "data" / "market" / "landed-cad-history.json"
        self._lock = asyncio.Lock()

    async def append(self, snapshot: LandedCostSnapshot) -> bool:
        async with self._lock:
            payload = await asyncio.to_thread(_read_history, self.path)
            rows = payload.setdefault("snapshots", [])
            if any(row.get("snapshot_id") == snapshot.snapshot_id for row in rows):
                return False
            rows.append(snapshot.to_dict())
            rows.sort(key=lambda row: (str(row.get("listing_observed_at", "")), str(row.get("recorded_at", ""))))
            await asyncio.to_thread(_write_history, self.path, payload)
            return True

    async def snapshots(self, *, source: str | None = None, source_id: str | None = None) -> list[dict[str, Any]]:
        payload = await asyncio.to_thread(_read_history, self.path)
        rows = list(payload.get("snapshots", []))
        if source is not None:
            rows = [row for row in rows if row.get("source") == source]
        if source_id is not None:
            rows = [row for row in rows if row.get("source_id") == source_id]
        return rows


def fx_only_delta(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, float | str]:
    """Compare stored landed totals only when every non-FX acquisition assumption is identical."""
    basis_keys = (
        "source",
        "source_id",
        "item_price",
        "source_currency",
        "shipping",
        "shipping_currency",
        "brokerage_cad",
        "province",
        "province_tax_rate",
        "tariff_evidence",
    )
    mismatches = [key for key in basis_keys if first.get(key) != second.get(key)]
    if mismatches:
        raise ValueError(f"not an FX-only comparison; changed fields: {', '.join(mismatches)}")
    old_total = float((first.get("estimate") or {}).get("total_cad"))
    new_total = float((second.get("estimate") or {}).get("total_cad"))
    delta = new_total - old_total
    return {
        "first_fx_as_of": str(first.get("fx_as_of") or ""),
        "second_fx_as_of": str(second.get("fx_as_of") or ""),
        "first_total_cad": round(old_total, 2),
        "second_total_cad": round(new_total, 2),
        "delta_cad": round(delta, 2),
        "delta_pct": round((delta / old_total) * 100.0, 3) if old_total else 0.0,
    }
