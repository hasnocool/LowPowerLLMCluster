from __future__ import annotations

from lowpower_llm_cluster.resource_runtime import SchedulingRequirements


def test_hard_resource_requirements_reject_unknown_measurements() -> None:
    requirements = SchedulingRequirements.from_source(
        {
            "worker_requirements": {
                "capabilities": ["json"],
                "max_cpu_load": 0.8,
                "max_thermal_c": 80,
                "min_available_memory_mb": 1024,
                "min_power_budget_w": 25,
            }
        }
    )
    resources = {
        "cpu_load_fraction": 0.2,
        "thermal_c": 60,
        "available_memory_mb": 2048,
        "power_budget_w": 30,
    }
    matched, _, _ = requirements.matches(
        worker_id="worker-a",
        capabilities={"json"},
        labels={},
        resources=resources,
        allow_steal=True,
    )
    assert matched

    for key in resources:
        unknown = dict(resources)
        unknown[key] = None
        matched, _, reason = requirements.matches(
            worker_id="worker-a",
            capabilities={"json"},
            labels={},
            resources=unknown,
            allow_steal=True,
        )
        assert not matched
        assert "unavailable" in reason or "unknown" in reason


def test_unconstrained_missing_resource_measurements_remain_eligible() -> None:
    requirements = SchedulingRequirements.from_source(
        {"worker_requirements": {"capabilities": ["json"]}}
    )
    matched, _, reason = requirements.matches(
        worker_id="worker-a",
        capabilities={"json"},
        labels={},
        resources={},
        allow_steal=True,
    )
    assert matched
    assert reason == "matched"
