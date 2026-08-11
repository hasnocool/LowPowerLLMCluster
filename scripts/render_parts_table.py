# scripts/render_parts_table.py
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "parts.json"
OUTPUT = ROOT / "PARTS.md"


def price(part: dict[str, object]) -> str:
    low = float(part["price_min_usd"])
    high = float(part["price_max_usd"])
    return f"${low:,.2f}" if low == high else f"${low:,.2f}–${high:,.2f}"


def marketplace(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if "alibaba" in host:
        return "Alibaba"
    if "aliexpress" in host:
        return "AliExpress"
    if "nvidia" in host:
        return "NVIDIA"
    if "minisforum" in host:
        return "MINISFORUM"
    if "frame.work" in host:
        return "Framework"
    if "allnetchina" in host:
        return "ALLNET"
    return host


def main() -> int:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    lines = [
        "# Current Parts & Listings",
        "",
        f"Market snapshot: **{data['snapshot_date']}**. Currency: **USD**.",
        "",
        "> Prices are sourcing snapshots, not quotes. Marketplace pages often contain multiple variants; secondary-market and experimental hardware carries additional risk. Confirm the exact SKU before ordering.",
        "",
        "| Category | Part | Price | MOQ | Status | Source |",
        "|---|---|---:|---:|---|---|",
    ]
    for part in data["parts"]:
        src = marketplace(str(part["url"]))
        lines.append(
            f"| {part['category']} | {part['name']} | {price(part)} | {part['moq']} | "
            f"{part['listing_status']} | [{src}]({part['url']}) |"
        )
    lines.extend(["", "## Why each part is here", ""])
    for part in data["parts"]:
        lines.extend(
            [
                f"### {part['name']}",
                "",
                part["plain_language"],
                "",
                f"- Vendor/source: {part['vendor']}",
                f"- Hardware class: {part.get('hardware_class', part['category'])}",
                f"- Software maturity: {part.get('software_maturity', 'not classified')}",
                f"- Risk: {part.get('risk_level', 'not classified')}",
                f"- Verified: {part['verified_on']}",
                f"- Source/listing: {part['url']}",
                "",
            ]
        )
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
