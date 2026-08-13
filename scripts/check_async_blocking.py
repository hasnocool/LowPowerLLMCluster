from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = tuple(
    ROOT / "src" / "lowpower_llm_cluster" / name
    for name in (
        "discovery.py",
        "http_runtime.py",
        "streaming_discovery.py",
        "catalog_refresh.py",
        "history.py",
        "runtime.py",
        "source_runtime.py",
        "process_adapter.py",
        "service_cli.py",
        "service_runtime.py",
        "service_install.py",
        "distributed_runtime.py",
        "distributed_cli.py",
        "distributed_cli_secure.py",
        "distributed_cli_common.py",
        "distributed_security.py",
        "secure_distributed.py",
        "secure_store.py",
        "secure_store_results.py",
        "secure_store_tasks.py",
        "secure_store_base.py",
        "secure_server.py",
        "secure_client.py",
        "distributed_service.py",
        "content_store.py",
        "snapshot_http.py",
        "resource_runtime.py",
        "telemetry_runtime.py",
        "fault_injection.py",
    )
)
BLOCKING_CALLS = {
    "open", "time.sleep", "sqlite3.connect", "urllib.request.urlopen",
    "subprocess.run", "subprocess.call", "subprocess.Popen",
    "requests.get", "requests.post", "requests.request", "Path.read_text", "Path.write_text",
}
CPU_HEAVY_CALLS = {"json.loads", "json.dumps"}


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def scan(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    errors: list[str] = []
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)):
        for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
            name = dotted_name(call.func)
            leaf = name.rsplit(".", 1)[-1]
            if name in BLOCKING_CALLS or leaf in {"read_text", "write_text", "urlopen"}:
                errors.append(f"{path.relative_to(ROOT)}:{call.lineno}: blocking call {name!r} inside async {function.name}()")
            if name in CPU_HEAVY_CALLS:
                errors.append(f"{path.relative_to(ROOT)}:{call.lineno}: CPU-heavy {name!r} runs directly inside async {function.name}()")
    return errors


def main() -> int:
    errors = [error for path in TARGETS for error in scan(path)]
    if errors:
        print("Async blocking guard failed:", file=sys.stderr)
        for error in errors: print(f"- {error}", file=sys.stderr)
        return 1
    print("Async blocking guard passed for local, resilient, secure-distributed and daemon runtime paths.")
    return 0


if __name__ == "__main__": raise SystemExit(main())
