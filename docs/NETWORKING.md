# Networking

## Start with 2.5GbE

For independent inference workers, 2.5GbE is inexpensive and fast enough for API requests, model management, telemetry and ordinary file movement.

```text
                     INTERNET / CLIENT LAN
                              │
                         ┌────┴────┐
                         │ ROUTER  │
                         └────┬────┘
                              │
                      ┌───────┴────────┐
                      │ 8-port 2.5GbE  │
                      │     switch     │
                      └─┬──┬──┬──┬──┬─┘
                        │  │  │  │  │
                        ▼  ▼  ▼  ▼  ▼
                       N1 N2 N3 N4 N5
```

## When 10GbE matters

Upgrade the backbone when you are frequently moving large model files, using shared NVMe storage, or experimenting heavily with distributed model execution. Even 10GbE is far slower than local DDR5, so faster Ethernet improves sharding but does not erase the local-memory advantage.
