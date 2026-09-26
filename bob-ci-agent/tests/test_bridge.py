"""
tests/test_bridge.py — focused tests for python.bridge (the MCP process bridge).

All four required scenarios are covered:
1. Valid ref  → exit 0, stdout contains valid JSON.
2. Invalid/unknown ref → exit non-zero, stderr contains an error, stdout clean.
3. stdout is not polluted with debug/logging text.
4. Existing python.ci_client tests are unaffected (they live in test_ci_client.py
   and do not interact with this file; this module adds tests only).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_bridge(*args: str) -> subprocess.CompletedProcess:
    """Invoke the bridge as ``python -m python.bridge <args>`` in a subprocess.

    The subprocess inherits the current Python interpreter and the
    bob-ci-agent working directory so that the ``python`` package is on the
    path (matching how pytest is run).
    """
    bob_ci_agent = Path(__file__).resolve().parent.parent  # bob-ci-agent/
    return subprocess.run(
        [sys.executable, "-m", "python.bridge", *args],
        capture_output=True,
        text=True,
        cwd=str(bob_ci_agent),
    )


# ---------------------------------------------------------------------------
# 1. Valid ref → exit 0, stdout is valid JSON
# ---------------------------------------------------------------------------


def test_valid_ref_exits_zero():
    """A known fixture ref must produce exit code 0."""
    proc = _run_bridge("run-42")
    assert proc.returncode == 0, f"Expected exit 0, got {proc.returncode}. stderr={proc.stderr!r}"


def test_valid_ref_stdout_is_valid_json():
    """stdout must be exactly one line of valid JSON."""
    proc = _run_bridge("run-42")
    assert proc.returncode == 0
    stdout = proc.stdout.strip()
    assert stdout, "stdout must not be empty on success"
    parsed = json.loads(stdout)  # raises if not valid JSON
    assert isinstance(parsed, dict)


def test_valid_ref_json_contains_expected_fields():
    """The JSON result must contain the standard pipeline fields."""
    proc = _run_bridge("run-42")
    assert proc.returncode == 0
    parsed = json.loads(proc.stdout.strip())
    assert parsed["run_id"] == "run-42"
    assert parsed["status"] == "failed"
    assert "failures" in parsed
    assert isinstance(parsed["failures"], list)


# ---------------------------------------------------------------------------
# 2. Invalid/unknown ref → non-zero exit, error on stderr, stdout clean
# ---------------------------------------------------------------------------


def test_unknown_ref_exits_nonzero():
    """An unknown ref must produce a non-zero exit code."""
    proc = _run_bridge("run-does-not-exist-99999")
    assert proc.returncode != 0, "Expected non-zero exit for unknown ref"


def test_unknown_ref_stderr_contains_error():
    """stderr must carry a human-readable error for an unknown ref."""
    proc = _run_bridge("run-does-not-exist-99999")
    assert proc.returncode != 0
    assert proc.stderr.strip(), "stderr must not be empty on failure"


def test_unknown_ref_stdout_is_empty():
    """stdout must be empty when the ref is not found."""
    proc = _run_bridge("run-does-not-exist-99999")
    assert proc.returncode != 0
    assert proc.stdout.strip() == "", f"stdout should be empty on failure, got {proc.stdout!r}"


def test_invalid_ref_empty_string_exits_nonzero():
    """An empty string ref must produce a non-zero exit code."""
    proc = _run_bridge("")
    assert proc.returncode != 0


def test_invalid_ref_path_separator_exits_nonzero():
    """A ref with a path separator must produce a non-zero exit code."""
    proc = _run_bridge("run/42")
    assert proc.returncode != 0


def test_no_args_exits_nonzero():
    """Invoking the bridge with no arguments must produce a non-zero exit code."""
    proc = _run_bridge()
    assert proc.returncode != 0
    assert proc.stderr.strip(), "Usage error must appear on stderr"


def test_too_many_args_exits_nonzero():
    """Invoking the bridge with extra arguments must produce a non-zero exit code."""
    proc = _run_bridge("run-42", "extra-arg")
    assert proc.returncode != 0


# ---------------------------------------------------------------------------
# 3. stdout is not polluted with debug/logging text on success
# ---------------------------------------------------------------------------


def test_stdout_is_only_json_on_success():
    """stdout must contain only the JSON line — no log lines, warnings, etc."""
    proc = _run_bridge("run-42")
    assert proc.returncode == 0
    stdout = proc.stdout.strip()
    # Must parse as JSON (would already fail above, but be explicit)
    parsed = json.loads(stdout)
    # stdout must be a single JSON object (no extra lines)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, f"Expected exactly 1 JSON line, got {len(lines)}: {lines}"
    assert isinstance(parsed, dict)


def test_stderr_is_empty_on_success():
    """No diagnostic text must leak to stderr on a successful run."""
    proc = _run_bridge("run-42")
    assert proc.returncode == 0
    assert proc.stderr.strip() == "", f"stderr should be empty on success, got {proc.stderr!r}"
