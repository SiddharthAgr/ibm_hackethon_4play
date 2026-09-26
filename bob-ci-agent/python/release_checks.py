"""
release_checks.py — Release-readiness business logic for the CI/CD Intelligence Agent.

Public API
----------
    check_release_readiness(
        ref: str,
        target_env: str,
        passed_tests: int,
        total_tests: int,
        coverage_pct: float,
        commits_behind: int,
        unresolved_blocker_count: int,
    ) -> ReadinessResult

All inputs are supplied by the caller (e.g., the Python MCP layer).
This module contains ONLY decision logic — no database access, no network
calls, no MCP registration, no Node.js interaction.

The individual check functions are also exported so callers or tests can
invoke them in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Status = Literal["PASS", "WARNING", "BLOCKER"]

# Stable string constants used as check names. The MCP layer depends on these
# being stable across versions — change them only with a coordinated update.
CHECK_TEST_PASS_RATE = "test_pass_rate"
CHECK_COVERAGE = "coverage"
CHECK_UNRESOLVED_BLOCKERS = "unresolved_blockers"
CHECK_BRANCH_BEHIND_MAIN = "branch_behind_main"


@dataclass(frozen=True)
class CheckResult:
    """Result of a single release gate check."""

    name: str
    status: Status
    detail: str


@dataclass(frozen=True)
class ReadinessResult:
    """Aggregated release-readiness result returned to the caller."""

    overall: Status
    checks: list[CheckResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation matching the MCP output schema."""
        return {
            "overall": self.overall,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail}
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def check_test_pass_rate(passed: int, total: int) -> CheckResult:
    """Evaluate the test pass-rate gate.

    Parameters
    ----------
    passed:
        Number of tests that passed.
    total:
        Total number of tests executed.

    Returns
    -------
    CheckResult
        PASS   — 100 % of tests passed.
        WARNING — 90 % <= pass rate < 100 %.
        BLOCKER — pass rate < 90 %, OR total <= 0 (unavailable/zero test data).
    """
    if total <= 0:
        return CheckResult(
            name=CHECK_TEST_PASS_RATE,
            status="BLOCKER",
            detail=f"Test data unavailable or zero tests reported (total={total}).",
        )
    if passed < 0 or passed > total:
        return CheckResult(
            name=CHECK_TEST_PASS_RATE,
            status="BLOCKER",
            detail=f"Invalid test counts: passed={passed}, total={total}.",
        )

    # Use integer arithmetic to preserve exact precision (avoids float drift).
    # pass_rate_pct = (passed / total) * 100 — keep as fraction for comparisons.
    if passed == total:
        return CheckResult(
            name=CHECK_TEST_PASS_RATE,
            status="PASS",
            detail=f"All {total} tests passed (100.0%).",
        )

    # passed < total from here on
    pct = passed / total * 100  # float, used only for the detail string
    if passed * 10 >= total * 9:  # passed/total >= 90/100 === passed*10 >= total*9
        return CheckResult(
            name=CHECK_TEST_PASS_RATE,
            status="WARNING",
            detail=f"{passed}/{total} tests passed ({pct:.2f}%). Below 100% pass rate.",
        )
    return CheckResult(
        name=CHECK_TEST_PASS_RATE,
        status="BLOCKER",
        detail=f"{passed}/{total} tests passed ({pct:.2f}%). Below 90% threshold.",
    )


def check_coverage(coverage_pct: float) -> CheckResult:
    """Evaluate the code-coverage gate.

    Parameters
    ----------
    coverage_pct:
        Total coverage as a percentage in [0, 100].

    Returns
    -------
    CheckResult
        PASS    — coverage_pct >= 80.
        WARNING — 70 <= coverage_pct < 80.
        BLOCKER — coverage_pct < 70.
    """
    if coverage_pct >= 80.0:
        return CheckResult(
            name=CHECK_COVERAGE,
            status="PASS",
            detail=f"Coverage is {coverage_pct:.2f}% (threshold: 80%).",
        )
    if coverage_pct >= 70.0:
        return CheckResult(
            name=CHECK_COVERAGE,
            status="WARNING",
            detail=f"Coverage is {coverage_pct:.2f}% — below 80% target.",
        )
    return CheckResult(
        name=CHECK_COVERAGE,
        status="BLOCKER",
        detail=f"Coverage is {coverage_pct:.2f}% — below 70% minimum.",
    )


def check_unresolved_blockers(count: int) -> CheckResult:
    """Evaluate the unresolved-blockers gate.

    Parameters
    ----------
    count:
        Number of unresolved blocker failures recorded in the last 24 hours.
        Supplied by the caller (e.g., queried from the failure-memory layer).

    Returns
    -------
    CheckResult
        PASS    — count == 0.
        BLOCKER — count >= 1.  (No WARNING state for this check.)
    """
    if count == 0:
        return CheckResult(
            name=CHECK_UNRESOLVED_BLOCKERS,
            status="PASS",
            detail="No unresolved blocker failures in the last 24 hours.",
        )
    return CheckResult(
        name=CHECK_UNRESOLVED_BLOCKERS,
        status="BLOCKER",
        detail=f"{count} unresolved blocker failure(s) recorded in the last 24 hours.",
    )


def check_branch_behind_main(commits_behind: int) -> CheckResult:
    """Evaluate the branch-staleness gate.

    Parameters
    ----------
    commits_behind:
        Number of commits the branch is behind the main branch.

    Returns
    -------
    CheckResult
        PASS    — commits_behind == 0.
        WARNING — 1 <= commits_behind <= 5.
        BLOCKER — commits_behind > 5.
    """
    if commits_behind == 0:
        return CheckResult(
            name=CHECK_BRANCH_BEHIND_MAIN,
            status="PASS",
            detail="Branch is up to date with main.",
        )
    if commits_behind <= 5:
        return CheckResult(
            name=CHECK_BRANCH_BEHIND_MAIN,
            status="WARNING",
            detail=f"Branch is {commits_behind} commit(s) behind main.",
        )
    return CheckResult(
        name=CHECK_BRANCH_BEHIND_MAIN,
        status="BLOCKER",
        detail=f"Branch is {commits_behind} commit(s) behind main — exceeds 5-commit limit.",
    )


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


def _aggregate_status(checks: list[CheckResult]) -> Status:
    """Return the overall status according to precedence rules.

    BLOCKER > WARNING > PASS.
    """
    statuses = {c.status for c in checks}
    if "BLOCKER" in statuses:
        return "BLOCKER"
    if "WARNING" in statuses:
        return "WARNING"
    return "PASS"


def check_release_readiness(
    ref: str,
    target_env: str,
    passed_tests: int,
    total_tests: int,
    coverage_pct: float,
    commits_behind: int,
    unresolved_blocker_count: int,
) -> ReadinessResult:
    """Run all release-readiness gates and return the aggregated result.

    This is the primary entry point for the Python MCP layer.

    Parameters
    ----------
    ref:
        Branch or commit reference being evaluated (e.g. ``"feat/auth"``).
        Stored in the result for traceability; not used in the gate logic.
    target_env:
        Deployment target, e.g. ``"staging"`` or ``"dev"``.
        Stored for traceability; threshold rules are currently environment-agnostic.
    passed_tests:
        Number of tests that passed in the latest CI run for *ref*.
    total_tests:
        Total number of tests executed in that CI run.
    coverage_pct:
        Overall code-coverage percentage (0–100) from the latest report.
    commits_behind:
        How many commits *ref* is behind the main branch.
    unresolved_blocker_count:
        Number of unresolved blocker failures logged in the last 24 hours.
        Supplied by the failure-memory layer (not owned by this module).

    Returns
    -------
    ReadinessResult
        Structured gate result with an ``overall`` status and a ``checks`` list.
        Call ``.to_dict()`` to get a JSON-serialisable ``dict``.
    """
    checks: list[CheckResult] = [
        check_test_pass_rate(passed_tests, total_tests),
        check_coverage(coverage_pct),
        check_unresolved_blockers(unresolved_blocker_count),
        check_branch_behind_main(commits_behind),
    ]
    overall = _aggregate_status(checks)
    return ReadinessResult(overall=overall, checks=checks)
