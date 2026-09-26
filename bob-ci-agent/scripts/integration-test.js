#!/usr/bin/env node
/**
 * scripts/integration-test.js
 * ============================
 * Exercises the MCP tool handlers directly (no STDIO) to verify
 * the full Bob → MCP → SQLite → Bob data flow.
 *
 * Tests:
 *   1. recall_failures: auth token expiry → f-seed-01, f-seed-02 (action=revert, confidence=high)
 *   2. recall_failures: Redis timeout    → f-seed-03, f-seed-04 (action=rerun, confidence=high)
 *   3. recall_failures: unseen failure   → 0 matches (escalation path)
 *   4. recall_failures: auth w/ oauth file → 0 matches (signature isolation)
 *   5. store_failure:   new triage result → returns stored:true + failure_id
 *   6. run_pipeline:    run-42 fixture    → returns status=failed, 1 failure
 *   7. get_coverage_report: feat/auth     → total=68%, BLOCKER for coverage gate
 *   8. check_release_readiness: feat/auth → overall=BLOCKER
 */

'use strict';

const { getDb }             = require('../mcp/db');
const { recallFailures }    = require('../mcp/tools/recall_failures');
const { storeFailure }      = require('../mcp/tools/store_failure');
const { runPipeline }       = require('../mcp/tools/run_pipeline');
const { getCoverageReport } = require('../mcp/tools/get_coverage_report');
const { checkReleaseReadiness } = require('../mcp/tools/check_release_readiness');

let passed = 0;
let failed = 0;

function assert(label, condition, got) {
  if (condition) {
    console.log(`  ✓ ${label}`);
    passed++;
  } else {
    console.error(`  ✗ ${label}${got !== undefined ? `  (got: ${JSON.stringify(got)})` : ''}`);
    failed++;
  }
}

async function main() {
  // Initialise DB
  await getDb();
  console.log('[integration] DB initialised\n');

  // ─── Test 1: auth token expiry ────────────────────────────────────────────
  console.log('Test 1 — recall_failures: auth token expiry (eval-01)');
  {
    const r = await recallFailures({
      signature: 'e05df3df6765b575ef14be0d76c581b5d7e29f641cd5520c270680c0fb63ecde',
      limit: 5,
    });
    assert('total_found = 2',         r.total_found === 2,             r.total_found);
    assert('matches[0].id = f-seed-01', r.matches[0]?.failure_id === 'f-seed-01', r.matches[0]?.failure_id);
    assert('matches[1].id = f-seed-02', r.matches[1]?.failure_id === 'f-seed-02', r.matches[1]?.failure_id);
    assert('action = revert',         r.matches.every(m => m.action === 'revert'), r.matches.map(m => m.action));
    assert('confidence = high',       r.matches.every(m => m.confidence === 'high'), r.matches.map(m => m.confidence));
    console.log();
  }

  // ─── Test 2: Redis timeout ───────────────────────────────────────────────
  console.log('Test 2 — recall_failures: Redis timeout (eval-02)');
  {
    const r = await recallFailures({
      signature: '56effcfd9638d069e96b6a83cc921cdc75e9a53320ce42e4dca4c36949e742eb',
      limit: 5,
    });
    assert('total_found = 2',         r.total_found === 2,             r.total_found);
    assert('action = rerun',          r.matches.every(m => m.action === 'rerun'), r.matches.map(m => m.action));
    assert('confidence = high',       r.matches.every(m => m.confidence === 'high'), r.matches.map(m => m.confidence));
    console.log();
  }

  // ─── Test 3: unseen failure (escalation) ─────────────────────────────────
  console.log('Test 3 — recall_failures: unseen billing failure (eval-09)');
  {
    const r = await recallFailures({
      signature: '9c9171d7da672706546650088b217d8149e8c0abdb56a32794bbfb4919b8d7fa',
      limit: 5,
    });
    assert('total_found = 0 → escalate', r.total_found === 0, r.total_found);
    assert('matches is empty array',     r.matches.length === 0, r.matches.length);
    console.log();
  }

  // ─── Test 4: signature isolation (eval-10) ────────────────────────────────
  console.log('Test 4 — recall_failures: same test/error, different file (eval-10)');
  {
    const r = await recallFailures({
      signature: 'a5af2e26e14c78cc2bf1eaf44621034fe03130fe16ed1c7aed7589dd10e8aebc',
      limit: 5,
    });
    assert('total_found = 0 (oauth file is isolated)', r.total_found === 0, r.total_found);
    console.log();
  }

  // ─── Test 5: store_failure ───────────────────────────────────────────────
  console.log('Test 5 — store_failure: persist a new triage result');
  {
    const r = await storeFailure({
      signature:       'deadbeef1234567890abcdef1234567890abcdef1234567890abcdef12345678',
      test_name:       'test_integration_store',
      error_type:      'TypeError',
      failing_file:    'tests/test_integration.py',
      action:          'fix',
      confidence:      'medium',
      confidence_score: 0.65,
      run_id:          'run-integration-01',
      failure_message: 'TypeError: integration test store',
      recommendation:  'Fix the type error in integration test',
    });
    assert('stored = true',           r.stored === true,              r);
    assert('failure_id starts f-',    r.failure_id?.startsWith('f-'), r.failure_id);
    assert('stored_at is present',    !!r.stored_at,                  r.stored_at);

    // Verify recall gets it back
    const recall = await recallFailures({
      signature: 'deadbeef1234567890abcdef1234567890abcdef1234567890abcdef12345678',
    });
    assert('recall finds stored row', recall.total_found >= 1,        recall.total_found);
    console.log();
  }

  // ─── Test 6: run_pipeline fixture ─────────────────────────────────────────
  console.log('Test 6 — run_pipeline: run-42 fixture');
  {
    const r = runPipeline({ ref: 'run-42' });
    assert('status = failed',         r.status === 'failed',          r.status);
    assert('source = fixture',        r.source === 'fixture',         r.source);
    assert('1 failure in payload',    r.failures.length === 1,        r.failures.length);
    assert('failure test_name matches', r.failures[0].test_name === 'test_auth_token_expiry', r.failures[0].test_name);
    assert('signature in fixture',    r.failures[0].signature === 'e05df3df6765b575ef14be0d76c581b5d7e29f641cd5520c270680c0fb63ecde', r.failures[0].signature);
    console.log();
  }

  // ─── Test 7: get_coverage_report ─────────────────────────────────────────
  console.log('Test 7 — get_coverage_report: feat/auth');
  {
    const r = getCoverageReport({ ref: 'feat/auth' });
    assert('total_coverage_pct = 68', r.total_coverage_pct === 68,   r.total_coverage_pct);
    assert('files array present',     Array.isArray(r.files),        typeof r.files);
    console.log();
  }

  // ─── Test 8: check_release_readiness ─────────────────────────────────────
  console.log('Test 8 — check_release_readiness: feat/auth → BLOCKER');
  {
    const r = await checkReleaseReadiness({ ref: 'feat/auth', target_env: 'staging' });
    assert('overall = BLOCKER',       r.overall === 'BLOCKER',        r.overall);
    const covCheck = r.checks.find(c => c.name === 'coverage_threshold');
    assert('coverage check = BLOCKER', covCheck?.status === 'BLOCKER', covCheck?.status);
    console.log();
  }

  // ─── Summary ─────────────────────────────────────────────────────────────
  console.log('='.repeat(60));
  console.log(`  PASSED: ${passed}   FAILED: ${failed}`);
  console.log('='.repeat(60));

  if (failed > 0) process.exitCode = 1;
  // Let the event loop drain naturally (avoids Windows UV worker cleanup crash)
}

main().catch(err => {
  console.error('[integration] Fatal:', err.message);
  console.error(err.stack);
  process.exitCode = 1;
});
