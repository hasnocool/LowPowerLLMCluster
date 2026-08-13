from __future__ import annotations

import pytest

from lowpower_llm_cluster.market_cli import _performance_records


def test_performance_records_accepts_top_level_list() -> None:
    records = [{"part_id": "example"}]
    assert _performance_records(records) is records


def test_performance_records_accepts_object_records_array() -> None:
    records = [{"part_id": "example"}]
    assert _performance_records({"records": records}) is records


def test_performance_records_rejects_non_array_records() -> None:
    with pytest.raises(ValueError, match="records.*array"):
        _performance_records({"records": {"part_id": "example"}})


def test_performance_records_rejects_scalar_payload() -> None:
    with pytest.raises(ValueError, match="object or array"):
        _performance_records("not-a-record-set")
