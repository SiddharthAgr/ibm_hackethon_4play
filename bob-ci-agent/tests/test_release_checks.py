"""
tests/test_release_checks.py — Unit tests for python.release_checks.

All tests are deterministic and require no network access, no database,
no MCP server, no Node.js, and no GitHub API.

Coverage:
  1.  All checks PASS
  2.  Test pass rate WARNING
  3.  Test pass rate BLOCKER
  4.  Coverage WARNING
  5.  Coverage BLOCKER
  6.  Unresolved blocker present
  7.  Branch behind main WARNING
  8.  Branch behind main BLOCKER
  9.  BLOCKER overrides WARNING
  10. WARNING overrides PASS
  11. Exact threshold boundary values
  12. Zero / unavailable test data handling
"""

from __future__ import annotations

import pytest

from python.release_checks import (
    CHECK_BRANCH_BEHIND_MAIN,
    CHECK_COVERAGE,
    CHECK_TEST_PASS_RATE,
    CHECK_UNRESOLVED_BLOCKERS,
    ReadinessResult,
    check_branch_behind_main,
    check_coverage,
    check_release_readiness,
    check_test_pass_rate,
    check_unresolved_blockers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_pass_kwargs(**overrides) -> dict:
    """Return coordinator kwargs that produce all-PASS when unmodified."""
    base = dict(
        ref="feat/example",
        target_env="staging",
        passed_tests=100,
        total_tests=100,
        coverage_pct=85.0,
        commits_behind=0,
        unresolved_blocker_count=0,
    )
    base.update(overrides)
    return base


# ===========================================================================
# 1. All checks PASS
# ===========================================================================


def test_all_checks_pass_overall():
    """When every gate passes the overall result is PASS."""
    result = check_release_readiness(**_all_pass_kwargs())
    assert result.overall == "PASS"


def test_all_checks_pass_individual_statuses():
    """Each individual check reports PASS when all inputs are ideal."""
    result = check_release_readiness(**_all_pass_kwargs())
    for check in result.checks:
        assert check.status == "PASS", f"{check.name} unexpectedly not PASS: {check}"


def test_all_checks_pass_check_names():
    """The four expected check names must all appear in the result."""
    result = check_release_readiness(**_all_pass_kwargs())
    names = {c.name for c in result.checks}
    assert CHECK_TEST_PASS_RATE in names
    assert CHECK_COVERAGE in names
    assert CHECK_UNRESOLVED_BLOCKERS in names
    assert CHECK_BRANCH_BEHIND_MAIN in names


def test_result_to_dict_schema():
    """to_dict() returns the expected MCP output schema."""
    result = check_release_readiness(**_all_pass_kwargs())
    d = result.to_dict()
    assert set(d.keys()) == {"overall", "checks"}
    assert d["overall"] == "PASS"
    for check in d["checks"]:
        assert set(check.keys()) == {"name", "status", "detail"}


# ===========================================================================
# 2. Test pass rate WARNING
# ===========================================================================


def test_test_pass_rate_warning_99_of_100():
    """99/100 tests passed (99%) triggers WARNING."""
    check = check_test_pass_rate(99, 100)
    assert check.status == "WARNING"


def test_test_pass_rate_warning_in_coordinator():
    """WARNING pass rate elevates overall to WARNING when no BLOCKER present."""
    result = check_release_readiness(**_all_pass_kwargs(passed_tests=99, total_tests=100))
    assert result.overall == "WARNING"


def test_test_pass_rate_warning_detail_mentions_pct():
    """WARNING detail message contains the pass count."""
    check = check_test_pass_rate(99, 100)
    assert "99" in check.detail


# ===========================================================================
# 3. Test pass rate BLOCKER
# ===========================================================================


def test_test_pass_rate_blocker_88_of_100():
    """88/100 tests passed (88%) triggers BLOCKER."""
    check = check_test_pass_rate(88, 100)
    assert check.status == "BLOCKER"


def test_test_pass_rate_blocker_in_coordinator():
    """BLOCKER pass rate makes overall BLOCKER."""
    result = check_release_readiness(**_all_pass_kwargs(passed_tests=88, total_tests=100))
    assert result.overall == "BLOCKER"


# ===========================================================================
# 4. Coverage WARNING
# ===========================================================================


def test_coverage_warning_79():
    """79% coverage triggers WARNING."""
    check = check_coverage(79.0)
    assert check.status == "WARNING"


def test_coverage_warning_in_coordinator():
    """Coverage WARNING elevates overall to WARNING."""
    result = check_release_readiness(**_all_pass_kwargs(coverage_pct=75.0))
    assert result.overall == "WARNING"


def test_coverage_warning_detail_contains_pct():
    """WARNING detail contains the coverage value."""
    check = check_coverage(75.0)
    assert "75.00" in check.detail


# ===========================================================================
# 5. Coverage BLOCKER
# ===========================================================================


def test_coverage_blocker_69():
    """69% coverage triggers BLOCKER."""
    check = check_coverage(69.0)
    assert check.status == "BLOCKER"


def test_coverage_blocker_in_coordinator():
    """Coverage BLOCKER makes overall BLOCKER."""
    result = check_release_readiness(**_all_pass_kwargs(coverage_pct=60.0))
    assert result.overall == "BLOCKER"


# ===========================================================================
# 6. Unresolved blocker present
# ===========================================================================


def test_unresolved_blocker_one():
    """1 unresolved blocker triggers BLOCKER."""
    check = check_unresolved_blockers(1)
    assert check.status == "BLOCKER"


def test_unresolved_blocker_zero_is_pass():
    """0 unresolved blockers is PASS."""
    check = check_unresolved_blockers(0)
    assert check.status == "PASS"


def test_unresolved_blocker_in_coordinator():
    """1 unresolved blocker makes overall BLOCKER."""
    result = check_release_readiness(**_all_pass_kwargs(unresolved_blocker_count=1))
    assert result.overall == "BLOCKER"


def test_unresolved_blocker_detail_contains_count():
    """BLOCKER detail contains the failure count."""
    check = check_unresolved_blockers(3)
    assert "3" in check.detail


def test_unresolved_blocker_no_warning_state():
    """Unresolved-blockers check has no WARNING state — only PASS or BLOCKER."""
    assert check_unresolved_blockers(0).status == "PASS"
    for n in (1, 2, 10):
        assert check_unresolved_blockers(n).status == "BLOCKER"


# ===========================================================================
# 7. Branch behind main WARNING
# ===========================================================================


def test_branch_behind_main_warning_1():
    """1 commit behind main triggers WARNING."""
    check = check_branch_behind_main(1)
    assert check.status == "WARNING"


def test_branch_behind_main_warning_5():
    """5 commits behind main triggers WARNING."""
    check = check_branch_behind_main(5)
    assert check.status == "WARNING"


def test_branch_behind_main_warning_in_coordinator():
    """WARNING commits-behind elevates overall to WARNING."""
    result = check_release_readiness(**_all_pass_kwargs(commits_behind=3))
    assert result.overall == "WARNING"


# ===========================================================================
# 8. Branch behind main BLOCKER
# ===========================================================================


def test_branch_behind_main_blocker_6():
    """6 commits behind main triggers BLOCKER."""
    check = check_branch_behind_main(6)
    assert check.status == "BLOCKER"


def test_branch_behind_main_blocker_in_coordinator():
    """BLOCKER commits-behind makes overall BLOCKER."""
    result = check_release_readiness(**_all_pass_kwargs(commits_behind=6))
    assert result.overall == "BLOCKER"


# ===========================================================================
# 9. BLOCKER overrides WARNING
# ===========================================================================


def test_blocker_overrides_warning():
    """When one check is WARNING and another is BLOCKER, overall must be BLOCKER."""
    result = check_release_readiness(
        **_all_pass_kwargs(
            passed_tests=95,   # WARNING (90–99%)
            total_tests=100,
            commits_behind=6,  # BLOCKER (>5)
        )
    )
    assert result.overall == "BLOCKER"


def test_blocker_overrides_warning_check_statuses():
    """Confirm that the individual check statuses are correct when mixed."""
    result = check_release_readiness(
        **_all_pass_kwargs(passed_tests=95, total_tests=100, commits_behind=6)
    )
    by_name = {c.name: c.status for c in result.checks}
    assert by_name[CHECK_TEST_PASS_RATE] == "WARNING"
    assert by_name[CHECK_BRANCH_BEHIND_MAIN] == "BLOCKER"


# ===========================================================================
# 10. WARNING overrides PASS
# ===========================================================================


def test_warning_overrides_pass():
    """When one check is WARNING and all others PASS, overall must be WARNING."""
    result = check_release_readiness(**_all_pass_kwargs(commits_behind=1))
    assert result.overall == "WARNING"


def test_warning_overrides_pass_other_checks_are_pass():
    """Confirm other checks remain PASS when only one WARNING present."""
    result = check_release_readiness(**_all_pass_kwargs(commits_behind=1))
    by_name = {c.name: c.status for c in result.checks}
    assert by_name[CHECK_TEST_PASS_RATE] == "PASS"
    assert by_name[CHECK_COVERAGE] == "PASS"
    assert by_name[CHECK_UNRESOLVED_BLOCKERS] == "PASS"
    assert by_name[CHECK_BRANCH_BEHIND_MAIN] == "WARNING"


# ===========================================================================
# 11. Exact threshold boundary values
# ===========================================================================


# --- Test pass rate boundaries ---

@pytest.mark.parametrize("passed,total,expected_status", [
    (89, 100, "BLOCKER"),   # 89% — below 90% threshold
    (90, 100, "WARNING"),   # 90% — exactly at lower WARNING boundary
    (99, 100, "WARNING"),   # 99% — top of WARNING range
    (100, 100, "PASS"),     # 100% — exactly PASS
])
def test_pass_rate_boundary(passed, total, expected_status):
    """Exact boundary values for test pass-rate thresholds."""
    check = check_test_pass_rate(passed, total)
    assert check.status == expected_status, (
        f"Expected {expected_status} for {passed}/{total}, got {check.status}"
    )


# --- Coverage boundaries ---

@pytest.mark.parametrize("pct,expected_status", [
    (69.0,  "BLOCKER"),   # just below 70% threshold
    (69.99, "BLOCKER"),   # still below 70%
    (70.0,  "WARNING"),   # exactly at 70% lower boundary
    (79.0,  "WARNING"),   # inside WARNING range
    (79.99, "WARNING"),   # just below 80%
    (80.0,  "PASS"),      # exactly at 80% boundary
    (80.01, "PASS"),      # just above 80%
])
def test_coverage_boundary(pct, expected_status):
    """Exact boundary values for coverage thresholds."""
    check = check_coverage(pct)
    assert check.status == expected_status, (
        f"Expected {expected_status} for coverage={pct}, got {check.status}"
    )


# --- Branch behind main boundaries ---

@pytest.mark.parametrize("behind,expected_status", [
    (0, "PASS"),
    (1, "WARNING"),
    (5, "WARNING"),
    (6, "BLOCKER"),
])
def test_branch_behind_boundary(behind, expected_status):
    """Exact boundary values for commits-behind-main thresholds."""
    check = check_branch_behind_main(behind)
    assert check.status == expected_status, (
        f"Expected {expected_status} for commits_behind={behind}, got {check.status}"
    )


# --- Unresolved blockers boundaries ---

@pytest.mark.parametrize("count,expected_status", [
    (0, "PASS"),
    (1, "BLOCKER"),
])
def test_unresolved_blockers_boundary(count, expected_status):
    """Exact boundary values for unresolved-blocker count."""
    check = check_unresolved_blockers(count)
    assert check.status == expected_status


# ===========================================================================
# 12. Zero / unavailable test data handling
# ===========================================================================


def test_zero_total_tests_is_blocker():
    """Zero total tests must be treated as BLOCKER, never silently PASS."""
    check = check_test_pass_rate(0, 0)
    assert check.status == "BLOCKER"


def test_zero_total_tests_detail_is_informative():
    """The BLOCKER detail for zero tests explains the unavailability."""
    check = check_test_pass_rate(0, 0)
    assert "0" in check.detail  # mentions the zero value


def test_negative_total_tests_is_blocker():
    """Negative total is invalid data — must be treated as BLOCKER."""
    check = check_test_pass_rate(0, -1)
    assert check.status == "BLOCKER"


def test_zero_total_tests_in_coordinator():
    """Zero total tests propagates BLOCKER through the coordinator."""
    result = check_release_readiness(**_all_pass_kwargs(passed_tests=0, total_tests=0))
    assert result.overall == "BLOCKER"


def test_passed_exceeds_total_is_blocker():
    """passed > total is invalid data and must be treated as BLOCKER."""
    check = check_test_pass_rate(101, 100)
    assert check.status == "BLOCKER"


def test_negative_passed_is_blocker():
    """Negative passed count is invalid data and must be treated as BLOCKER."""
    check = check_test_pass_rate(-1, 100)
    assert check.status == "BLOCKER"


# ===========================================================================
# Structural / regression guards
# ===========================================================================


def test_result_is_readiness_result_instance():
    """Coordinator must return a ReadinessResult instance."""
    result = check_release_readiness(**_all_pass_kwargs())
    assert isinstance(result, ReadinessResult)


def test_result_has_four_checks():
    """There must be exactly four checks in the result."""
    result = check_release_readiness(**_all_pass_kwargs())
    assert len(result.checks) == 4


def test_check_names_are_stable():
    """Check name constants must match the values in the result."""
    result = check_release_readiness(**_all_pass_kwargs())
    names = [c.name for c in result.checks]
    assert CHECK_TEST_PASS_RATE in names
    assert CHECK_COVERAGE in names
    assert CHECK_UNRESOLVED_BLOCKERS in names
    assert CHECK_BRANCH_BEHIND_MAIN in names


def test_to_dict_is_json_serialisable():
    """to_dict() output must be JSON-serialisable."""
    import json
    result = check_release_readiness(**_all_pass_kwargs())
    serialized = json.dumps(result.to_dict())
    parsed = json.loads(serialized)
    assert parsed["overall"] == "PASS"
    assert len(parsed["checks"]) == 4


def test_target_env_dev_same_logic():
    """target_env='dev' must apply the same thresholds as 'staging'."""
    staging = check_release_readiness(**_all_pass_kwargs(target_env="staging"))
    dev = check_release_readiness(**_all_pass_kwargs(target_env="dev"))
    assert staging.overall == dev.overall
    for s_check, d_check in zip(staging.checks, dev.checks):
        assert s_check.status == d_check.status
