from lowpower_llm_cluster.firmware_history import bios_history_for_revision, normalize_revision_scoped_bios_history


def test_revision_scoped_payload_is_preserved():
    payload={"revisions":[{"board_revision":"1.0","bios":[{"version":"F12","release_date":"2024-01-01","url":"/f12.zip"},{"version":"F14","release_date":"2025-01-01","url":"/f14.zip"}]},{"board_revision":"1.2","bios":[{"version":"F14","release_date":"2025-02-01","url":"/rev12/f14.zip"}]}]}
    rows=normalize_revision_scoped_bios_history(payload,source_url="https://www.gigabyte.com/api/bios")
    rev12=bios_history_for_revision(rows,"Rev. 1.2")
    assert rev12["status"] == "revision_scoped"
    assert len(rev12["rows"]) == 1
    assert rev12["rows"][0]["version"] == "F14"
    assert rev12["rows"][0]["board_revisions"] == ["1.2"]


def test_unscoped_history_is_not_silently_assigned_to_revision():
    rows=[{"version":"F14","release_date":"2025-01-01"}]
    result=bios_history_for_revision(rows,"1.2")
    assert result["status"] == "no_revision_scoped_history"
    assert result["rows"] == []
    assert result["unscoped_rows_ignored"] == 1
