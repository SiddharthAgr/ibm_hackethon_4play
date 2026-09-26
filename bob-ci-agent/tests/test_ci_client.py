"""
tests/test_ci_client.py — pytest tests for python.ci_client.run_pipeline.

All tests are deterministic and require no network access.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from python.ci_client import (
    InvalidPipelineReferenceError,
    InvalidPipelineResultError,
    PipelineFixtureNotFoundError,
    _FIXTURES_DIR,
    run_pipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_temp_fixture(data: dict[str, Any], ref: str = "run-tmp") -> str:
    """Write *data* as JSON to a temp fixture in the real fixtures dir.

    Returns the ref name so it can be passed to run_pipeline.
    The caller is responsible for deleting the file (use tmp_fixture fixture).
    """
    path = _FIXTURES_DIR / f"{ref}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return ref


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=False)
def tmp_fixture(request):
    """Creates a temporary fixture file and removes it after the test."""
    data, ref = request.param
    path = _FIXTURES_DIR / f"{ref}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    yield ref
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# 1. run_pipeline("run-42") returns a dictionary
# ---------------------------------------------------------------------------


def test_run_pipeline_returns_dict():
    result = run_pipeline("run-42")
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 2. Returned run_id is "run-42"
# ---------------------------------------------------------------------------


def test_run_pipeline_run_id():
    result = run_pipeline("run-42")
    assert result["run_id"] == "run-42"


# ---------------------------------------------------------------------------
# 3. Returned status is "failed"
# ---------------------------------------------------------------------------


def test_run_pipeline_status_failed():
    result = run_pipeline("run-42")
    assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# 4. Failures list is present
# ---------------------------------------------------------------------------


def test_run_pipeline_failures_present():
    result = run_pipeline("run-42")
    assert "failures" in result
    assert isinstance(result["failures"], list)
    assert len(result["failures"]) > 0


# ---------------------------------------------------------------------------
# 5. First failure contains required fields: test, error, file
# ---------------------------------------------------------------------------


def test_run_pipeline_failure_has_required_fields():
    result = run_pipeline("run-42")
    failure = result["failures"][0]
    assert "test" in failure
    assert "error" in failure
    assert "file" in failure


# ---------------------------------------------------------------------------
# 6. Empty ref is rejected
# ---------------------------------------------------------------------------


def test_empty_ref_raises():
    with pytest.raises(InvalidPipelineReferenceError):
        run_pipeline("")


# ---------------------------------------------------------------------------
# 7. Whitespace-only ref is rejected
# ---------------------------------------------------------------------------


def test_whitespace_ref_raises():
    with pytest.raises(InvalidPipelineReferenceError):
        run_pipeline("   ")


# ---------------------------------------------------------------------------
# 8. Unknown fixture / run ID produces PipelineFixtureNotFoundError
# ---------------------------------------------------------------------------


def test_unknown_ref_raises_fixture_not_found():
    with pytest.raises(PipelineFixtureNotFoundError):
        run_pipeline("run-does-not-exist-99999")


# ---------------------------------------------------------------------------
# 9. Malformed fixture (missing required field) raises InvalidPipelineResultError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tmp_fixture",
    [
        (
            {
                # missing "ref", "failures"
                "run_id": "run-bad",
                "status": "failed",
            },
            "run-bad-missing-fields",
        )
    ],
    indirect=True,
)
def test_malformed_fixture_missing_fields(tmp_fixture):
    with pytest.raises(InvalidPipelineResultError):
        run_pipeline(tmp_fixture)


@pytest.mark.parametrize(
    "tmp_fixture",
    [
        (
            {
                "run_id": "run-bad",
                "ref": "feat/bad",
                "status": "unknown-status",  # unsupported status
                "failures": [],
            },
            "run-bad-status",
        )
    ],
    indirect=True,
)
def test_malformed_fixture_bad_status(tmp_fixture):
    with pytest.raises(InvalidPipelineResultError):
        run_pipeline(tmp_fixture)


@pytest.mark.parametrize(
    "tmp_fixture",
    [
        (
            {
                "run_id": "run-bad",
                "ref": "feat/bad",
                "status": "failed",
                "failures": [
                    {
                        "test": "test_something",
                        # missing "error" and "file"
                    }
                ],
            },
            "run-bad-failure-fields",
        )
    ],
    indirect=True,
)
def test_malformed_fixture_failure_missing_fields(tmp_fixture):
    with pytest.raises(InvalidPipelineResultError):
        run_pipeline(tmp_fixture)


# ---------------------------------------------------------------------------
# 10. No live network connection required for the demo fixture
# ---------------------------------------------------------------------------


def test_no_network_required():
    """run_pipeline must work without any network calls.

    We verify this by monkey-patching socket to prevent connections and
    confirming the function still returns the expected result.
    """
    import socket

    original_connect = socket.socket.connect

    def refuse_connect(self, *args, **kwargs):
        raise OSError("Network access is not allowed in this test")

    socket.socket.connect = refuse_connect
    try:
        result = run_pipeline("run-42")
        assert result["run_id"] == "run-42"
    finally:
        socket.socket.connect = original_connect


# ---------------------------------------------------------------------------
# 11. Returned structure is JSON-serializable
# ---------------------------------------------------------------------------


def test_result_is_json_serializable():
    result = run_pipeline("run-42")
    serialized = json.dumps(result)
    assert isinstance(serialized, str)
    # Round-trip
    parsed = json.loads(serialized)
    assert parsed["run_id"] == "run-42"


# ---------------------------------------------------------------------------
# 12. Additional fixture fields are preserved safely
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tmp_fixture",
    [
        (
            {
                "run_id": "run-extra",
                "ref": "feat/extra",
                "status": "passed",
                "failures": [],
                "triggered_at": "2025-01-26T10:00:00Z",
                "branch": "feat/extra",
                "commit_sha": "abc123",
                "custom_metadata": {"team": "alpha", "priority": 1},
            },
            "run-extra",
        )
    ],
    indirect=True,
)
def test_extra_fields_preserved(tmp_fixture):
    result = run_pipeline(tmp_fixture)
    assert result["commit_sha"] == "abc123"
    assert result["custom_metadata"] == {"team": "alpha", "priority": 1}


# ---------------------------------------------------------------------------
# Non-string ref raises InvalidPipelineReferenceError
# ---------------------------------------------------------------------------


def test_non_string_ref_raises():
    with pytest.raises(InvalidPipelineReferenceError):
        run_pipeline(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Whitespace around valid ref is stripped correctly
# ---------------------------------------------------------------------------


def test_whitespace_stripped_from_valid_ref():
    result = run_pipeline("  run-42  ")
    assert result["run_id"] == "run-42"
