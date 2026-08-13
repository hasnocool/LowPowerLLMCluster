from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
from pathlib import Path


def render_systemd_unit(*, service_command: str, config: str, history: str, output: str, cache: str, interval: float, extra_args: list[str] | None = None) -> str:
    args = [service_command, "--config", config, "--history", history, "--output", output, "--cache", cache, "--interval", str(interval), *(extra_args or [])]
    command = " ".join(shlex.quote(value) for value in args)
    return f"""[Unit]\nDescription=LowPowerLLMCluster discovery service\nAfter=network-online.target\nWants=network-online.target\nStartLimitIntervalSec=300\nStartLimitBurst=5\n\n[Service]\nType=simple\nExecStart={command}\nRestart=on-failure\nRestartSec=10\nTimeoutStopSec=30\nNice=5\nIOSchedulingClass=idle\nNoNewPrivileges=true\nPrivateTmp=true\nUMask=0077\n\n[Install]\nWantedBy=default.target\n"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or render the LowPowerLLMCluster systemd service")
    parser.add_argument("--config", required=True)
    parser.add_argument("--history", default="results/catalog-history.sqlite3")
    parser.add_argument("--output", default="results/discovery-latest.json")
    parser.add_argument("--cache", default="results/catalog-http-cache.json")
    parser.add_argument("--interval", type=float, default=300.0)
    parser.add_argument("--unit-name", default="lowpower-llm-cluster.service")
    parser.add_argument("--system", action="store_true")
    parser.add_argument("--destination")
    parser.add_argument("--enable-now", action="store_true")
    args = parser.parse_args()
    service = shutil.which("llm-cluster-service") or "llm-cluster-service"
    destination = Path(args.destination) if args.destination else (Path("/etc/systemd/system") / args.unit_name if args.system else Path.home() / ".config/systemd/user" / args.unit_name)
    config = str(Path(args.config).expanduser().resolve())
    history = str(Path(args.history).expanduser().resolve())
    output = str(Path(args.output).expanduser().resolve())
    cache = str(Path(args.cache).expanduser().resolve())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_systemd_unit(service_command=service, config=config, history=history, output=output, cache=cache, interval=args.interval), encoding="utf-8")
    print(destination)
    if args.enable_now:
        systemctl = ["systemctl", *([] if args.system else ["--user"])]
        subprocess.run([*systemctl, "daemon-reload"], check=True)
        subprocess.run([*systemctl, "enable", "--now", args.unit_name], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
