"""
tests/test_coverage_reader.py — pytest tests for python.coverage_reader.get_coverage_report.

All tests are deterministic and require no network access.

Coverage:
  1.  Successful read of the seeded coverage-feat-auth report.
  2.  Correct total coverage value (68%).
  3.  Correct file-level fields.
  4.  Correct uncovered-line data.
  5.  Missing report file.
  6.  Malformed JSON.
  7.  Missing required top-level field.
  8.  Malformed file entry / missing required file-level field.
  9.  Numeric coverage values are preserved.
  10. Returned ref matches the requested ref.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from python.coverage_reader import (
    CoverageReportNotFoundError,
    InvalidCoverageRefError,
    InvalidCoverageReportError,
    _REPORTS_DIR,
    get_coverage_report,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# Ref used to exercise the committed seeded demo report.
# The file on disk is reports/coverage-feat-auth.json
_SEEDED_REF = "feat-auth"
_SEEDED_TOTAL_COVERAGE = 68.0


def _write_temp_report(data: Any, ref: str) -> Path:
    """Write *data* as JSON to a temporary coverage report in the real reports dir.

    Returns the path so the caller can clean it up.
    """
    path = _REPORTS_DIR / f"coverage-{ref}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture()
def tmp_coverage_report(request):
    """Parametrize with (data, ref); creates the file and removes it after the test."""
    data, ref = request.param
    path = _REPORTS_DIR / f"coverage-{ref}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    yield ref
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# 1. Successful read of the seeded coverage-feat-auth report
# ---------------------------------------------------------------------------


def test_seeded_report_returns_dict():
    """get_coverage_report('feat-auth') must return a dict."""
    result = get_coverage_report(_SEEDED_REF)
    assert isinstance(result, dict)


def test_seeded_report_has_required_top_level_keys():
    """The returned dict must have ref, total_coverage_pct, and files."""
    result = get_coverage_report(_SEEDED_REF)
    assert "ref" in result
    assert "total_coverage_pct" in result
    assert "files" in result


# ---------------------------------------------------------------------------
# 2. Correct total coverage value (68%)
# ---------------------------------------------------------------------------


def test_seeded_total_coverage_is_68():
    """total_coverage_pct must be 68.0 for the seeded feat-auth report."""
    result = get_coverage_report(_SEEDED_REF)
    assert result["total_coverage_pct"] == _SEEDED_TOTAL_COVERAGE


# ---------------------------------------------------------------------------
# 3. Correct file-level fields
# ---------------------------------------------------------------------------


def test_seeded_files_is_list():
    """files must be a non-empty list."""
    result = get_coverage_report(_SEEDED_REF)
    assert isinstance(result["files"], list)
    assert len(result["files"]) > 0


def test_seeded_file_entries_have_required_fields():
    """Every file entry must have path, coverage_pct, and uncovered_lines."""
    result = get_coverage_report(_SEEDED_REF)
    for entry in result["files"]:
        assert "path" in entry, f"Missing 'path' in {entry}"
        assert "coverage_pct" in entry, f"Missing 'coverage_pct' in {entry}"
        assert "uncovered_lines" in entry, f"Missing 'uncovered_lines' in {entry}"


def test_seeded_file_entries_have_no_extra_fields():
    """Returned file entries must contain ONLY the three required fields."""
    result = get_coverage_report(_SEEDED_REF)
    for entry in result["files"]:
        assert set(entry.keys()) == {"path", "coverage_pct", "uncovered_lines"}, (
            f"Unexpected keys in file entry: {set(entry.keys())}"
        )


def test_seeded_output_has_no_extra_top_level_fields():
    """Returned dict must contain ONLY the three required top-level fields."""
    result = get_coverage_report(_SEEDED_REF)
    assert set(result.keys()) == {"ref", "total_coverage_pct", "files"}


# ---------------------------------------------------------------------------
# 4. Correct uncovered-line data
# ---------------------------------------------------------------------------


def test_seeded_uncovered_lines_are_lists():
    """uncovered_lines must be a list for every file entry."""
    result = get_coverage_report(_SEEDED_REF)
    for entry in result["files"]:
        assert isinstance(entry["uncovered_lines"], list), (
            f"uncovered_lines is not a list for {entry['path']!r}"
        )


def test_seeded_known_uncovered_lines():
    """Check uncovered lines for a known file in the seeded report."""
    result = get_coverage_report(_SEEDED_REF)
    # Find src/auth/token.py which has known uncovered lines [45, 46, 47]
    token_entry = next(
        (e for e in result["files"] if e["path"] == "src/auth/token.py"), None
    )
    assert token_entry is not None, "Expected 'src/auth/token.py' in seeded report"
    assert token_entry["uncovered_lines"] == [45, 46, 47]


def test_seeded_fully_covered_file_has_empty_uncovered_lines():
    """A fully covered file (100%) must have an empty uncovered_lines list."""
    result = get_coverage_report(_SEEDED_REF)
    test_entry = next(
        (e for e in result["files"] if e["path"] == "tests/test_auth.py"), None
    )
    assert test_entry is not None, "Expected 'tests/test_auth.py' in seeded report"
    assert test_entry["coverage_pct"] == 100.0
    assert test_entry["uncovered_lines"] == []


# ---------------------------------------------------------------------------
# 5. Missing report file
# ---------------------------------------------------------------------------


def test_missing_report_raises_not_found():
    """A ref with no corresponding file must raise CoverageReportNotFoundError."""
    with pytest.raises(CoverageReportNotFoundError):
        get_coverage_report("ref-does-not-exist-99999")


def test_missing_report_error_message_contains_ref():
    """The CoverageReportNotFoundError message must name the missing ref."""
    ref = "no-such-ref-xyz"
    with pytest.raises(CoverageReportNotFoundError, match=ref):
        get_coverage_report(ref)


# ---------------------------------------------------------------------------
# 6. Malformed JSON
# ---------------------------------------------------------------------------


@pytest.fixture()
def malformed_json_report(tmp_path, monkeypatch):
    """Patch _REPORTS_DIR to a tmpdir and write a non-JSON file there."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    bad_file = tmp_path / "coverage-bad-json.json"
    bad_file.write_text("{ this is not json }", encoding="utf-8")
    return "bad-json"


def test_malformed_json_raises(malformed_json_report):
    """A report file with invalid JSON must raise InvalidCoverageReportError."""
    with pytest.raises(InvalidCoverageReportError, match="not valid JSON"):
        get_coverage_report(malformed_json_report)


# ---------------------------------------------------------------------------
# 7. Missing required top-level field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_key", ["ref", "total_coverage_pct", "files"])
def test_missing_top_level_field_raises(missing_key, tmp_path, monkeypatch):
    """A report missing any required top-level field must raise InvalidCoverageReportError."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    complete = {
        "ref": "feat-test",
        "total_coverage_pct": 75.0,
        "files": [],
    }
    del complete[missing_key]
    ref = "missing-field-test"
    report_path = tmp_path / f"coverage-{ref}.json"
    report_path.write_text(json.dumps(complete), encoding="utf-8")

    with pytest.raises(InvalidCoverageReportError, match=missing_key):
        get_coverage_report(ref)


# ---------------------------------------------------------------------------
# 8. Malformed file entry / missing required file-level field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_key", ["path", "coverage_pct", "uncovered_lines"])
def test_missing_file_entry_field_raises(missing_key, tmp_path, monkeypatch):
    """A file entry missing any required field must raise InvalidCoverageReportError."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    entry = {
        "path": "src/example.py",
        "coverage_pct": 80.0,
        "uncovered_lines": [1, 2],
    }
    del entry[missing_key]
    data = {
        "ref": "feat-test",
        "total_coverage_pct": 80.0,
        "files": [entry],
    }
    ref = "bad-file-entry"
    report_path = tmp_path / f"coverage-{ref}.json"
    report_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InvalidCoverageReportError, match=missing_key):
        get_coverage_report(ref)


def test_file_entry_not_object_raises(tmp_path, monkeypatch):
    """A file entry that is not a dict must raise InvalidCoverageReportError."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    data = {
        "ref": "feat-test",
        "total_coverage_pct": 80.0,
        "files": ["not-a-dict"],
    }
    ref = "bad-entry-type"
    (tmp_path / f"coverage-{ref}.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InvalidCoverageReportError):
        get_coverage_report(ref)


def test_files_not_list_raises(tmp_path, monkeypatch):
    """'files' that is not a list must raise InvalidCoverageReportError."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    data = {
        "ref": "feat-test",
        "total_coverage_pct": 80.0,
        "files": "not-a-list",
    }
    ref = "bad-files-type"
    (tmp_path / f"coverage-{ref}.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InvalidCoverageReportError):
        get_coverage_report(ref)


def test_total_coverage_pct_not_numeric_raises(tmp_path, monkeypatch):
    """'total_coverage_pct' that is not numeric must raise InvalidCoverageReportError."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    data = {
        "ref": "feat-test",
        "total_coverage_pct": "eighty",
        "files": [],
    }
    ref = "bad-total-type"
    (tmp_path / f"coverage-{ref}.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InvalidCoverageReportError):
        get_coverage_report(ref)


def test_file_coverage_pct_not_numeric_raises(tmp_path, monkeypatch):
    """file entry 'coverage_pct' that is not numeric must raise InvalidCoverageReportError."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    data = {
        "ref": "feat-test",
        "total_coverage_pct": 80.0,
        "files": [
            {
                "path": "src/example.py",
                "coverage_pct": "high",
                "uncovered_lines": [],
            }
        ],
    }
    ref = "bad-file-cov-type"
    (tmp_path / f"coverage-{ref}.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(InvalidCoverageReportError):
        get_coverage_report(ref)


# ---------------------------------------------------------------------------
# 9. Numeric coverage values are preserved
# ---------------------------------------------------------------------------


def test_seeded_total_coverage_is_float():
    """total_coverage_pct must be a numeric type (int or float)."""
    result = get_coverage_report(_SEEDED_REF)
    assert isinstance(result["total_coverage_pct"], (int, float))


def test_numeric_coverage_preserved_exactly(tmp_path, monkeypatch):
    """Numeric coverage values must be preserved exactly without rounding."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    data = {
        "ref": "feat-precise",
        "total_coverage_pct": 68.123456789,
        "files": [
            {
                "path": "src/module.py",
                "coverage_pct": 91.666666667,
                "uncovered_lines": [10, 20],
            }
        ],
    }
    ref = "precise-coverage"
    (tmp_path / f"coverage-{ref}.json").write_text(json.dumps(data), encoding="utf-8")

    result = get_coverage_report(ref)
    assert result["total_coverage_pct"] == data["total_coverage_pct"]
    assert result["files"][0]["coverage_pct"] == data["files"][0]["coverage_pct"]


def test_integer_coverage_pct_preserved(tmp_path, monkeypatch):
    """Integer coverage_pct values (e.g. 100) must be preserved as-is."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    data = {
        "ref": "feat-int",
        "total_coverage_pct": 100,
        "files": [
            {
                "path": "src/complete.py",
                "coverage_pct": 100,
                "uncovered_lines": [],
            }
        ],
    }
    ref = "int-coverage"
    (tmp_path / f"coverage-{ref}.json").write_text(json.dumps(data), encoding="utf-8")

    result = get_coverage_report(ref)
    assert result["total_coverage_pct"] == 100
    assert result["files"][0]["coverage_pct"] == 100


# ---------------------------------------------------------------------------
# 10. Returned ref matches the requested ref
# ---------------------------------------------------------------------------


def test_returned_ref_matches_requested_seeded():
    """Returned ref must match the ref passed to get_coverage_report."""
    result = get_coverage_report(_SEEDED_REF)
    assert result["ref"] == _SEEDED_REF


def test_returned_ref_matches_requested_custom(tmp_path, monkeypatch):
    """Returned ref must match the ref argument, not the ref in the file."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    # The file contains ref "feat/auth" (different slash form) but the caller
    # supplies "feat-auth-v2" as the key — the returned ref must equal the
    # caller-supplied ref, not the value stored in the file.
    data = {
        "ref": "different-ref-in-file",
        "total_coverage_pct": 75.0,
        "files": [],
    }
    ref = "my-custom-ref"
    (tmp_path / f"coverage-{ref}.json").write_text(json.dumps(data), encoding="utf-8")

    result = get_coverage_report(ref)
    assert result["ref"] == ref


# ---------------------------------------------------------------------------
# Ref validation
# ---------------------------------------------------------------------------


def test_empty_ref_raises():
    """Empty ref must raise InvalidCoverageRefError."""
    with pytest.raises(InvalidCoverageRefError):
        get_coverage_report("")


def test_whitespace_only_ref_raises():
    """Whitespace-only ref must raise InvalidCoverageRefError."""
    with pytest.raises(InvalidCoverageRefError):
        get_coverage_report("   ")


def test_non_string_ref_raises():
    """Non-string ref must raise InvalidCoverageRefError."""
    with pytest.raises(InvalidCoverageRefError):
        get_coverage_report(42)  # type: ignore[arg-type]


def test_ref_with_forward_slash_raises():
    """Ref containing '/' must raise InvalidCoverageRefError (path traversal guard)."""
    with pytest.raises(InvalidCoverageRefError):
        get_coverage_report("feat/auth")


def test_ref_with_backslash_raises():
    """Ref containing '\\' must raise InvalidCoverageRefError (path traversal guard)."""
    with pytest.raises(InvalidCoverageRefError):
        get_coverage_report("feat\\auth")


def test_whitespace_stripped_from_valid_ref():
    """Leading/trailing whitespace must be stripped from the ref."""
    result = get_coverage_report(f"  {_SEEDED_REF}  ")
    assert result["ref"] == _SEEDED_REF


# ---------------------------------------------------------------------------
# JSON report is not a top-level object
# ---------------------------------------------------------------------------


def test_report_is_json_array_raises(tmp_path, monkeypatch):
    """A report that is a JSON array (not an object) must raise InvalidCoverageReportError."""
    monkeypatch.setattr("python.coverage_reader._REPORTS_DIR", tmp_path)
    ref = "array-report"
    (tmp_path / f"coverage-{ref}.json").write_text(
        json.dumps([{"path": "a.py"}]), encoding="utf-8"
    )
    with pytest.raises(InvalidCoverageReportError):
        get_coverage_report(ref)


# ---------------------------------------------------------------------------
# Output is JSON-serializable
# ---------------------------------------------------------------------------


def test_result_is_json_serializable():
    """The returned dict from the seeded report must be JSON-serializable."""
    import json as _json

    result = get_coverage_report(_SEEDED_REF)
    serialized = _json.dumps(result)
    parsed = _json.loads(serialized)
    assert parsed["ref"] == _SEEDED_REF
    assert parsed["total_coverage_pct"] == _SEEDED_TOTAL_COVERAGE
