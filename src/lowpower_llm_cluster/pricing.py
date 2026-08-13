# src/lowpower_llm_cluster/pricing.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class FxTable:
    """Explicit FX snapshot. Rates are units of target currency per one source unit."""

    target_currency: str
    rates: Mapping[str, float]
    as_of: str

    def convert(self, amount: float, source_currency: str) -> float:
        source = source_currency.upper()
        target = self.target_currency.upper()
        if source == target:
            return float(amount)
        try:
            rate = float(self.rates[source])
        except KeyError as exc:
            raise KeyError(f"missing {source}->{target} FX rate") from exc
        if rate <= 0:
            raise ValueError("FX rates must be positive")
        return float(amount) * rate


@dataclass(frozen=True, slots=True)
class LandedCostEstimate:
    item_cad: float
    shipping_cad: float
    duty_cad: float
    brokerage_cad: float
    tax_cad: float
    total_cad: float
    province: str
    fx_as_of: str
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_PROVINCE_SALES_TAX = {
    "AB": 0.05,
    "BC": 0.12,
    "MB": 0.12,
    "NB": 0.15,
    "NL": 0.15,
    "NS": 0.14,
    "NT": 0.05,
    "NU": 0.05,
    "ON": 0.13,
    "PE": 0.15,
    "QC": 0.14975,
    "SK": 0.11,
    "YT": 0.05,
}


def estimate_canada_landed_cost(
    *,
    item_price: float,
    source_currency: str,
    fx: FxTable,
    province: str = "BC",
    shipping: float = 0.0,
    shipping_currency: str | None = None,
    duty_rate: float = 0.0,
    brokerage_cad: float = 0.0,
    tax_rate: float | None = None,
) -> LandedCostEstimate:
    """Planning estimate for a Canadian purchase, not a customs/tax determination."""
    if min(item_price, shipping, duty_rate, brokerage_cad) < 0:
        raise ValueError("prices/rates cannot be negative")
    province = province.upper()
    if tax_rate is None:
        if province not in _PROVINCE_SALES_TAX:
            raise ValueError(f"unknown province/territory code: {province}")
        tax_rate = _PROVINCE_SALES_TAX[province]
    if tax_rate < 0 or duty_rate < 0:
        raise ValueError("tax and duty rates cannot be negative")

    item_cad = fx.convert(item_price, source_currency)
    shipping_cad = fx.convert(shipping, shipping_currency or source_currency)
    duty_cad = item_cad * duty_rate
    taxable = item_cad + shipping_cad + duty_cad + brokerage_cad
    tax_cad = taxable * tax_rate
    total = taxable + tax_cad
    assumptions = (
        "FX rate supplied explicitly; no live exchange rate is silently assumed.",
        "Duty defaults to 0% and must be overridden when classification/origin makes duty applicable.",
        "Tax is a planning rate by province/territory; actual border and retail tax treatment can differ.",
        "Brokerage and shipping must be supplied when the seller/carrier does not include them.",
    )
    return LandedCostEstimate(
        item_cad=round(item_cad, 2), shipping_cad=round(shipping_cad, 2), duty_cad=round(duty_cad, 2),
        brokerage_cad=round(brokerage_cad, 2), tax_cad=round(tax_cad, 2), total_cad=round(total, 2),
        province=province, fx_as_of=fx.as_of, assumptions=assumptions,
    )
