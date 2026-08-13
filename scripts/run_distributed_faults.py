from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from lowpower_llm_cluster.content_store import ContentAddressedStore
from lowpower_llm_cluster.fault_injection import FaultInjectedClient, FaultPlan
from lowpower_llm_cluster.secure_distributed import SecureDistributedStore


async def run() -> None:
    with tempfile.TemporaryDirectory(prefix="lpllm-chaos-") as raw:
        root = Path(raw)
        artifacts = ContentAddressedStore(root / "artifacts")
        path = root / "tasks.sqlite3"
        async with SecureDistributedStore(path, artifacts) as store:
            # Keep leadership comfortably valid while exercising worker failures.
            leader = await store.acquire_leader("primary", lease_s=2.0)
            await store.register_worker("worker-a", capabilities=["json"], labels={}, resources={})
            await store.register_worker("worker-b", capabilities=["json"], labels={}, resources={})

            await store.submit_cycle([{"name": "fixture", "type": "json"}], cycle_id="worker-crash")
            first = await store.lease("worker-a", epoch=leader.epoch, lease_s=0.02, capabilities=["json"], labels={}, resources={})
            assert first
            await asyncio.sleep(0.03)  # worker disappears without heartbeat
            second = await store.lease("worker-b", epoch=leader.epoch, lease_s=1.0, capabilities=["json"], labels={}, resources={})
            assert second and second["task_id"] == first["task_id"] and second["attempt"] == 2
            assert await store.complete(second["task_id"], "worker-b", epoch=leader.epoch)

            await store.submit_cycle([{"name": "partition", "type": "json"}], cycle_id="network-partition")
            partitioned = await store.lease("worker-a", epoch=leader.epoch, lease_s=0.02, capabilities=["json"], labels={}, resources={})
            assert partitioned

            class StoreClient:
                async def heartbeat(self, task_id: str, **kwargs):
                    return await store.heartbeat(task_id, "worker-a", **kwargs)

            broken = FaultInjectedClient(StoreClient(), FaultPlan(failures={"heartbeat": {1}}))
            try:
                await broken.heartbeat(partitioned["task_id"], epoch=leader.epoch, lease_s=0.02, resources={})
            except ConnectionError:
                pass
            else:
                raise AssertionError("heartbeat network partition was not injected")
            await asyncio.sleep(0.03)
            reclaimed = await store.lease("worker-b", epoch=leader.epoch, lease_s=1.0, capabilities=["json"], labels={}, resources={})
            assert reclaimed and reclaimed["task_id"] == partitioned["task_id"] and reclaimed["attempt"] == 2
            assert await store.complete(reclaimed["task_id"], "worker-b", epoch=leader.epoch)

            # Shorten only the leadership lease under test, then promote the standby.
            leader = await store.acquire_leader("primary", lease_s=0.02)
            await asyncio.sleep(0.03)
            promoted = await store.acquire_leader("standby", lease_s=1.0)
            assert promoted.epoch > leader.epoch
            try:
                await store.lease("worker-a", epoch=leader.epoch, lease_s=1.0, capabilities=["json"], labels={}, resources={})
            except PermissionError:
                pass
            else:
                raise AssertionError("stale leader epoch accepted")

            backup = await store.backup(root / "checkpoint.sqlite3")
            assert backup.exists()

        async with SecureDistributedStore(path, ContentAddressedStore(root / "artifacts")) as reopened:
            crash_status = await reopened.cycle_status("worker-crash")
            partition_status = await reopened.cycle_status("network-partition")
            assert crash_status["done"] and partition_status["done"]

    print("Distributed fault suite passed: crash reclaim, heartbeat partition reclaim, stale-epoch fencing, backup, restart persistence.")


def main() -> int:
    argparse.ArgumentParser(description="Deterministic distributed-runtime fault injection smoke suite").parse_args()
    asyncio.run(run())
    return 0


if __name__ == "__main__": raise SystemExit(main())
