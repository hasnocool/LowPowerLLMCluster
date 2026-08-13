from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|token|secret|password|passwd|authorization|cookie|session|credential|private[_-]?key|client[_-]?secret)", re.I)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*", re.I),
)
_SENSITIVE_QUERY = {"api_key", "apikey", "key", "token", "access_token", "auth", "authorization", "password", "secret", "signature"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sanitize_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.scheme not in {"http", "https"}:
        return value
    userinfo_host = parsed.netloc.rsplit("@", 1)[-1]
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        query.append((key, "[REDACTED]" if key.lower() in _SENSITIVE_QUERY else item))
    return urlunsplit((parsed.scheme, userinfo_host, parsed.path, urlencode(query), parsed.fragment))


def sanitize(value: Any, *, key: str = "") -> Any:
    """Recursively redact common secret-bearing fields and values for repo-safe artifacts."""
    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): sanitize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize(item) for item in value]
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        text = value.replace(str(Path.home()), "~")
        text = _sanitize_url(text)
        for pattern in _SECRET_VALUE_PATTERNS:
            text = pattern.sub("[REDACTED]", text)
        return text
    return value


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(sanitize(value), indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def _tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists() or limit < 1:
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]


class DebugArtifactWriter:
    """Structured runtime debug artifacts with sanitization and bounded rotation."""

    def __init__(self, root: str | Path = "results/debug", *, max_log_bytes: int = 8 * 1024 * 1024, keep_runs: int = 20) -> None:
        self.root = Path(root).expanduser().resolve()
        self.max_log_bytes = max(64 * 1024, int(max_log_bytes))
        self.keep_runs = max(1, int(keep_runs))
        self.log_path = self.root / "runtime.jsonl"
        self._lock = asyncio.Lock()

    async def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        payload = sanitize({"ts": utc_now(), "event": event, **fields})
        async with self._lock:
            await asyncio.to_thread(self._append_sync, payload)
        return payload

    def _append_sync(self, payload: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists() and self.log_path.stat().st_size >= self.max_log_bytes:
            rotated = self.log_path.with_suffix(self.log_path.suffix + ".1")
            rotated.unlink(missing_ok=True)
            self.log_path.replace(rotated)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")

    async def write_run(
        self,
        run_id: str,
        *,
        summary: Mapping[str, Any],
        source_quality: Sequence[Mapping[str, Any]] = (),
        scheduler: Mapping[str, Any] | None = None,
        effective_config: Mapping[str, Any] | None = None,
    ) -> dict[str, str]:
        return await asyncio.to_thread(
            self._write_run_sync,
            run_id,
            dict(summary),
            list(source_quality),
            dict(scheduler or {}),
            dict(effective_config or {}),
        )

    def _write_run_sync(self, run_id: str, summary: dict[str, Any], source_quality: list[Mapping[str, Any]], scheduler: dict[str, Any], effective_config: dict[str, Any]) -> dict[str, str]:
        run_dir = self.root / "runs" / run_id
        files = {
            "summary": run_dir / "summary.json",
            "source_quality": run_dir / "source-quality.json",
            "scheduler": run_dir / "scheduler.json",
            "config": run_dir / "effective-config.redacted.json",
        }
        _write_atomic(files["summary"], _json_bytes(summary))
        _write_atomic(files["source_quality"], _json_bytes(source_quality))
        _write_atomic(files["scheduler"], _json_bytes(scheduler))
        _write_atomic(files["config"], _json_bytes(effective_config))
        latest = {
            "generated_at": utc_now(),
            "run_id": run_id,
            "files": {name: str(path) for name, path in files.items()},
        }
        _write_atomic(self.root / "latest.json", _json_bytes(latest))
        self._prune_runs_sync()
        return {name: str(path) for name, path in files.items()}

    def _prune_runs_sync(self) -> None:
        runs = self.root / "runs"
        if not runs.exists():
            return
        children = sorted((path for path in runs.iterdir() if path.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in children[self.keep_runs:]:
            shutil.rmtree(path, ignore_errors=True)


def _read_source_quality(history: Path) -> list[dict[str, Any]]:
    if not history.exists():
        return []
    try:
        connection = sqlite3.connect(history)
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM source_quality ORDER BY quality_score DESC, source").fetchall()
    except sqlite3.Error:
        return []
    finally:
        try:
            connection.close()
        except Exception:
            pass
    return [dict(row) for row in rows]


def export_repo_debug_bundle(
    *,
    destination: str | Path,
    debug_dir: str | Path = "results/debug",
    history: str | Path = "results/catalog-history.sqlite3",
    config: str | Path = "config/discovery.example.json",
    event_log: str | Path = "results/events.jsonl",
    latest_output: str | Path = "results/discovery-latest.json",
    tail_lines: int = 500,
) -> Path:
    """Create a sanitized diagnostic directory intended to be safe to commit to a repository."""
    dest = Path(destination).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    debug_root = Path(debug_dir).expanduser().resolve()
    history_path = Path(history).expanduser().resolve()
    config_path = Path(config).expanduser().resolve()
    event_path = Path(event_log).expanduser().resolve()
    latest_path = Path(latest_output).expanduser().resolve()

    config_payload: Any = {}
    if config_path.exists():
        try:
            config_payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config_payload = {"read_error": True, "path": str(config_path)}
    latest_payload: Any = {}
    if latest_path.exists():
        try:
            latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest_payload = {"read_error": True, "path": str(latest_path)}

    artifacts: dict[str, bytes] = {
        "effective-config.redacted.json": _json_bytes(config_payload),
        "latest-run.json": _json_bytes(latest_payload),
        "source-quality.json": _json_bytes(_read_source_quality(history_path)),
        "environment.json": _json_bytes({
            "generated_at": utc_now(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executable": Path(sys.executable).name,
        }),
    }
    runtime_tail = "\n".join(_tail_lines(debug_root / "runtime.jsonl", tail_lines))
    event_tail = "\n".join(_tail_lines(event_path, tail_lines))
    artifacts["runtime-tail.jsonl"] = ((runtime_tail + "\n") if runtime_tail else "").encode("utf-8")
    artifacts["events-tail.jsonl"] = ((event_tail + "\n") if event_tail else "").encode("utf-8")
    readme = """# LowPowerLLMCluster debug bundle\n\nThis directory was generated for repository-safe debugging. Secret-like keys, authentication material, cookies, and common token formats are redacted. Review the files before publishing. Raw HTTP bodies and the full SQLite database are intentionally excluded.\n"""
    artifacts["README.md"] = readme.encode("utf-8")

    manifest_files: list[dict[str, Any]] = []
    for name, raw in artifacts.items():
        if name.endswith(".jsonl"):
            cleaned_lines: list[str] = []
            for line in raw.decode("utf-8", errors="replace").splitlines():
                try:
                    cleaned_lines.append(json.dumps(sanitize(json.loads(line)), sort_keys=True, default=str))
                except json.JSONDecodeError:
                    cleaned_lines.append(str(sanitize(line)))
            raw = (("\n".join(cleaned_lines) + "\n") if cleaned_lines else "").encode("utf-8")
        _write_atomic(dest / name, raw)
        manifest_files.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    manifest = {"generated_at": utc_now(), "repo_safe": True, "files": manifest_files}
    _write_atomic(dest / "manifest.json", _json_bytes(manifest))
    return dest
