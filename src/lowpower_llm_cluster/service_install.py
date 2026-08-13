from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
from pathlib import Path


def render_systemd_unit(*, service_command: str, config: str, history: str, output: str, cache: str, interval: float | None, extra_args: list[str] | None = None) -> str:
    args = [service_command, "--config", config, "--history", history, "--output", output, "--cache", cache]
    if interval is not None:
        args.extend(["--interval", str(interval)])
    args.extend(extra_args or [])
    command = " ".join(shlex.quote(value) for value in args)
    mode = "continuous" if interval is None else f"scheduled every {interval:g}s"
    return f"""[Unit]\nDescription=LowPowerLLMCluster discovery service ({mode})\nAfter=network-online.target\nWants=network-online.target\nStartLimitIntervalSec=300\nStartLimitBurst=5\n\n[Service]\nType=simple\nExecStart={command}\nRestart=on-failure\nRestartSec=10\nTimeoutStopSec=30\nNice=5\nIOSchedulingClass=idle\nNoNewPrivileges=true\nPrivateTmp=true\nUMask=0077\n\n[Install]\nWantedBy=default.target\n"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or render the LowPowerLLMCluster systemd service")
    parser.add_argument("--config", required=True)
    parser.add_argument("--history", default="results/catalog-history.sqlite3")
    parser.add_argument("--output", default="results/discovery-latest.json")
    parser.add_argument("--cache", default="results/catalog-http-cache.json")
    parser.add_argument("--interval", type=float, default=None, help="optional delay between scan starts; omit for continuous scanning")
    parser.add_argument("--unit-name", default="lowpower-llm-cluster.service")
    parser.add_argument("--system", action="store_true")
    parser.add_argument("--destination")
    parser.add_argument("--enable-now", action="store_true")
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
    service = shutil.which("llm-cluster-service") or "llm-cluster-service"
    destination = Path(args.destination) if args.destination else (Path("/etc/systemd/system") / args.unit_name if args.system else Path.home() / ".config/systemd/user" / args.unit_name)
    config = str(Path(args.config).expanduser().resolve())
    history = str(Path(args.history).expanduser().resolve())
    output = str(Path(args.output).expanduser().resolve())
    cache = str(Path(args.cache).expanduser().resolve())
    extra: list[str] = []
    if args.distributed_coordinator:
        extra.extend(["--distributed-coordinator", args.distributed_coordinator])
    for flag, value in (("--distributed-admin-token-file", args.distributed_admin_token_file), ("--distributed-tls-ca", args.distributed_tls_ca), ("--distributed-tls-cert", args.distributed_tls_cert), ("--distributed-tls-key", args.distributed_tls_key), ("--otlp-endpoint", args.otlp_endpoint)):
        if value:
            extra.extend([flag, str(Path(value).expanduser().resolve()) if flag != "--otlp-endpoint" else str(value)])
    if args.distributed_poll_s is not None: extra.extend(["--distributed-poll-s", str(args.distributed_poll_s)])
    if args.distributed_timeout_s is not None: extra.extend(["--distributed-timeout-s", str(args.distributed_timeout_s)])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_systemd_unit(service_command=service, config=config, history=history, output=output, cache=cache, interval=args.interval, extra_args=extra), encoding="utf-8")
    print(destination)
    if args.enable_now:
        systemctl = ["systemctl", *([] if args.system else ["--user"])]
        subprocess.run([*systemctl, "daemon-reload"], check=True)
        subprocess.run([*systemctl, "enable", "--now", args.unit_name], check=True)
    return 0


if __name__ == "__main__": raise SystemExit(main())
