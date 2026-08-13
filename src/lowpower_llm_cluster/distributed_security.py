from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import ssl
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

AUTH_WORKER_HEADER = "X-LPLLM-Worker"
AUTH_TIMESTAMP_HEADER = "X-LPLLM-Timestamp"
AUTH_NONCE_HEADER = "X-LPLLM-Nonce"
AUTH_SIGNATURE_HEADER = "X-LPLLM-Signature"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class WorkerCredential:
    worker_id: str
    secret: str
    roles: tuple[str, ...] = ("worker",)


class AuthRegistry:
    """Small file-backed worker/admin credential registry.

    This intentionally avoids a database-side secret store. Rotate the credential file
    atomically and restart/reload the coordinator. Secrets are never returned by APIs.
    """

    def __init__(self, workers: Mapping[str, WorkerCredential], *, admin_tokens: tuple[str, ...] = ()) -> None:
        self.workers = dict(workers)
        self.admin_tokens = tuple(token for token in admin_tokens if token)

    @classmethod
    def load(cls, path: Path | str) -> "AuthRegistry":
        raw = _read_json(Path(path))
        workers: dict[str, WorkerCredential] = {}
        for worker_id, item in dict(raw.get("workers", {})).items():
            if isinstance(item, str):
                secret, roles = item, ("worker",)
            else:
                secret = str(item.get("secret", ""))
                roles = tuple(str(role) for role in item.get("roles", ("worker",)))
            if not secret:
                raise ValueError(f"worker {worker_id!r} has no secret")
            workers[str(worker_id)] = WorkerCredential(str(worker_id), secret, roles)
        admin = raw.get("admin_tokens", raw.get("admin_token", ()))
        if isinstance(admin, str):
            admin_tokens = (admin,)
        else:
            admin_tokens = tuple(str(item) for item in admin)
        return cls(workers, admin_tokens=admin_tokens)

    def worker(self, worker_id: str) -> WorkerCredential | None:
        return self.workers.get(worker_id)

    def admin_ok(self, token: str) -> bool:
        return any(hmac.compare_digest(token, expected) for expected in self.admin_tokens)


def body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def worker_signature(secret: str, *, method: str, path_qs: str, body: bytes, timestamp: str, nonce: str) -> str:
    canonical = "\n".join((method.upper(), path_qs, body_sha256(body), timestamp, nonce)).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def signed_worker_headers(worker_id: str, secret: str, *, method: str, path_qs: str, body: bytes = b"", now: float | None = None) -> dict[str, str]:
    timestamp = str(int(time.time() if now is None else now))
    nonce = secrets.token_hex(16)
    return {
        AUTH_WORKER_HEADER: worker_id,
        AUTH_TIMESTAMP_HEADER: timestamp,
        AUTH_NONCE_HEADER: nonce,
        AUTH_SIGNATURE_HEADER: worker_signature(secret, method=method, path_qs=path_qs, body=body, timestamp=timestamp, nonce=nonce),
    }


class ReplayWindow:
    """Bounded nonce replay cache for signed worker requests."""

    def __init__(self, *, max_age_s: float = 120.0, max_entries: int = 100_000) -> None:
        self.max_age_s = max(1.0, float(max_age_s))
        self.max_entries = max(100, int(max_entries))
        self._seen: dict[tuple[str, str], float] = {}
        self._order: deque[tuple[float, tuple[str, str]]] = deque()

    def accept(self, worker_id: str, nonce: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        cutoff = current - self.max_age_s
        while self._order and self._order[0][0] < cutoff:
            seen_time, key = self._order.popleft()
            if self._seen.get(key) == seen_time:
                self._seen.pop(key, None)
        key = (worker_id, nonce)
        if key in self._seen:
            return False
        self._seen[key] = current
        self._order.append((current, key))
        while len(self._seen) > self.max_entries and self._order:
            seen_time, oldest = self._order.popleft()
            if self._seen.get(oldest) == seen_time:
                self._seen.pop(oldest, None)
        return True


def verify_worker_request(
    registry: AuthRegistry,
    replay: ReplayWindow,
    *,
    method: str,
    path_qs: str,
    body: bytes,
    headers: Mapping[str, str],
    now: float | None = None,
    max_clock_skew_s: float = 90.0,
) -> WorkerCredential:
    worker_id = str(headers.get(AUTH_WORKER_HEADER, ""))
    timestamp = str(headers.get(AUTH_TIMESTAMP_HEADER, ""))
    nonce = str(headers.get(AUTH_NONCE_HEADER, ""))
    supplied = str(headers.get(AUTH_SIGNATURE_HEADER, ""))
    credential = registry.worker(worker_id)
    if credential is None or not timestamp or not nonce or not supplied:
        raise PermissionError("missing or unknown worker authentication")
    try:
        request_time = float(timestamp)
    except ValueError as exc:
        raise PermissionError("invalid worker timestamp") from exc
    current = time.time() if now is None else now
    if abs(current - request_time) > max_clock_skew_s:
        raise PermissionError("worker request timestamp outside allowed clock skew")
    expected = worker_signature(credential.secret, method=method, path_qs=path_qs, body=body, timestamp=timestamp, nonce=nonce)
    if not hmac.compare_digest(supplied, expected):
        raise PermissionError("invalid worker signature")
    if not replay.accept(worker_id, nonce, now=current):
        raise PermissionError("replayed worker request")
    return credential


def build_server_ssl_context(*, cert: Path | str, key: Path | str, client_ca: Path | str | None = None, require_client_cert: bool = False) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    if client_ca is not None:
        context.load_verify_locations(cafile=str(client_ca))
    if require_client_cert:
        if client_ca is None:
            raise ValueError("client_ca is required when mTLS client certificates are required")
        context.verify_mode = ssl.CERT_REQUIRED
    else:
        context.verify_mode = ssl.CERT_OPTIONAL if client_ca is not None else ssl.CERT_NONE
    return context


def build_client_ssl_context(*, ca: Path | str | None = None, cert: Path | str | None = None, key: Path | str | None = None, insecure_skip_verify: bool = False) -> ssl.SSLContext:
    if insecure_skip_verify:
        context = ssl._create_unverified_context()  # noqa: SLF001 - explicit opt-in CLI escape hatch
    else:
        context = ssl.create_default_context(cafile=None if ca is None else str(ca))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if cert is not None:
        context.load_cert_chain(str(cert), None if key is None else str(key))
    return context
