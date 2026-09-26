"""
coverage_reader.py — Python coverage report reader for the IBM Bob CI/CD Intelligence Agent.

Public API
----------
    get_coverage_report(ref: str) -> dict

The function accepts a branch/commit reference, loads the corresponding
coverage report from ``reports/coverage-<ref>.json``, validates its
structure, and returns a structured dictionary that matches the project
``get_coverage_report`` MCP tool output contract.

Report location convention::

    reports/coverage-<ref>.json

where ``<ref>`` is the raw ref as supplied by the caller (whitespace
stripped; path separators forbidden).

Example: ``get_coverage_report("feat-auth")`` reads
``reports/coverage-feat-auth.json``.

For the hackathon MVP the file-based fixture is the primary (and only)
data source.  No network calls are made.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Root of the bob-ci-agent package: the directory that contains python/
_PACKAGE_ROOT: Path = Path(__file__).resolve().parent.parent
_REPORTS_DIR: Path = _PACKAGE_ROOT / "reports"

# ---------------------------------------------------------------------------
# Required schema fields
# ---------------------------------------------------------------------------

# Required top-level keys in every coverage report
_REQUIRED_REPORT_KEYS: tuple[str, ...] = ("ref", "total_coverage_pct", "files")

# Required keys inside each file entry
_REQUIRED_FILE_KEYS: tuple[str, ...] = ("path", "coverage_pct", "uncovered_lines")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class InvalidCoverageRefError(ValueError):
    """Raised when the supplied ``ref`` is not a valid coverage reference."""


class CoverageReportNotFoundError(FileNotFoundError):
    """Raised when no coverage report file exists for the requested ``ref``."""


class InvalidCoverageReportError(ValueError):
    """Raised when a coverage report file does not match the expected schema."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_ref(ref: str) -> str:
    """Return the stripped ref if valid, otherwise raise InvalidCoverageRefError.

    Rules:
    - Must be a non-empty string after stripping whitespace.
    - Path separators are not allowed (prevents directory traversal).
    """
    if not isinstance(ref, str):
        raise InvalidCoverageRefError(
            f"Coverage reference must be a string, got {type(ref).__name__!r}."
        )
    stripped = ref.strip()
    if not stripped:
        raise InvalidCoverageRefError(
            "Coverage reference must not be empty or whitespace-only."
        )
    if "/" in stripped or "\\" in stripped:
        raise InvalidCoverageRefError(
            f"Coverage reference {stripped!r} contains path separators, which are not allowed."
        )
    return stripped


def _load_report(ref: str) -> dict[str, Any]:
    """Load and JSON-parse the coverage report file for *ref*.

    Raises
    ------
    CoverageReportNotFoundError
        If the report file does not exist.
    InvalidCoverageReportError
        If the file exists but is not valid JSON, or is not a JSON object.
    """
    report_path: Path = _REPORTS_DIR / f"coverage-{ref}.json"
    if not report_path.exists():
        raise CoverageReportNotFoundError(
            f"No coverage report found for ref {ref!r}. "
            f"Expected file: {report_path}"
        )
    try:
        with report_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise InvalidCoverageReportError(
            f"Coverage report for {ref!r} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise InvalidCoverageReportError(
            f"Coverage report for {ref!r} must be a JSON object, "
            f"got {type(data).__name__!r}."
        )
    return data


def _validate_report(data: dict[str, Any], ref: str) -> None:
    """Validate that *data* conforms to the coverage report schema.

    Raises
    ------
    InvalidCoverageReportError
        On any schema violation.
    """
    # Required top-level keys
    for key in _REQUIRED_REPORT_KEYS:
        if key not in data:
            raise InvalidCoverageReportError(
                f"Coverage report for {ref!r} is missing required field {key!r}."
            )

    # total_coverage_pct must be numeric
    total = data["total_coverage_pct"]
    if not isinstance(total, (int, float)):
        raise InvalidCoverageReportError(
            f"Coverage report for {ref!r}: 'total_coverage_pct' must be numeric, "
            f"got {type(total).__name__!r}."
        )

    # files must be a list
    files = data["files"]
    if not isinstance(files, list):
        raise InvalidCoverageReportError(
            f"Coverage report for {ref!r}: 'files' must be a list, "
            f"got {type(files).__name__!r}."
        )

    # Validate each file entry
    for idx, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise InvalidCoverageReportError(
                f"Coverage report for {ref!r}: file entry at index {idx} must be "
                f"an object, got {type(entry).__name__!r}."
            )
        for key in _REQUIRED_FILE_KEYS:
            if key not in entry:
                raise InvalidCoverageReportError(
                    f"Coverage report for {ref!r}: file entry at index {idx} is "
                    f"missing required field {key!r}."
                )
        # coverage_pct must be numeric
        cov = entry["coverage_pct"]
        if not isinstance(cov, (int, float)):
            raise InvalidCoverageReportError(
                f"Coverage report for {ref!r}: file entry at index {idx} field "
                f"'coverage_pct' must be numeric, got {type(cov).__name__!r}."
            )
        # uncovered_lines must be a list
        lines = entry["uncovered_lines"]
        if not isinstance(lines, list):
            raise InvalidCoverageReportError(
                f"Coverage report for {ref!r}: file entry at index {idx} field "
                f"'uncovered_lines' must be a list, got {type(lines).__name__!r}."
            )


def _build_output(data: dict[str, Any], ref: str) -> dict[str, Any]:
    """Return only the required output fields from *data*.

    Extracts exactly the fields required by the ``get_coverage_report``
    MCP tool contract, discarding any additional fixture fields.
    """
    return {
        "ref": ref,
        "total_coverage_pct": data["total_coverage_pct"],
        "files": [
            {
                "path": entry["path"],
                "coverage_pct": entry["coverage_pct"],
                "uncovered_lines": list(entry["uncovered_lines"]),
            }
            for entry in data["files"]
        ],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_coverage_report(ref: str) -> dict[str, Any]:
    """Load, validate, and return the coverage report for *ref*.

    Parameters
    ----------
    ref:
        Branch or commit reference, e.g. ``"feat-auth"``.  Leading/trailing
        whitespace is stripped automatically.  The report is read from
        ``reports/coverage-<ref>.json`` relative to the package root.

    Returns
    -------
    dict
        Structured coverage report matching the ``get_coverage_report``
        MCP tool output contract::

            {
                "ref":               str,
                "total_coverage_pct": float,
                "files": [
                    {
                        "path":             str,
                        "coverage_pct":     float,
                        "uncovered_lines":  list[int],
                    },
                    ...
                ]
            }

    Raises
    ------
    InvalidCoverageRefError
        If *ref* is empty, whitespace-only, non-string, or contains path
        separators.
    CoverageReportNotFoundError
        If no report file exists for the given *ref*.
    InvalidCoverageReportError
        If the report file is not valid JSON or fails schema validation.

    Example
    -------
    >>> from python.coverage_reader import get_coverage_report
    >>> report = get_coverage_report("feat-auth")
    >>> report["total_coverage_pct"]
    68.0
    >>> report["ref"]
    'feat-auth'
    """
    clean_ref: str = _validate_ref(ref)
    data: dict[str, Any] = _load_report(clean_ref)
    _validate_report(data, clean_ref)
    return _build_output(data, clean_ref)
