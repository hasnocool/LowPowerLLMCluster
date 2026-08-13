# Continuous scanning and live dashboard

`llm-cluster-service` now treats continuous operation as the default. When `--interval` is omitted, a new discovery cycle starts immediately after the previous cycle finishes. This keeps the crawler processing as fast as the configured source limits, adaptive concurrency, circuit breakers and HTTP backoff allow.

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

Endpoints:

- `/` — catalog dashboard with a live activity indicator
- `/logs` — live event-log page with current database counters
- `/api/state` — current observation/listing/run state
- `/api/logs` — recent JSON event history
- `/api/events` — Server-Sent Events stream for live browser updates
- `/healthz` — dashboard and database health

The dashboard web service defaults to port `8788`, leaving `8787` available for the discovery service health endpoint.

Static dashboard regeneration remains supported. `--refresh-interval N` optionally rebuilds the static catalog snapshot every N seconds, while database state and logs remain live regardless of that setting.

## systemd

`llm-cluster-install-service` no longer inserts an interval by default, so newly rendered service units scan continuously. Supply `--interval` to intentionally create a scheduled service.
