"""
ci_client.py — Python CI pipeline client for the IBM Bob CI/CD Intelligence Agent.

Public API
----------
    run_pipeline(ref: str) -> dict

The function accepts a pipeline reference / run ID, loads the corresponding
fixture from ``demo/fixtures/<ref>.json``, validates and normalizes the result,
and returns a structured dictionary that matches the project failure schema.

For the hackathon MVP the fixture is the primary (and only) data source.
Live CI provider support can be layered on later via the optional
``CI_API_TOKEN`` environment variable path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Root of the bob-ci-agent package: the directory that contains python/
_PACKAGE_ROOT: Path = Path(__file__).resolve().parent.parent
_FIXTURES_DIR: Path = _PACKAGE_ROOT / "demo" / "fixtures"

# ---------------------------------------------------------------------------
# Supported statuses
# ---------------------------------------------------------------------------

SUPPORTED_STATUSES: frozenset[str] = frozenset({"passed", "failed"})

# Required top-level keys in every pipeline result
_REQUIRED_RESULT_KEYS: tuple[str, ...] = ("run_id", "ref", "status", "failures")

# Required keys inside each failure object
_REQUIRED_FAILURE_KEYS: tuple[str, ...] = ("test", "error", "file")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class InvalidPipelineReferenceError(ValueError):
    """Raised when the supplied ``ref`` is not a valid pipeline reference."""


class PipelineFixtureNotFoundError(FileNotFoundError):
    """Raised when no fixture file exists for the requested ``ref``."""


class InvalidPipelineResultError(ValueError):
    """Raised when a fixture (or live CI response) does not match the schema."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_ref(ref: str) -> str:
    """Return the stripped ref if valid, otherwise raise InvalidPipelineReferenceError.

    Rules:
    - Must be a non-empty string after stripping whitespace.
    - Path separators are not allowed (prevents directory traversal).
    """
    if not isinstance(ref, str):
        raise InvalidPipelineReferenceError(
            f"Pipeline reference must be a string, got {type(ref).__name__!r}."
        )
    stripped = ref.strip()
    if not stripped:
        raise InvalidPipelineReferenceError(
            "Pipeline reference must not be empty or whitespace-only."
        )
    if "/" in stripped or "\\" in stripped:
        raise InvalidPipelineReferenceError(
            f"Pipeline reference {stripped!r} contains path separators, which are not allowed."
        )
    return stripped


def _load_fixture(ref: str) -> dict[str, Any]:
    """Load and JSON-parse the fixture file for *ref*.

    Raises
    ------
    PipelineFixtureNotFoundError
        If the fixture file does not exist.
    InvalidPipelineResultError
        If the file exists but is not valid JSON.
    """
    fixture_path: Path = _FIXTURES_DIR / f"{ref}.json"
    if not fixture_path.exists():
        raise PipelineFixtureNotFoundError(
            f"No fixture found for pipeline reference {ref!r}. "
            f"Expected file: {fixture_path}"
        )
    try:
        with fixture_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise InvalidPipelineResultError(
            f"Fixture for {ref!r} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise InvalidPipelineResultError(
            f"Fixture for {ref!r} must be a JSON object, got {type(data).__name__!r}."
        )
    return data


def _validate_result(data: dict[str, Any], ref: str) -> None:
    """Validate that *data* conforms to the pipeline result schema.

    Raises
    ------
    InvalidPipelineResultError
        On any schema violation.
    """
    # Required top-level keys
    for key in _REQUIRED_RESULT_KEYS:
        if key not in data:
            raise InvalidPipelineResultError(
                f"Pipeline result for {ref!r} is missing required field {key!r}."
            )

    # Status must be supported
    status = data["status"]
    if status not in SUPPORTED_STATUSES:
        raise InvalidPipelineResultError(
            f"Pipeline result for {ref!r} has unsupported status {status!r}. "
            f"Supported values: {sorted(SUPPORTED_STATUSES)}"
        )

    # failures must be a list
    failures = data["failures"]
    if not isinstance(failures, list):
        raise InvalidPipelineResultError(
            f"Pipeline result for {ref!r}: 'failures' must be a list, "
            f"got {type(failures).__name__!r}."
        )

    # Validate each failure object
    for idx, failure in enumerate(failures):
        if not isinstance(failure, dict):
            raise InvalidPipelineResultError(
                f"Pipeline result for {ref!r}: failure at index {idx} must be "
                f"an object, got {type(failure).__name__!r}."
            )
        for key in _REQUIRED_FAILURE_KEYS:
            if key not in failure:
                raise InvalidPipelineResultError(
                    f"Pipeline result for {ref!r}: failure at index {idx} is "
                    f"missing required field {key!r}."
                )
        # Optional numeric fields — validate type when present
        for num_key in ("line", "duration_ms"):
            if num_key in failure and not isinstance(failure[num_key], (int, float)):
                raise InvalidPipelineResultError(
                    f"Pipeline result for {ref!r}: failure at index {idx} field "
                    f"{num_key!r} must be numeric, got {type(failure[num_key]).__name__!r}."
                )


def _normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized copy of *data*.

    The core schema fields are promoted to the top level; any additional
    metadata from the fixture is preserved unchanged.
    """
    normalized: dict[str, Any] = dict(data)  # shallow copy; preserves extra fields
    return normalized


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_pipeline(ref: str) -> dict[str, Any]:
    """Load, validate, and return the CI pipeline result for *ref*.

    Parameters
    ----------
    ref:
        Pipeline run identifier (e.g. ``"run-42"``).  Leading/trailing
        whitespace is stripped automatically.

    Returns
    -------
    dict
        Normalized pipeline result matching the project failure schema::

            {
                "run_id":       str,
                "ref":          str,
                "status":       "passed" | "failed",
                "failures":     list[dict],
                "triggered_at": str,        # when present in the fixture
                ...                         # any extra fixture fields are preserved
            }

    Raises
    ------
    InvalidPipelineReferenceError
        If *ref* is empty, whitespace-only, or otherwise invalid.
    PipelineFixtureNotFoundError
        If no fixture exists for the given *ref* and live CI is not configured.
    InvalidPipelineResultError
        If the fixture (or live CI response) does not match the schema.

    Example
    -------
    >>> from python.ci_client import run_pipeline
    >>> result = run_pipeline("run-42")
    >>> result["status"]
    'failed'
    """
    clean_ref: str = _validate_ref(ref)

    # ------------------------------------------------------------------
    # Live CI path (optional, environment-variable gated)
    # ------------------------------------------------------------------
    # Placeholder for a future GitHubActionsProvider.  When CI_API_TOKEN
    # is set a concrete provider can be injected here.  For the MVP this
    # branch is intentionally unreachable so the fixture path is always used.
    ci_token: str | None = os.environ.get("CI_API_TOKEN")
    if ci_token:
        # Future: call _get_live_ci_result(clean_ref, ci_token)
        # For now, fall through to the fixture path.
        pass

    # ------------------------------------------------------------------
    # Fixture path (primary path for MVP)
    # ------------------------------------------------------------------
    data: dict[str, Any] = _load_fixture(clean_ref)
    _validate_result(data, clean_ref)
    return _normalize_result(data)
