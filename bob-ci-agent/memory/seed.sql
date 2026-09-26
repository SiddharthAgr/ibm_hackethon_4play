-- =============================================================================
-- Failure Memory Store — seed.sql
-- Populate memory/failures.db with 10 realistic historical CI failures.
-- Run via:  npm run seed-db   (or)   sqlite3 memory/failures.db < memory/seed.sql
-- =============================================================================
--
-- Signatures are stable SHA-256 hashes of:
--   test_name + ":" + error_type + ":" + failing_file
-- Pre-computed so the demo can recall them without a live hash step.
--
-- Confidence scores:
--   high   >= 0.80   — at least 2 prior identical failures with matching resolutions
--   medium  0.50-0.79 — 1 prior failure or mixed outcomes
--   low    < 0.50   — first occurrence or no matching pattern
-- =============================================================================

-- Wipe existing seed rows so re-seeding is idempotent
DELETE FROM failures WHERE id IN (
    'f-seed-01','f-seed-02','f-seed-03','f-seed-04','f-seed-05',
    'f-seed-06','f-seed-07','f-seed-08','f-seed-09','f-seed-10'
);

-- ---------------------------------------------------------------------------
-- 1. Auth token expiry — AssertionError (HTTP 401 expected, 500 received)
--    This is the primary demo fixture: run-42 produces the same signature.
--    Two past occurrences → high confidence → action = revert
-- ---------------------------------------------------------------------------
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-01',
    'e05df3df6765b575ef14be0d76c581b5d7e29f641cd5520c270680c0fb63ecde',
    'run-38', 'task-session-001',
    'test_auth_token_expiry', 'AssertionError', 'tests/test_auth.py',
    'AssertionError: expected 401, got 500 — JWT middleware raised unhandled exception',
    'revert', 'Revert commit d4f9a12: JWT middleware change introduced in feat/auth broke token expiry path. Two prior failures confirm this pattern.',
    'high', 0.92,
    'Reverted commit d4f9a12 on feat/auth branch. Tests green after revert.',
    1, '2025-09-20T08:14:00Z'
);

INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-02',
    'e05df3df6765b575ef14be0d76c581b5d7e29f641cd5520c270680c0fb63ecde',
    'run-35', 'task-session-002',
    'test_auth_token_expiry', 'AssertionError', 'tests/test_auth.py',
    'AssertionError: expected 401, got 500 — JWT middleware raised unhandled exception',
    'revert', 'Same error seen in run-30. Pattern: every feat/auth JWT change breaks this test. Recommend revert until JWT middleware is covered by unit tests.',
    'high', 0.88,
    'Reverted JWT middleware changes. Opened issue #241 to add unit tests before re-merging.',
    1, '2025-09-17T11:45:00Z'
);

-- ---------------------------------------------------------------------------
-- 2. Flaky integration test — timeout waiting for Redis
--    Two occurrences with action = rerun → pattern: infrastructure flake
-- ---------------------------------------------------------------------------
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-03',
    '56effcfd9638d069e96b6a83cc921cdc75e9a53320ce42e4dca4c36949e742eb',
    'run-36', 'task-session-003',
    'test_cache_write_under_load', 'TimeoutError', 'tests/integration/test_cache.py',
    'TimeoutError: Redis connection timed out after 5000ms — CI runner out of ephemeral memory',
    'rerun', 'Flaky timeout — Redis container on CI runner ran out of memory. Re-run the pipeline; no code change needed.',
    'high', 0.85,
    'Re-ran pipeline. Tests passed on second attempt. Added CI runner memory note to runbook.',
    1, '2025-09-18T14:22:00Z'
);

INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-04',
    '56effcfd9638d069e96b6a83cc921cdc75e9a53320ce42e4dca4c36949e742eb',
    'run-33', 'task-session-004',
    'test_cache_write_under_load', 'TimeoutError', 'tests/integration/test_cache.py',
    'TimeoutError: Redis connection timed out after 5000ms',
    'rerun', 'Second occurrence of Redis timeout on this test. CI flake — rerun resolves. Consider mocking Redis in unit tests to decouple from infra.',
    'high', 0.83,
    'Rerun resolved. Added retry logic in CI YAML for this test suite.',
    1, '2025-09-15T09:08:00Z'
);

-- ---------------------------------------------------------------------------
-- 3. Missing dependency — ImportError after a dependency was removed from requirements
-- ---------------------------------------------------------------------------
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-05',
    'df20a04a30cf463be8776afa3cf7937f4df2542b157dcc090194579adfffa7a9',
    'run-37', 'task-session-005',
    'test_report_pdf_export', 'ImportError', 'tests/test_reports.py',
    'ImportError: No module named ''reportlab'' — package removed from requirements.txt in feat/slim-deps',
    'fix', 'Add reportlab back to requirements.txt, or mock the PDF export in tests if the dependency is intentionally removed. One prior occurrence with same fix.',
    'medium', 0.72,
    'Added reportlab==4.0.9 back to requirements.txt. PR #256 merged.',
    1, '2025-09-19T16:55:00Z'
);

-- ---------------------------------------------------------------------------
-- 4. Type error — wrong return type from refactored service method
-- ---------------------------------------------------------------------------
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-06',
    '3aec2dcde503e9757a0e13b791b32cef046687709ce03958a7c3eea6f9e20f41',
    'run-39', 'task-session-006',
    'test_user_profile_serializer', 'TypeError', 'tests/test_serializers.py',
    'TypeError: expected str, got NoneType — user.display_name returned None after profile refactor',
    'fix', 'Guard None in UserProfile.display_name getter or update the serializer to handle None. Medium confidence — first occurrence but clear root cause.',
    'medium', 0.65,
    'Added None guard in UserProfile.display_name. Serializer test updated with null-profile fixture.',
    1, '2025-09-21T10:30:00Z'
);

-- ---------------------------------------------------------------------------
-- 5. Flaky network test — DNS resolution failure in CI sandbox
-- ---------------------------------------------------------------------------
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-07',
    '3a9c2298cccd892a01905336e54c10c8dc965680a48d304dc697981241041cf8',
    'run-40', 'task-session-007',
    'test_webhook_delivery_external', 'ConnectionError', 'tests/integration/test_webhooks.py',
    'ConnectionError: [Errno -2] Name or service not known — external webhook URL unreachable in CI sandbox',
    'rerun', 'CI sandbox DNS resolution failed for external webhook target. Infrastructure flake — no code defect. Rerun or mock the external call.',
    'high', 0.90,
    'Rerun succeeded. Added VCR cassette to intercept the external call in tests to prevent future flakes.',
    1, '2025-09-22T07:40:00Z'
);

-- ---------------------------------------------------------------------------
-- 6. Coverage gate failure — coverage dropped below threshold after refactor
--    action = fix (add tests); escalate if low confidence
-- ---------------------------------------------------------------------------
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-08',
    'b34bbc88c80ddf14e54c9a363765fdbff44a90e653e3be706fc4febe5d24e62d',
    'run-34', 'task-session-008',
    'coverage_gate_check', 'CoverageError', 'python/ci_client.py',
    'CoverageError: total coverage 68% is below required threshold 80% — 23 lines uncovered in ci_client.py',
    'fix', 'Add unit tests for uncovered branches in ci_client.py (lines 45-67, 112-130). Coverage subagent can generate specific targets. Deploy is blocked until gate passes.',
    'high', 0.87,
    'Added 18 new test cases covering pipeline status parsing and error branches. Coverage raised to 84%.',
    1, '2025-09-16T13:15:00Z'
);

-- ---------------------------------------------------------------------------
-- 7. AttributeError — missing attribute after model schema migration
-- ---------------------------------------------------------------------------
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-09',
    '3c66c75c496d7e1b0523ace9ee97ad6473fc957e8086a315520bc54f541dbbcb',
    'run-41', 'task-session-009',
    'test_pipeline_run_status_model', 'AttributeError', 'tests/test_models.py',
    'AttributeError: ''PipelineRun'' object has no attribute ''triggered_by'' — field added to DB but model class not updated',
    'fix', 'Add triggered_by field to PipelineRun model class and update the migration. Low-risk fix — model/migration mismatch is the clear cause.',
    'medium', 0.75,
    'Added triggered_by to PipelineRun dataclass and Alembic migration. All model tests pass.',
    1, '2025-09-23T09:05:00Z'
);

-- ---------------------------------------------------------------------------
-- 8. New / unseen failure — low confidence, escalate for human review
--    This tests the escalation path in benchmark.py
-- ---------------------------------------------------------------------------
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved, stored_at
) VALUES (
    'f-seed-10',
    '822a91f2d2a3127e29937019a19f744a7849ffe81e7be114e2a8ba4d065c9057',
    'run-43', 'task-session-010',
    'test_kubernetes_manifest_validation', 'ValidationError', 'tests/test_deploy.py',
    'ValidationError: Kubernetes manifest missing required field ''resources.limits'' in deployment spec',
    'escalate', 'No prior record of this failure. Manual review required — possible intentional manifest change or new validation rule. Escalating to on-call.',
    'low', 0.35,
    NULL,
    0, '2025-09-24T17:20:00Z'
);
