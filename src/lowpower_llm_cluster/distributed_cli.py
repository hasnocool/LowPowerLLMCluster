from __future__ import annotations

import argparse
import asyncio
import socket

from .distributed_cli_common import run_collect, run_coordinator, run_status, run_submit, run_worker
from .distributed_cli_secure import run_backup, run_cancel, run_drain, run_init_auth, run_restore, run_undrain, run_workers

def _add_secure_admin_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--admin-token")
    parser.add_argument("--admin-token-file")
    parser.add_argument("--tls-ca")
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--tls-insecure-skip-verify", action="store_true")


def main() -> int:
    parser = argparse.ArgumentParser(description="Distributed LowPowerLLMCluster source-worker backend")
    sub = parser.add_subparsers(dest="command", required=True)
    coordinator = sub.add_parser("coordinator")
    coordinator.add_argument("--state", default="results/distributed-tasks.sqlite3"); coordinator.add_argument("--artifacts", default="results/distributed-artifacts")
    coordinator.add_argument("--host", default="0.0.0.0"); coordinator.add_argument("--port", type=int, default=8788)
    coordinator.add_argument("--auth-file", help="enable authenticated v2 coordinator")
    coordinator.add_argument("--node-id", default=socket.gethostname()); coordinator.add_argument("--standby", action="store_true"); coordinator.add_argument("--leader-lease-s", type=float, default=10)
    coordinator.add_argument("--tls-cert"); coordinator.add_argument("--tls-key"); coordinator.add_argument("--tls-client-ca"); coordinator.add_argument("--require-client-cert", action="store_true")
    submit = sub.add_parser("submit"); submit.add_argument("--coordinator", required=True); submit.add_argument("--config", required=True); submit.add_argument("--cycle-id"); _add_secure_admin_args(submit)
    status = sub.add_parser("status"); status.add_argument("--coordinator", required=True); status.add_argument("--cycle-id", required=True); _add_secure_admin_args(status)
    collect = sub.add_parser("collect"); collect.add_argument("--coordinator", required=True); collect.add_argument("--cycle-id", required=True); collect.add_argument("--config", required=True)
    collect.add_argument("--history", default="results/catalog-history.sqlite3"); collect.add_argument("--output", default="results/discovery-latest.json"); collect.add_argument("--wait", action="store_true"); collect.add_argument("--timeout-s", type=float, default=3600); collect.add_argument("--poll-s", type=float, default=2); _add_secure_admin_args(collect)
    worker = sub.add_parser("worker"); worker.add_argument("--coordinator", required=True); worker.add_argument("--config", required=True); worker.add_argument("--cache", default="results/worker-http-cache.json"); worker.add_argument("--worker-id")
    worker.add_argument("--worker-secret"); worker.add_argument("--worker-secret-file"); worker.add_argument("--capability", action="append"); worker.add_argument("--label", action="append")
    worker.add_argument("--power-budget-w", type=float); worker.add_argument("--energy-budget-wh", type=float); worker.add_argument("--shared-snapshot-dir"); worker.add_argument("--snapshot-max-age-s", type=float); worker.add_argument("--prefer-snapshot", action="store_true")
    worker.add_argument("--lease-s", type=float, default=60); worker.add_argument("--heartbeat-s", type=float, default=20); worker.add_argument("--poll-s", type=float, default=2); worker.add_argument("--work-steal-after-s", type=float, default=60); worker.add_argument("--max-attempts", type=int, default=5); worker.add_argument("--once", action="store_true")
    worker.add_argument("--tls-ca"); worker.add_argument("--tls-cert"); worker.add_argument("--tls-key"); worker.add_argument("--tls-insecure-skip-verify", action="store_true")
    for name in ("workers", "drain", "undrain", "cancel", "backup"):
        command = sub.add_parser(name); command.add_argument("--coordinator", required=True); _add_secure_admin_args(command)
        if name in {"drain", "undrain"}: command.add_argument("--worker-id", required=True)
        if name == "cancel": command.add_argument("--cycle-id", required=True)
        if name == "backup": command.add_argument("--destination", required=True)
    restore = sub.add_parser("restore-state"); restore.add_argument("--backup", required=True); restore.add_argument("--state", default="results/distributed-tasks.sqlite3")
    init_auth = sub.add_parser("init-auth"); init_auth.add_argument("--output", default="config/distributed-auth.json"); init_auth.add_argument("--worker", action="append", required=True)
    args = parser.parse_args()
    functions = {"coordinator":run_coordinator,"submit":run_submit,"status":run_status,"collect":run_collect,"worker":run_worker,"workers":run_workers,"drain":run_drain,"undrain":run_undrain,"cancel":run_cancel,"backup":run_backup,"restore-state":run_restore,"init-auth":run_init_auth}
    return asyncio.run(functions[args.command](args))


if __name__ == "__main__": raise SystemExit(main())
