# scripts/profile_jsonld.py
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lowpower_llm_cluster.discovery import _parse_jsonld_page


def build_page(products: int) -> str:
    graph = [
        {
            "@type": "Product",
            "name": f"Synthetic product {index}",
            "sku": f"SKU-{index}",
            "offers": {"price": str(100 + index % 100), "priceCurrency": "USD"},
        }
        for index in range(products)
    ]
    return '<script type="application/ld+json">' + json.dumps({"@graph": graph}, separators=(",", ":")) + "</script>"


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile JSON-LD parser CPU cost before enabling process pools")
    parser.add_argument("--products", type=int, nargs="+", default=[100, 1000, 10000])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    rows = []
    for count in args.products:
        page = build_page(count)
        samples = []
        for _ in range(args.repeats):
            started = time.perf_counter()
            records = _parse_jsonld_page("synthetic", "https://example.invalid/product", page)
            elapsed = time.perf_counter() - started
            if len(records) != count:
                raise RuntimeError(f"parsed {len(records)} records, expected {count}")
            samples.append(elapsed)
        median = statistics.median(samples)
        rows.append({
            "products": count,
            "median_ms": round(median * 1000.0, 3),
            "products_per_s": round(count / max(median, 1e-9), 2),
            "html_bytes": len(page.encode("utf-8")),
        })
    print(json.dumps({"parser": "thread_default", "results": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
