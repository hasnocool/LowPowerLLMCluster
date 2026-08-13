# Distributed Security Model

The v2 distributed protocol secures **transport**, **worker identity**, **administrative authority**, **replay resistance** and **leadership fencing** as separate controls.

## Trust boundaries

- **Admin token**: can submit/cancel cycles, read results/worker state, drain/undrain workers and request backups.
- **Worker secret**: authenticates exactly one worker ID and allows register/lease/heartbeat/batch/complete/fail/self-drain for that identity.
- **TLS server key**: proves the coordinator endpoint to clients and encrypts traffic.
- **mTLS worker certificate**: optional second transport identity/control. HMAC worker identity still applies.
- **Coordinator epoch**: prevents an old leader or stale worker lease from committing after failover.
- **CAS SHA-256 digest**: addresses immutable payloads and detects accidental/malicious content substitution when the digest is verified by storage lookup.

Do not reuse the admin token as a worker secret.

## Request signing

Worker HMAC canonical form:

```text
METHOD\n
RAW_PATH_AND_QUERY\n
SHA256(BODY)\n
UNIX_TIMESTAMP\n
NONCE
```

The coordinator rejects:

- unknown worker IDs;
- invalid HMAC signatures;
- timestamps outside the configured skew window;
- repeated `(worker_id, nonce)` pairs;
- mutations for a lease not owned by that worker;
- mutations carrying a stale coordinator epoch.

## Credential storage

`init-auth` creates a `0600` JSON file. Treat it like a password database:

- do not commit it;
- back it up separately from public repository data;
- distribute only each worker's own secret to that worker;
- prefer mounted secret files over command-line tokens;
- rotate credentials when a node is repurposed/lost.

The built-in registry is intentionally small and file-backed. External secret-manager integration and automatic certificate/secret rotation remain a later operational-hardening layer.

## TLS guidance

For deployed coordinators:

1. use a hostname covered by the server certificate;
2. distribute the issuing CA to workers/admin clients;
3. enable mTLS when you control worker certificates;
4. keep the coordinator behind a firewall/VPN even with TLS;
5. never use `--tls-insecure-skip-verify` outside a disposable development environment.

## HA boundary

Active/standby leadership is lease + epoch fencing over one durable task-state database. It is **not a quorum protocol**. A network partition combined with storage that presents inconsistent views can still defeat the assumptions of this design.

For installations that require independent coordinators across failure domains, the next step is an external consensus/state service rather than attempting SQLite multi-master replication.
