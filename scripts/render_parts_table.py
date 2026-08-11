from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lowpower_llm_cluster.catalog import load_catalog  # noqa: E402
from lowpower_llm_cluster.evidence import memory_basis  # noqa: E402

CATALOG = ROOT / "data" / "parts.json"
OUTPUT = ROOT / "PARTS.md"


def price(part: dict[str, object]) -> str:
    low = part.get("price_min_usd")
    high = part.get("price_max_usd")
    if low is None or high is None:
        return f"unresolved ({part.get('price_status', 'unknown')})"
    low_f = float(low)
    high_f = float(high)
    return f"${low_f:,.2f}" if low_f == high_f else f"${low_f:,.2f}–${high_f:,.2f}"


def marketplace(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    labels = {
        "alibaba.com": "Alibaba", "aliexpress.com": "AliExpress", "aliexpress.us": "AliExpress",
        "nvidia.com": "NVIDIA", "minisforum.com": "MINISFORUM", "frame.work": "Framework",
        "allnetchina.cn": "ALLNET", "raspberrypi.com": "Raspberry Pi", "amd.com": "AMD",
        "tenstorrent.com": "Tenstorrent", "coral.ai": "Coral", "firefly.store": "Firefly",
        "developer.memryx.com": "MemryX", "intel.com": "Intel", "chinaglobalmall.com": "ChinaGlobalMall",
    }
    return labels.get(host, host)


def main() -> int:
    data = load_catalog(CATALOG)
    lines = [
        "# Current Parts & Listings", "",
        f"Market snapshot: **{data['snapshot_date']}**. Currency: **USD**. Catalog schema: **v{data['schema_version']}**.", "",
        "> Prices are sourcing snapshots, not quotes. `unresolved` is intentional for watch-list hardware whose current price cannot be verified honestly.", "",
        "| Category | Part | Price | Memory | Source | Why it is here |",
        "|---|---|---:|---:|---|---|",
    ]
    for part in data["parts"]:
        src = marketplace(str(part["url"]))
        why = (str(part["plain_language"]).replace("|", "\\|").replace("\n", " ")
               .replace("“", "'").replace("”", "'"))
        mem, basis, _ = memory_basis(part)
        memory = "unknown" if mem is None else f"{mem:g} GB ({basis})"
        lines.append(
            f"| {part['category']} | {part['name']} | {price(part)} | {memory} | [{src}]({part['url']}) | {why} |"
        )

    accelerators = [p for p in data["parts"] if p.get("accelerator_family")]
    lines.extend([
        "", "## Accelerator quick view", "",
        "TOPS/TFLOPS are discovery metadata, **not cross-platform LLM scores**. `LLM support` reflects an actual runtime path, not marketing arithmetic.", "",
        "| Accelerator | Family | Memory | LLM support | Role | Lifecycle |",
        "|---|---|---:|---|---|---|",
    ])
    for part in accelerators:
        memory = f"{part['memory_capacity_gb']} GB" if part.get("memory_capacity_gb") else "on-chip / n.a."
        lines.append(
            f"| {part['name']} | {part.get('accelerator_family')} | {memory} | {part.get('llm_support')} | "
            f"{part.get('workload_role')} | {part.get('lifecycle_status')} |"
        )

    lines.extend([
        "", "## Reading the catalog", "",
        "The machine-readable catalog keeps source type, software maturity, risk, lifecycle, power scope and host requirements. "
        "Use `data/parts.json` as the manifest and the files in `data/catalog/` as the editable source records. Included/fixed RAM and fixed GPU VRAM are kept separate from board/CPU maximums.", "",
        "A discrete GPU is a first-class LLM sourcing target, but its board TGP/TBP is not complete-node power. A specialist accelerator is not a failed LLM node either: Coral/MemryX-class hardware can still save whole-cluster energy by keeping larger workers asleep. "
        "Conversely, an EOL FPGA/ASIC with impressive TOPS stays a research/watch item until a real runtime, price and complete-node benchmark exist.", "",
    ])

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
