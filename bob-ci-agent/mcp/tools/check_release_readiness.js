/**
 * mcp/tools/check_release_readiness.js
 * =====================================
 * Run a set of release gates and return PASS / WARNING / BLOCKER status.
 *
 * Gates checked:
 *   1. coverage_threshold — total coverage >= 80% from reports/coverage-<ref>.json
 *   2. open_blockers      — no unresolved low-confidence failures in memory
 *   3. target_env         — valid deploy target
 *
 * Input:  { ref: string, target_env: "staging" | "dev" }
 * Output: {
 *   overall: "PASS" | "WARNING" | "BLOCKER",
 *   checks: [ { name, status, detail } ],
 *   ref, target_env
 * }
 */

'use strict';

const path = require('path');
const fs   = require('fs');
const { getDb, queryOne } = require('../db');

const REPORTS_DIR = path.resolve(__dirname, '..', '..', 'reports');
const COVERAGE_THRESHOLD = 80;

// ---------------------------------------------------------------------------
// Gate: coverage
// ---------------------------------------------------------------------------

function checkCoverage(ref) {
  const safeRef    = ref.replace(/\//g, '-').replace(/[^a-zA-Z0-9._-]/g, '_');
  const reportPath = path.join(REPORTS_DIR, `coverage-${safeRef}.json`);

  if (!fs.existsSync(reportPath)) {
    return {
      name:   'coverage_threshold',
      status: 'WARNING',
      detail: `No coverage report found for ref "${ref}" (looked for ${path.basename(reportPath)}). Cannot verify threshold.`,
    };
  }

  try {
    const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    const total  = report.total_coverage_pct ?? report.total ?? null;

    if (total === null) {
      return { name: 'coverage_threshold', status: 'WARNING', detail: 'Coverage report missing total_coverage_pct field.' };
    }
    if (total < COVERAGE_THRESHOLD) {
      return {
        name:   'coverage_threshold',
        status: 'BLOCKER',
        detail: `Coverage ${total}% is below required ${COVERAGE_THRESHOLD}%. Deploy is blocked until gate passes.`,
      };
    }
    return {
      name:   'coverage_threshold',
      status: 'PASS',
      detail: `Coverage ${total}% meets the ${COVERAGE_THRESHOLD}% threshold.`,
    };
  } catch (err) {
    return { name: 'coverage_threshold', status: 'WARNING', detail: `Failed to parse coverage report: ${err.message}` };
  }
}

// ---------------------------------------------------------------------------
// Gate: open escalations in memory
// ---------------------------------------------------------------------------

const OPEN_BLOCKERS_SQL = `
  SELECT COUNT(*) AS cnt
  FROM failures
  WHERE resolved = 0
    AND confidence = 'low'
    AND action    = 'escalate'
`;

async function checkOpenBlockers() {
  try {
    await getDb();
    const row = queryOne(OPEN_BLOCKERS_SQL);
    const cnt = row?.cnt ?? 0;
    if (cnt > 0) {
      return {
        name:   'open_blockers',
        status: 'WARNING',
        detail: `${cnt} unresolved low-confidence failure(s) pending escalation in failure memory.`,
      };
    }
    return { name: 'open_blockers', status: 'PASS', detail: 'No unresolved escalated failures in memory.' };
  } catch (err) {
    return { name: 'open_blockers', status: 'WARNING', detail: `Could not query failure memory: ${err.message}` };
  }
}

// ---------------------------------------------------------------------------
// Gate: target environment
// ---------------------------------------------------------------------------

function checkTargetEnv(targetEnv) {
  const allowed = ['staging', 'dev'];
  if (!allowed.includes(targetEnv)) {
    return {
      name:   'target_env',
      status: 'BLOCKER',
      detail: `Unknown target_env "${targetEnv}". Permitted values: ${allowed.join(', ')}.`,
    };
  }
  return {
    name:   'target_env',
    status: 'PASS',
    detail: `Target environment "${targetEnv}" is a valid deploy target.`,
  };
}

// ---------------------------------------------------------------------------
// Aggregator
// ---------------------------------------------------------------------------

/**
 * @param {{ ref: string, target_env?: string }} input
 * @returns {Promise<{ overall: string, checks: object[], ref: string, target_env: string }>}
 */
async function checkReleaseReadiness(input) {
  const { ref, target_env = 'staging' } = input;
  if (!ref || typeof ref !== 'string') {
    throw new Error('check_release_readiness: "ref" is required');
  }

  const checks = await Promise.all([
    checkCoverage(ref),          // sync but wrapped in Promise.all for consistency
    checkOpenBlockers(),
    checkTargetEnv(target_env),
  ]);

  let overall = 'PASS';
  for (const c of checks) {
    if (c.status === 'BLOCKER') { overall = 'BLOCKER'; break; }
    if (c.status === 'WARNING' && overall !== 'BLOCKER') { overall = 'WARNING'; }
  }

  return { overall, checks, ref, target_env };
}

module.exports = { checkReleaseReadiness };
