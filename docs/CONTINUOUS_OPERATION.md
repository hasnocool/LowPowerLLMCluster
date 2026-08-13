# Continuous scanning and live dashboard

`llm-cluster-service` treats continuous operation as the default. When `--interval` is omitted, a new discovery cycle starts immediately after the previous cycle finishes. This keeps the crawler processing as fast as the configured source limits, adaptive concurrency, circuit breakers and HTTP backoff allow.

Use an explicit interval only when you want scheduled/throttled operation:

```bash
# continuous (default)
llm-cluster-service --config config/discovery.example.json

# optional scheduled mode
llm-cluster-service --config config/discovery.example.json --interval 300
```

The service writes machine-readable events to `results/events.jsonl` by default. Events include service start/stop, cycle start/completion/error, observation counts, change counts and scheduled waits. The journal is bounded and rotates to `events.jsonl.1`.

## Live dashboard

Run the dashboard against the same history database and event journal:

```bash
llm-cluster-dashboard \
  --history results/catalog-history.sqlite3 \
  --event-log results/events.jsonl \
  --host 0.0.0.0 \
  --port 8788
```

The dashboard watches SQLite in read-only mode every 0.5 seconds by default. Because discovery commits observations batch-by-batch, the UI can show progress before a complete discovery cycle finishes.

### Canonical catalog vs live discoveries

The original overview cards (`Catalog records`, `Priced records`, `Memory known`, and `Low-risk entries`) describe the verified canonical catalog and therefore do not increase merely because the scanner found another marketplace listing. They are now explicitly labelled as canonical metrics.

A separate live runtime block updates from SQLite every few seconds and shows:

- active live/staging discoveries;
- total observations already committed to SQLite;
- the current scanner/run state;
- the exact history database path and current file size.

`/discoveries` is the live product/listing browser. It reads directly from `listing_state`, so newly committed active listings become browsable without waiting for static HTML regeneration or canonical promotion. It supports text search and source filtering and refreshes from the event stream plus a short polling fallback.

The staging boundary is intentional: discovery data is saved immediately and visible immediately, but it is not silently promoted into the canonical catalog before enrichment and validation establish its identity/evidence quality.

Endpoints:

- `/` — canonical catalog dashboard plus live runtime counters
- `/discoveries` — live/staging discoveries from SQLite
- `/logs` — live event-log page with current database counters
- `/api/state` — current observation/listing/run state, history path and database size
- `/api/discoveries` — active staged listings with search/source filtering
- `/api/logs` — recent JSON event history
- `/api/events` — Server-Sent Events stream for live browser updates
- `/healthz` — dashboard and database health

The dashboard web service defaults to port `8788`, leaving `8787` available for the discovery service health endpoint.

Static dashboard regeneration remains supported. `--refresh-interval N` optionally rebuilds the static canonical catalog snapshot every N seconds, while database state, live discoveries and logs remain live regardless of that setting.

## systemd

`llm-cluster-install-service` does not insert an interval by default, so newly rendered service units scan continuously. Supply `--interval` only to intentionally create a scheduled service.

For a matched scanner + dashboard deployment, install both units together so they are guaranteed to use the same absolute history and event-log paths:

```bash
llm-cluster-install-service \
  --config config/discovery.example.json \
  --with-dashboard \
  --enable-now
```

This writes the discovery unit plus `llm-cluster-dashboard.service`. The installer resolves `--history`, `--event-log`, discovery output/cache and dashboard output to absolute paths before writing either unit.

### Upgrading an older install

Older deployments may have a dashboard unit pointed at `data/ingest/catalog.sqlite3`. That database uses the pre-live ingest schema and does not contain `observations`, `listing_state` and `refresh_runs`. The current dashboard detects that mismatch instead of reporting a misleading `0 observations · 0 active · idle` state. It also searches the nearby project `results/catalog-history.sqlite3` location and automatically uses it when a compatible live-history database already exists.

If no compatible history database exists, the dashboard reports `misconfigured` or `disconnected`; start/reinstall `llm-cluster-service` so the continuous scanner can create and populate the live history database.
