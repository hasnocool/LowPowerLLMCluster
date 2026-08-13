from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
from pathlib import Path


def _command(args: list[str]) -> str:
    return " ".join(shlex.quote(value) for value in args)


def render_systemd_unit(
    *,
    service_command: str,
    config: str,
    history: str,
    output: str,
    cache: str,
    event_log: str = "results/events.jsonl",
    interval: float | None,
    extra_args: list[str] | None = None,
) -> str:
    args = [
        service_command,
        "--config", config,
        "--history", history,
        "--output", output,
        "--cache", cache,
        "--event-log", event_log,
    ]
    if interval is not None:
        args.extend(["--interval", str(interval)])
    args.extend(extra_args or [])
    mode = "continuous" if interval is None else f"scheduled every {interval:g}s"
    return f"""[Unit]\nDescription=LowPowerLLMCluster discovery service ({mode})\nAfter=network-online.target\nWants=network-online.target\nStartLimitIntervalSec=300\nStartLimitBurst=5\n\n[Service]\nType=simple\nExecStart={_command(args)}\nRestart=on-failure\nRestartSec=10\nTimeoutStopSec=30\nNice=5\nIOSchedulingClass=idle\nNoNewPrivileges=true\nPrivateTmp=true\nUMask=0077\n\n[Install]\nWantedBy=default.target\n"""


def render_dashboard_systemd_unit(
    *,
    dashboard_command: str,
    history: str,
    event_log: str,
    output: str,
    host: str,
    port: int,
    db_poll: float,
) -> str:
    args = [
        dashboard_command,
        "--history", history,
        "--event-log", event_log,
        "--output", output,
        "--host", host,
        "--port", str(port),
        "--db-poll", str(db_poll),
    ]
    return f"""[Unit]\nDescription=LowPowerLLMCluster live dashboard\nAfter=network-online.target lowpower-llm-cluster.service\nWants=network-online.target\n\n[Service]\nType=simple\nExecStart={_command(args)}\nRestart=on-failure\nRestartSec=5\nNoNewPrivileges=true\nPrivateTmp=true\nUMask=0077\n\n[Install]\nWantedBy=default.target\n"""


def _systemctl(system: bool) -> list[str]:
    return ["systemctl", *([] if system else ["--user"])]


def main() -> int:
    parser = argparse.ArgumentParser(description="Install LowPowerLLMCluster continuous discovery and optional live dashboard services")
    parser.add_argument("--config", required=True)
    parser.add_argument("--history", default="results/catalog-history.sqlite3")
    parser.add_argument("--output", default="results/discovery-latest.json")
    parser.add_argument("--cache", default="results/catalog-http-cache.json")
    parser.add_argument("--event-log", default="results/events.jsonl")
    parser.add_argument("--interval", type=float, default=None, help="optional delay between scan starts; omit for continuous scanning")
    parser.add_argument("--unit-name", default="lowpower-llm-cluster.service")
    parser.add_argument("--system", action="store_true")
    parser.add_argument("--destination")
    parser.add_argument("--enable-now", action="store_true")
    parser.add_argument("--with-dashboard", action="store_true", help="install a dashboard service wired to the same history/event files")
    parser.add_argument("--dashboard-unit-name", default="llm-cluster-dashboard.service")
    parser.add_argument("--dashboard-destination")
    parser.add_argument("--dashboard-output", default="results/catalog-dashboard.html")
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--dashboard-port", type=int, default=8788)
    parser.add_argument("--dashboard-db-poll", type=float, default=0.5)
    parser.add_argument("--distributed-coordinator")
    parser.add_argument("--distributed-admin-token-file", help="preferred over embedding a token in the unit")
    parser.add_argument("--distributed-tls-ca")
    parser.add_argument("--distributed-tls-cert")
    parser.add_argument("--distributed-tls-key")
    parser.add_argument("--distributed-poll-s", type=float)
    parser.add_argument("--distributed-timeout-s", type=float)
    parser.add_argument("--otlp-endpoint")
    args = parser.parse_args()

    if args.interval is not None and args.interval <= 0:
        parser.error("--interval must be positive when supplied")
    if args.dashboard_port < 1 or args.dashboard_db_poll <= 0:
        parser.error("dashboard port and polling interval must be positive")

    base_dir = Path("/etc/systemd/system") if args.system else Path.home() / ".config/systemd/user"
    service = shutil.which("llm-cluster-service") or "llm-cluster-service"
    dashboard_service = shutil.which("llm-cluster-dashboard") or "llm-cluster-dashboard"
    destination = Path(args.destination) if args.destination else base_dir / args.unit_name

    config = str(Path(args.config).expanduser().resolve())
    history = str(Path(args.history).expanduser().resolve())
    output = str(Path(args.output).expanduser().resolve())
    cache = str(Path(args.cache).expanduser().resolve())
    event_log = str(Path(args.event_log).expanduser().resolve())
    dashboard_output = str(Path(args.dashboard_output).expanduser().resolve())

    for path in (Path(history), Path(output), Path(cache), Path(event_log), Path(dashboard_output)):
        path.parent.mkdir(parents=True, exist_ok=True)

    extra: list[str] = []
    if args.distributed_coordinator:
        extra.extend(["--distributed-coordinator", args.distributed_coordinator])
    for flag, value in (
        ("--distributed-admin-token-file", args.distributed_admin_token_file),
        ("--distributed-tls-ca", args.distributed_tls_ca),
        ("--distributed-tls-cert", args.distributed_tls_cert),
        ("--distributed-tls-key", args.distributed_tls_key),
        ("--otlp-endpoint", args.otlp_endpoint),
    ):
        if value:
            extra.extend([flag, str(Path(value).expanduser().resolve()) if flag != "--otlp-endpoint" else str(value)])
    if args.distributed_poll_s is not None:
        extra.extend(["--distributed-poll-s", str(args.distributed_poll_s)])
    if args.distributed_timeout_s is not None:
        extra.extend(["--distributed-timeout-s", str(args.distributed_timeout_s)])

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_systemd_unit(
            service_command=service,
            config=config,
            history=history,
            output=output,
            cache=cache,
            event_log=event_log,
            interval=args.interval,
            extra_args=extra,
        ),
        encoding="utf-8",
    )
    print(destination)

    installed_units = [args.unit_name]
    if args.with_dashboard:
        dashboard_destination = Path(args.dashboard_destination) if args.dashboard_destination else base_dir / args.dashboard_unit_name
        dashboard_destination.parent.mkdir(parents=True, exist_ok=True)
        dashboard_destination.write_text(
            render_dashboard_systemd_unit(
                dashboard_command=dashboard_service,
                history=history,
                event_log=event_log,
                output=dashboard_output,
                host=args.dashboard_host,
                port=args.dashboard_port,
                db_poll=args.dashboard_db_poll,
            ),
            encoding="utf-8",
        )
        print(dashboard_destination)
        installed_units.append(args.dashboard_unit_name)

    if args.enable_now:
        systemctl = _systemctl(args.system)
        subprocess.run([*systemctl, "daemon-reload"], check=True)
        for unit in installed_units:
            subprocess.run([*systemctl, "enable", "--now", unit], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
