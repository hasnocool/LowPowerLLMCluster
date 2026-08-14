from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FailurePolicy:
    failure_class: str
    base_cooldown_cycles: int
    max_cooldown_cycles: int
    retryable: bool


_POLICIES = {
    "access_denied": FailurePolicy("access_denied", 16, 64, True),
    "rate_limited": FailurePolicy("rate_limited", 4, 32, True),
    "tls_error": FailurePolicy("tls_error", 16, 64, True),
    "network_error": FailurePolicy("network_error", 4, 32, True),
    "timeout": FailurePolicy("timeout", 2, 16, True),
    "server_error": FailurePolicy("server_error", 2, 16, True),
    "protocol_error": FailurePolicy("protocol_error", 4, 16, True),
    "parser_error": FailurePolicy("parser_error", 4, 32, True),
    "unknown_error": FailurePolicy("unknown_error", 2, 16, True),
}

_STATUS = re.compile(r"\b(?:status(?:=|\s)|http(?:\s+status)?\s*)(\d{3})\b", re.I)


def classify_error(error: str) -> FailurePolicy:
    """Classify source failures without relying on one exception implementation."""
    text = str(error or "")
    lower = text.lower()
    status = None
    match = _STATUS.search(lower)
    if match:
        try:
            status = int(match.group(1))
        except ValueError:
            status = None
    for code in (400, 401, 403, 404, 408, 429, 500, 502, 503, 504):
        if status is None and (f" {code}" in lower or f": {code}" in lower or f"{code}, message" in lower):
            status = code
            break

    if status in {401, 403} or "forbidden" in lower or "access denied" in lower:
        return _POLICIES["access_denied"]
    if status == 429 or "too many requests" in lower or "rate limit" in lower:
        return _POLICIES["rate_limited"]
    if status is not None and 500 <= status <= 599:
        return _POLICIES["server_error"]
    if "certificate" in lower or "ssl" in lower or "tls" in lower:
        return _POLICIES["tls_error"]
    if "timeout" in lower or "timed out" in lower:
        return _POLICIES["timeout"]
    if any(token in lower for token in ("cannot connect", "connection refused", "connection reset", "name or service not known", "dns", "clientconnectorerror")):
        return _POLICIES["network_error"]
    if any(token in lower for token in ("more than 8190 bytes", "header field", "badhttpmessage", "clientresponseerror")):
        return _POLICIES["protocol_error"]
    if any(token in lower for token in ("jsondecodeerror", "parse error", "parser", "invalid xml", "invalid json")):
        return _POLICIES["parser_error"]
    return _POLICIES["unknown_error"]


def cooldown_cycles(error: str, consecutive_failures: int) -> tuple[str, int]:
    policy = classify_error(error)
    exponent = max(0, min(4, int(consecutive_failures) - 1))
    cycles = min(policy.max_cooldown_cycles, policy.base_cooldown_cycles * (2**exponent))
    return policy.failure_class, max(1, int(cycles))
