#!/usr/bin/env python3
"""
evaluation/benchmark.py
=======================
Measures the quality of the failure memory recall pipeline against
a fixed set of ground-truth fixtures.

Metrics produced
----------------
retrieval_accuracy   : fraction of cases where at least one expected failure_id
                       was returned by recall_failures (hit-or-miss per case).
recommendation_match : fraction of cases where the recalled action matches the
                       expected action.
escalation_rate      : fraction of cases where total_found == 0 AND
                       expected.should_escalate is True  (correct escalations)
                       plus a false-escalation count (escalated when shouldn't).
latency_ms           : per-case and aggregate p50/p95 SQL query latency.

Usage
-----
    python evaluation/benchmark.py                        # default paths
    python evaluation/benchmark.py --db memory/failures.db \\
                                    --fixtures evaluation/fixtures/ci_failure_cases.json \\
                                    --out evaluation/results/

Dependencies
------------
    stdlib only: sqlite3, json, time, argparse, pathlib, statistics
    No pip installs needed — safe for Docker with python:3.11-slim.
"""

import argparse
import json
import pathlib
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Defaults — all relative to the repo root so the script works from anywhere
# ---------------------------------------------------------------------------
_REPO_ROOT     = pathlib.Path(__file__).resolve().parent.parent
_DEFAULT_DB    = _REPO_ROOT / "memory" / "failures.db"
_DEFAULT_FIX   = _REPO_ROOT / "evaluation" / "fixtures" / "ci_failure_cases.json"
_DEFAULT_OUT   = _REPO_ROOT / "evaluation" / "results"

RECALL_LIMIT   = 5          # mirrors the default in recall_failures MCP tool
LOW_CONF_THRESHOLD = 0.50   # confidence_score below this → would be "low" / escalate


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def open_db(db_path: pathlib.Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}", file=sys.stderr)
        print("        Run:  sqlite3 memory/failures.db < memory/schema.sql", file=sys.stderr)
        print("              sqlite3 memory/failures.db < memory/seed.sql", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def recall_failures(conn: sqlite3.Connection, signature: str, limit: int = RECALL_LIMIT) -> tuple[list[dict], float]:
    """
    Execute the same query used by recall_failures.js.
    Returns (rows_as_dicts, elapsed_ms).
    """
    sql = """
        SELECT
            id               AS failure_id,
            test_name,
            error_type,
            failing_file,
            action,
            recommendation,
            confidence,
            confidence_score,
            resolution,
            resolved,
            stored_at
        FROM failures
        WHERE signature = ?
        ORDER BY stored_at DESC
        LIMIT ?
    """
    t0 = time.perf_counter()
    cur = conn.execute(sql, (signature, limit))
    rows = [dict(r) for r in cur.fetchall()]
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return rows, elapsed_ms


# ---------------------------------------------------------------------------
# Triage logic (mirrors the triage subagent decision tree from the plan)
# ---------------------------------------------------------------------------

def decide_action(matches: list[dict]) -> tuple[str, str, float]:
    """
    Reproduce the triage subagent confidence logic so the benchmark can
    evaluate end-to-end recommendation quality without a live LLM.

    Returns (action, confidence_label, confidence_score).
    """
    if not matches:
        return "escalate", "low", 0.30

    # Collect actions from matches
    actions = [m["action"] for m in matches if m.get("action")]
    if not actions:
        return "escalate", "low", 0.30

    # Majority action
    action_counts: dict[str, int] = {}
    for a in actions:
        action_counts[a] = action_counts.get(a, 0) + 1
    majority_action = max(action_counts, key=lambda k: action_counts[k])

    # Use the average confidence_score from matched rows where available
    scores = [m["confidence_score"] for m in matches if m.get("confidence_score") is not None]
    avg_score: float = sum(scores) / len(scores) if scores else 0.0

    if len(matches) >= 2 and avg_score >= 0.80:
        return majority_action, "high", avg_score
    elif len(matches) >= 1 and avg_score >= 0.50:
        return majority_action, "medium", avg_score
    else:
        return "escalate", "low", avg_score


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_case(case: dict[str, Any], matches: list[dict], elapsed_ms: float) -> dict[str, Any]:
    """
    Evaluate one fixture case against recall results.
    Returns a result dict with per-metric pass/fail flags.
    """
    expected      = case["expected"]
    exp_ids       = set(expected.get("expected_ids", []))
    exp_action    = expected.get("action")
    exp_confidence= expected.get("confidence")
    exp_escalate  = expected.get("should_escalate", False)
    min_found     = expected.get("total_found_min", 0)

    returned_ids  = {m["failure_id"] for m in matches}
    total_found   = len(matches)

    # Retrieval accuracy: any expected ID was returned
    if exp_ids:
        retrieval_hit = bool(exp_ids & returned_ids)
    else:
        # No expected IDs → correct result is zero matches
        retrieval_hit = (total_found == 0)

    # Count check: at least total_found_min rows returned
    count_ok = (total_found >= min_found)

    # Derive recommendation via triage logic
    derived_action, derived_confidence, derived_score = decide_action(matches)

    recommendation_match = (derived_action == exp_action)
    confidence_match     = (derived_confidence == exp_confidence)

    # Escalation correctness
    actually_escalated = (derived_action == "escalate")
    if exp_escalate:
        escalation_correct = actually_escalated         # should escalate and did
        false_escalation   = False
    else:
        escalation_correct = not actually_escalated     # should NOT escalate and didn't
        false_escalation   = actually_escalated

    return {
        "case_id":              case["case_id"],
        "description":          case["description"],
        "total_found":          total_found,
        "count_ok":             count_ok,
        "returned_ids":         sorted(returned_ids),
        "retrieval_hit":        retrieval_hit,
        "expected_action":      exp_action,
        "derived_action":       derived_action,
        "recommendation_match": recommendation_match,
        "expected_confidence":  exp_confidence,
        "derived_confidence":   derived_confidence,
        "confidence_match":     confidence_match,
        "should_escalate":      exp_escalate,
        "did_escalate":         actually_escalated,
        "escalation_correct":   escalation_correct,
        "false_escalation":     false_escalation,
        "latency_ms":           round(elapsed_ms, 3),
    }


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {}

    retrieval_hits       = sum(1 for r in results if r["retrieval_hit"])
    recommendation_hits  = sum(1 for r in results if r["recommendation_match"])
    correct_escalations  = sum(1 for r in results if r["escalation_correct"])
    false_escalations    = sum(1 for r in results if r["false_escalation"])
    latencies            = [r["latency_ms"] for r in results]

    sorted_latencies = sorted(latencies)
    p50 = statistics.median(latencies)
    p95_idx = max(0, int(0.95 * n) - 1)
    p95 = sorted_latencies[p95_idx]

    return {
        "total_cases":              n,
        "retrieval_accuracy":       round(retrieval_hits / n, 4),
        "retrieval_hits":           retrieval_hits,
        "recommendation_match_rate":round(recommendation_hits / n, 4),
        "recommendation_hits":      recommendation_hits,
        "escalation_accuracy":      round(correct_escalations / n, 4),
        "correct_escalations":      correct_escalations,
        "false_escalation_count":   false_escalations,
        "latency_p50_ms":           round(p50, 3),
        "latency_p95_ms":           round(p95, 3),
        "latency_max_ms":           round(max(latencies), 3),
        "latency_min_ms":           round(min(latencies), 3),
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_json(out_dir: pathlib.Path, results: list[dict], summary: dict) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"benchmark_{ts}.json"
    payload = {
        "generated_at": ts,
        "summary":      summary,
        "cases":        results,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def write_markdown(out_dir: pathlib.Path, results: list[dict], summary: dict) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"benchmark_{ts}.md"

    lines = [
        "# Failure Memory Benchmark Results",
        "",
        f"**Generated:** {ts}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total cases | {summary['total_cases']} |",
        f"| Retrieval accuracy | {summary['retrieval_accuracy']:.0%} ({summary['retrieval_hits']}/{summary['total_cases']}) |",
        f"| Recommendation match rate | {summary['recommendation_match_rate']:.0%} ({summary['recommendation_hits']}/{summary['total_cases']}) |",
        f"| Escalation accuracy | {summary['escalation_accuracy']:.0%} ({summary['correct_escalations']}/{summary['total_cases']}) |",
        f"| False escalations | {summary['false_escalation_count']} |",
        f"| Latency p50 | {summary['latency_p50_ms']} ms |",
        f"| Latency p95 | {summary['latency_p95_ms']} ms |",
        f"| Latency max | {summary['latency_max_ms']} ms |",
        "",
        "## Per-case results",
        "",
        "| Case | Retrieved? | Action match? | Escalation OK? | Latency (ms) |",
        "|---|---|---|---|---|",
    ]

    for r in results:
        ret  = "PASS" if r["retrieval_hit"]        else "FAIL"
        rec  = "PASS" if r["recommendation_match"] else f"FAIL (got {r['derived_action']}, exp {r['expected_action']})"
        esc  = "PASS" if r["escalation_correct"]   else "FAIL"
        lines.append(
            f"| {r['case_id']} | {ret} | {rec} | {esc} | {r['latency_ms']} |"
        )

    lines += [
        "",
        "---",
        "",
        "_Generated by evaluation/benchmark.py_",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark the failure memory recall pipeline against fixtures."
    )
    parser.add_argument(
        "--db",
        type=pathlib.Path,
        default=_DEFAULT_DB,
        help=f"Path to failures.db  (default: {_DEFAULT_DB})",
    )
    parser.add_argument(
        "--fixtures",
        type=pathlib.Path,
        default=_DEFAULT_FIX,
        help=f"Path to fixture JSON  (default: {_DEFAULT_FIX})",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=_DEFAULT_OUT,
        help=f"Output directory      (default: {_DEFAULT_OUT})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=RECALL_LIMIT,
        help=f"recall_failures LIMIT (default: {RECALL_LIMIT})",
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="Skip writing JSON output file",
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Skip writing Markdown output file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Load fixtures
    if not args.fixtures.exists():
        print(f"[ERROR] Fixtures file not found: {args.fixtures}", file=sys.stderr)
        sys.exit(1)

    with args.fixtures.open() as f:
        fixture_cases: list[dict] = json.load(f)

    print(f"[benchmark] DB        : {args.db}")
    print(f"[benchmark] Fixtures  : {args.fixtures}  ({len(fixture_cases)} cases)")
    print(f"[benchmark] Output dir: {args.out}")
    print()

    conn = open_db(args.db)

    results: list[dict] = []
    for case in fixture_cases:
        sig = case["signature"]
        matches, elapsed_ms = recall_failures(conn, sig, limit=args.limit)
        result = score_case(case, matches, elapsed_ms)
        results.append(result)

        status = "PASS" if (result["retrieval_hit"] and result["recommendation_match"]) else "FAIL"
        print(
            f"  [{status}] {case['case_id']:10s}  "
            f"found={result['total_found']}  "
            f"action={result['derived_action']:8s}  "
            f"conf={result['derived_confidence']:6s}  "
            f"{result['latency_ms']:.2f}ms"
        )

    conn.close()

    summary = aggregate(results)
    print()
    print("=" * 60)
    print(f"  Retrieval accuracy       : {summary['retrieval_accuracy']:.0%}  ({summary['retrieval_hits']}/{summary['total_cases']})")
    print(f"  Recommendation match rate: {summary['recommendation_match_rate']:.0%}  ({summary['recommendation_hits']}/{summary['total_cases']})")
    print(f"  Escalation accuracy      : {summary['escalation_accuracy']:.0%}  ({summary['correct_escalations']}/{summary['total_cases']})")
    print(f"  False escalations        : {summary['false_escalation_count']}")
    print(f"  Latency p50/p95          : {summary['latency_p50_ms']}ms / {summary['latency_p95_ms']}ms")
    print("=" * 60)

    written: list[pathlib.Path] = []

    if not args.no_json:
        p = write_json(args.out, results, summary)
        written.append(p)
        print(f"\n[benchmark] JSON  -> {p}")

    if not args.no_markdown:
        p = write_markdown(args.out, results, summary)
        written.append(p)
        print(f"[benchmark] MD    -> {p}")

    # Exit non-zero if any case fails (useful for CI gate)
    any_fail = any(
        not (r["retrieval_hit"] and r["recommendation_match"])
        for r in results
    )
    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
