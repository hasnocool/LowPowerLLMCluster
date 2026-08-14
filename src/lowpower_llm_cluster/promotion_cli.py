from __future__ import annotations

import argparse
import json
from pathlib import Path

from .canonical_promotion import promote, records_from_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote verified discovery records into the canonical catalog")
    parser.add_argument("--input", default="results/discovery-latest.json")
    parser.add_argument("--catalog", default="data/catalog/auto-promoted.json")
    parser.add_argument("--report", default="results/promotion-latest.json")
    parser.add_argument("--min-source-confidence", type=float, default=0.80)
    parser.add_argument("--min-sku-confidence", type=float, default=0.55)
    args = parser.parse_args()
    report = promote(records_from_output(Path(args.input)), catalog_path=args.catalog, report_path=args.report, min_source_confidence=args.min_source_confidence, min_sku_confidence=args.min_sku_confidence)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
