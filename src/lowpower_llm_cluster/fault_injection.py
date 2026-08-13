from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FaultPlan:
    """Deterministic call-count fault injector used by distributed-runtime tests."""

    failures: dict[str, set[int]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def hit(self, operation: str) -> None:
        count = self.counts.get(operation, 0) + 1
        self.counts[operation] = count
        if count in self.failures.get(operation, set()):
            raise ConnectionError(f"injected {operation} failure #{count}")


class FaultInjectedClient:
    def __init__(self, client: Any, plan: FaultPlan) -> None:
        self.client, self.plan = client, plan

    def __getattr__(self, name: str) -> Any:
        value = getattr(self.client, name)
        if not callable(value) or name.startswith("_"):
            return value

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            self.plan.hit(name)
            return await value(*args, **kwargs)
        return wrapped
