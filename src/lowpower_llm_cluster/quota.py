# src/lowpower_llm_cluster/quota.py
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
from typing import Any, Mapping

from .catalog import project_root


_REMAINING_HEADERS = (
    "ratelimit-remaining",
    "x-ratelimit-remaining",
    "x-rate-limit-remaining",
    "x-ratelimit-remaining-requests",
)
_LIMIT_HEADERS = (
    "ratelimit-limit",
    "x-ratelimit-limit",
    "x-rate-limit-limit",
    "x-ratelimit-limit-requests",
)
_RESET_AT_HEADERS = (
    "ratelimit-reset",
    "x-ratelimit-reset",
    "x-rate-limit-reset",
)
_RESET_AFTER_HEADERS = (
    "ratelimit-reset-after",
    "x-ratelimit-reset-after",
    "x-rate-limit-reset-after",
)


@dataclass(frozen=True, slots=True)
class ProviderQuotaSnapshot:
    provider: str
    observed_at: str
    remaining: float | None
    limit: float | None
    reset_at: str | None
    reset_after_s: float | None
    reset_raw: str | None
    header_names: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _headers(headers: Mapping[str, Any]) -> dict[str, str]:
    return {str(key).strip().casefold(): str(value).strip() for key, value in headers.items()}


def _first(headers: Mapping[str, str], names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in names:
        value = headers.get(name)
        if value not in (None, ""):
            return name, value
    return None, None


def _number(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _reset_timestamp(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None and numeric >= 100_000_000:
        try:
            return datetime.fromtimestamp(numeric, UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def parse_provider_quota(
    provider: str,
    headers: Mapping[str, Any],
    *,
    observed_at: str | None = None,
) -> ProviderQuotaSnapshot | None:
    """Parse common provider-reported quota headers without inventing missing reset semantics."""
    normalized = _headers(headers)
    remaining_name, remaining_raw = _first(normalized, _REMAINING_HEADERS)
    limit_name, limit_raw = _first(normalized, _LIMIT_HEADERS)
    reset_name, reset_raw = _first(normalized, _RESET_AT_HEADERS)
    reset_after_name, reset_after_raw = _first(normalized, _RESET_AFTER_HEADERS)
    if not any((remaining_name, limit_name, reset_name, reset_after_name)):
        return None

    reset_after = _number(reset_after_raw)
    if reset_after is not None and reset_after < 0:
        reset_after = None
    names = tuple(name for name in (remaining_name, limit_name, reset_name, reset_after_name) if name)
    return ProviderQuotaSnapshot(
        provider=provider or "unknown",
        observed_at=observed_at or datetime.now(UTC).isoformat(),
        remaining=_number(remaining_raw),
        limit=_number(limit_raw),
        reset_at=_reset_timestamp(reset_raw),
        reset_after_s=reset_after,
        reset_raw=reset_raw or reset_after_raw,
        header_names=names,
    )


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "providers": {}, "history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


class ProviderQuotaHistory:
    """Restart-safe latest + append-only quota observations for providers that expose them."""

    def __init__(self, path: Path | None = None, *, history_limit: int = 10_000) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        self.path = path or project_root() / "data" / "market" / "provider-quotas.json"
        self.history_limit = history_limit
        self._lock = asyncio.Lock()

    async def observe(self, provider: str, headers: Mapping[str, Any], *, observed_at: str | None = None) -> ProviderQuotaSnapshot | None:
        snapshot = parse_provider_quota(provider, headers, observed_at=observed_at)
        if snapshot is None:
            return None
        async with self._lock:
            payload = await asyncio.to_thread(_read, self.path)
            row = snapshot.to_dict()
            payload.setdefault("providers", {})[snapshot.provider] = row
            history = payload.setdefault("history", [])
            duplicate = bool(history and history[-1] == row)
            if not duplicate:
                history.append(row)
                if len(history) > self.history_limit:
                    del history[: len(history) - self.history_limit]
            await asyncio.to_thread(_write, self.path, payload)
        return snapshot

    async def latest(self, provider: str | None = None) -> dict[str, Any]:
        payload = await asyncio.to_thread(_read, self.path)
        providers = dict(payload.get("providers", {}))
        if provider is None:
            return providers
        return dict(providers.get(provider, {}))
