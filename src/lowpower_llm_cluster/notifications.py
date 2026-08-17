# src/lowpower_llm_cluster/notifications.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from email.message import EmailMessage
import os
import smtplib
from typing import Any, Iterable, Mapping, Protocol, Sequence

import httpx


_PRIORITY_ORDER = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


@dataclass(frozen=True, slots=True)
class NotificationDelivery:
    adapter: str
    ok: bool
    alert_fingerprint: str
    error: str | None = None


class NotificationAdapter(Protocol):
    name: str

    async def send(self, alert: Mapping[str, Any]) -> None: ...


def alert_priority(alert: Mapping[str, Any]) -> str:
    explicit = str(alert.get("priority") or "").upper()
    if explicit in _PRIORITY_ORDER:
        return explicit
    severity = str(alert.get("severity") or "").casefold()
    return {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4"}.get(severity, "P4")


def format_alert(alert: Mapping[str, Any]) -> str:
    subject = alert.get("title") or alert.get("part_id") or alert.get("source_id") or "market item"
    reason = str(alert.get("reason") or alert.get("type") or "market change")
    priority = alert_priority(alert)
    price = ""
    if alert.get("new_price") is not None:
        price = f" — {alert.get('new_price')} {alert.get('currency') or ''}".rstrip()
    url = alert.get("url") or alert.get("source_url")
    suffix = f" — {url}" if url else ""
    return f"[{priority}] {subject}: {reason}{price}{suffix}"


class WebhookNotificationAdapter:
    """Generic JSON webhook delivery using non-blocking HTTP I/O."""

    def __init__(
        self,
        url: str,
        *,
        name: str = "webhook",
        timeout_s: float = 10.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not url.startswith("https://"):
            raise ValueError("notification webhooks must use HTTPS")
        self.url = url
        self.name = name
        self.timeout_s = timeout_s
        self.headers = dict(headers or {})

    def payload(self, alert: Mapping[str, Any]) -> dict[str, Any]:
        return {"text": format_alert(alert), "priority": alert_priority(alert), "alert": dict(alert)}

    async def send(self, alert: Mapping[str, Any]) -> None:
        async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=False) as client:
            response = await client.post(self.url, json=self.payload(alert), headers=self.headers)
            response.raise_for_status()


class ChatWebhookNotificationAdapter(WebhookNotificationAdapter):
    """Text-first webhook suitable for chat endpoints that accept a `text` JSON field."""

    def __init__(self, url: str, *, name: str = "chat", timeout_s: float = 10.0, headers: Mapping[str, str] | None = None) -> None:
        super().__init__(url, name=name, timeout_s=timeout_s, headers=headers)

    def payload(self, alert: Mapping[str, Any]) -> dict[str, Any]:
        return {"text": format_alert(alert)}


def _smtp_send(
    *,
    host: str,
    port: int,
    use_ssl: bool,
    starttls: bool,
    username: str | None,
    password: str | None,
    sender: str,
    recipients: Sequence[str],
    message: EmailMessage,
    timeout_s: float,
) -> None:
    smtp_type = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_type(host=host, port=port, timeout=timeout_s) as smtp:
        if starttls and not use_ssl:
            smtp.starttls()
        if username:
            smtp.login(username, password or "")
        smtp.send_message(message, from_addr=sender, to_addrs=list(recipients))


class EmailNotificationAdapter:
    """SMTP delivery isolated in a worker thread so synchronous SMTP cannot block the event loop."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        recipients: Sequence[str],
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool = False,
        starttls: bool = True,
        timeout_s: float = 15.0,
        name: str = "email",
    ) -> None:
        if not host or port <= 0 or not sender or not recipients:
            raise ValueError("SMTP host, positive port, sender and at least one recipient are required")
        if use_ssl and starttls:
            raise ValueError("choose SMTP SSL or STARTTLS, not both")
        self.host = host
        self.port = port
        self.sender = sender
        self.recipients = tuple(recipients)
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.starttls = starttls
        self.timeout_s = timeout_s
        self.name = name

    async def send(self, alert: Mapping[str, Any]) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message["Subject"] = f"LowPowerLLMCluster {alert_priority(alert)}: {alert.get('type', 'market alert')}"
        message.set_content(format_alert(alert))
        await asyncio.to_thread(
            _smtp_send,
            host=self.host,
            port=self.port,
            use_ssl=self.use_ssl,
            starttls=self.starttls,
            username=self.username,
            password=self.password,
            sender=self.sender,
            recipients=self.recipients,
            message=message,
            timeout_s=self.timeout_s,
        )


async def deliver_alerts(
    alerts: Iterable[Mapping[str, Any]],
    adapters: Sequence[NotificationAdapter],
    *,
    maximum_priority: str = "P4",
) -> list[NotificationDelivery]:
    """Fan alert evidence out concurrently without allowing one adapter failure to stop the others."""
    maximum_priority = maximum_priority.upper()
    if maximum_priority not in _PRIORITY_ORDER:
        raise ValueError("maximum_priority must be one of P1, P2, P3, P4")
    selected = [dict(alert) for alert in alerts if _PRIORITY_ORDER[alert_priority(alert)] <= _PRIORITY_ORDER[maximum_priority]]
    jobs: list[tuple[NotificationAdapter, Mapping[str, Any]]] = [
        (adapter, alert) for alert in selected for adapter in adapters
    ]
    if not jobs:
        return []
    results = await asyncio.gather(*(adapter.send(alert) for adapter, alert in jobs), return_exceptions=True)
    deliveries: list[NotificationDelivery] = []
    for (adapter, alert), result in zip(jobs, results, strict=True):
        fingerprint = str(alert.get("fingerprint") or alert.get("source_id") or alert.get("part_id") or alert.get("type") or "unknown")
        if isinstance(result, BaseException):
            deliveries.append(NotificationDelivery(adapter=adapter.name, ok=False, alert_fingerprint=fingerprint, error=f"{type(result).__name__}: {result}"))
        else:
            deliveries.append(NotificationDelivery(adapter=adapter.name, ok=True, alert_fingerprint=fingerprint))
    return deliveries


def adapters_from_config(config: Mapping[str, Any], *, environ: Mapping[str, str] | None = None) -> list[NotificationAdapter]:
    """Build adapters while keeping credentials and webhook URLs in environment variables."""
    env = environ or os.environ
    adapters: list[NotificationAdapter] = []
    for row in config.get("adapters", []):
        if not row.get("enabled", True):
            continue
        kind = str(row.get("type") or "").casefold()
        name = str(row.get("name") or kind or "notification")
        if kind in {"webhook", "chat"}:
            url_env = str(row.get("url_env") or "")
            url = env.get(url_env, "") if url_env else ""
            if not url:
                continue
            cls = ChatWebhookNotificationAdapter if kind == "chat" else WebhookNotificationAdapter
            adapters.append(cls(url, name=name, timeout_s=float(row.get("timeout_s", 10.0))))
            continue
        if kind == "email":
            password_env = str(row.get("password_env") or "")
            username_env = str(row.get("username_env") or "")
            recipients = row.get("recipients") or []
            adapters.append(
                EmailNotificationAdapter(
                    host=str(row["host"]),
                    port=int(row.get("port", 587)),
                    sender=str(row["sender"]),
                    recipients=[str(value) for value in recipients],
                    username=env.get(username_env) if username_env else None,
                    password=env.get(password_env) if password_env else None,
                    use_ssl=bool(row.get("use_ssl", False)),
                    starttls=bool(row.get("starttls", not row.get("use_ssl", False))),
                    timeout_s=float(row.get("timeout_s", 15.0)),
                    name=name,
                )
            )
            continue
        raise ValueError(f"unsupported notification adapter type: {kind!r}")
    return adapters
