---
description: Triage a CI pipeline failure by run ID
argument-hint: <run-id>
---

Call `run_pipeline` with `ref=$1`.

If `status` is `"failed"` and `failures` is non-empty:

1. For each failure in the failures array:
   a. Compute `signature = SHA-256(test_name + ":" + error_type + ":" + failing_file)`
   b. Call `recall_failures({ signature, limit: 5 })`
   c. Based on `total_found` and `confidence_score`, determine `action` and `confidence`
   d. Call `store_failure(...)` with the full payload and recommendation

2. Show a summary table:
   | Test | Error | Action | Confidence | History |
   |------|-------|--------|------------|---------|
   | ... | ... | ... | ... | N matches |

3. If any action is `"revert"`, show the specific commit to revert from the recommendation.
4. If any action is `"escalate"`, note that on-call has been notified.
5. If action is `"fix"`, show the specific lines/files to fix from the recommendation.
6. If action is `"rerun"`, confirm this is a known infrastructure flake.

If `status` is `"passed"`, report: "Pipeline $1 passed — no triage needed."
If `status` is `"unknown"`, report the hint from the run_pipeline response and suggest adding a fixture.
