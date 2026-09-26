/**
 * mcp/tools/get_coverage_report.js
 * =================================
 * Fetch the latest coverage report for a git ref.
 *
 * Source: reports/coverage-<ref>.json  (file-based for demo)
 *   - "feat/auth" → reports/coverage-feat-auth.json
 *
 * Input:  { ref: string }
 * Output: {
 *   ref:               string,
 *   total_coverage_pct: number,
 *   files: [ { path, coverage_pct, uncovered_lines[] } ],
 *   source: "file"
 * }
 */

'use strict';

const path = require('path');
const fs   = require('fs');

const REPORTS_DIR = path.resolve(__dirname, '..', '..', 'reports');

/**
 * @param {{ ref: string }} input
 * @returns {object} coverage report
 */
function getCoverageReport(input) {
  const { ref } = input;
  if (!ref || typeof ref !== 'string') {
    throw new Error('get_coverage_report: "ref" is required');
  }

  // Normalise ref to filename-safe string
  const safeRef    = ref.replace(/\//g, '-').replace(/[^a-zA-Z0-9._-]/g, '_');
  const reportPath = path.join(REPORTS_DIR, `coverage-${safeRef}.json`);

  if (!fs.existsSync(reportPath)) {
    return {
      ref,
      total_coverage_pct: null,
      files:  [],
      source: 'file',
      error:  `Coverage report not found: ${path.basename(reportPath)}. Expected at reports/coverage-${safeRef}.json`,
    };
  }

  try {
    const raw    = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    const total  = raw.total_coverage_pct ?? raw.total ?? 0;
    const files  = raw.files ?? [];
    return {
      ref,
      total_coverage_pct: total,
      files,
      source: 'file',
    };
  } catch (err) {
    throw new Error(`get_coverage_report: failed to parse ${path.basename(reportPath)}: ${err.message}`);
  }
}

module.exports = { getCoverageReport };
