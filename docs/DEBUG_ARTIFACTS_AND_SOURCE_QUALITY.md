# Debug artifacts and source-quality learning

The continuous discovery service writes two complementary diagnostic streams:

- `results/events.jsonl` — compact service lifecycle events used by the live dashboard.
- `results/debug/runtime.jsonl` — detailed structured scanner/scheduler/source-quality events with rotation.

Each completed refresh also writes a retained per-run directory under:

```text
results/debug/runs/<run-id>/
├── summary.json
├── source-quality.json
├── scheduler.json
└── effective-config.redacted.json
```

The default keeps the latest 20 run directories and rotates the detailed JSONL log at about 8 MiB. The systemd installer resolves `--debug-dir` to an absolute path so a deployed service has one unambiguous diagnostic location.

## Repository-safe debug bundles

Runtime files can contain local paths and operational details, so do not commit the entire `results/` directory. Instead create a sanitized bundle:

```bash
llm-cluster-debug-export
```

By default it writes a timestamped directory below `debug-artifacts/` containing:

- a redacted effective configuration;
- the latest discovery run;
- the persistent source-quality table;
- a tail of `runtime.jsonl`;
- a tail of `events.jsonl`;
- basic Python/platform information;
- a SHA-256 manifest;
- a short README explaining the bundle.

Secret-like keys, authorization/cookie fields, common API-key/token formats, URL credentials, and sensitive URL query parameters are redacted. Raw HTTP response bodies and the full SQLite database are deliberately excluded. Review the generated bundle before publishing it, then it can be committed or attached to a debugging PR.

Useful overrides:

```bash
llm-cluster-debug-export \
  --debug-dir /absolute/path/to/results/debug \
  --history /absolute/path/to/catalog-history.sqlite3 \
  --event-log /absolute/path/to/events.jsonl \
  --latest-output /absolute/path/to/discovery-latest.json \
  --destination debug-artifacts \
  --tail-lines 1000
```

## Source-quality learning

The scanner maintains a `source_quality` table in `catalog-history.sqlite3`. Each source accumulates evidence across successful and failed scan cycles rather than being judged on one request.

The quality score combines:

- success rate;
- unique products contributed per cycle;
- price completeness;
- specification richness;
- freshness of publication metadata when available;
- LLM/AI-hardware relevance signals;
- raw-to-unique duplicate rate;
- average source latency.

The scheduler does not adapt until a source has at least three measured cycles by default. Static curated sources continue to run every cycle. Automatically learned sources (`auto-*`) may then receive a bounded policy:

| Quality | Scan cadence | Crawl budget |
| --- | --- | --- |
| >= 0.80 | every cycle | up to 1.50x |
| >= 0.65 | every cycle | up to 1.25x |
| >= 0.50 | every 2 cycles | 1.00x |
| >= 0.35 | every 3 cycles | at least 0.75x |
| < 0.35 | every 4 cycles | at least 0.50x |

These are sampling/budget changes, not permanent bans. A weak learned source remains eligible for later scans and can recover its score as its results improve. The candidate-page budget is capped (96 pages by default), and all existing global/per-host concurrency, retry/backoff, cache, response-size, and circuit-breaker controls still apply.

Every decision is visible in `scheduler.json`, `runtime.jsonl`, and `runtime.source_quality_learning` inside the latest discovery output. This makes source-budget changes explainable and gives debugging bundles enough evidence to reproduce why a source was favored or sampled less often.

## Default deployment

Re-rendering the normal paired service units also wires the debug path:

```bash
llm-cluster-install-service \
  --config config/discovery.example.json \
  --with-dashboard \
  --enable-now
```

To use a different location:

```bash
llm-cluster-install-service \
  --config config/discovery.example.json \
  --debug-dir /var/lib/lowpower-llm-cluster/debug \
  --with-dashboard \
  --enable-now
```
