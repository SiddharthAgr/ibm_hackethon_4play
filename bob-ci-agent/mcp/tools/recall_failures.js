/**
 * mcp/tools/recall_failures.js
 * ============================
 * Retrieves historical CI failures matching a given SHA-256 signature.
 *
 * Contract (from Apurva's memory spec):
 *   Input : { signature: string, limit?: number }
 *   Output: { matches: [...], total_found: number }
 *
 * The signature is pre-computed by the triage subagent:
 *   SHA-256( test_name + ":" + error_type + ":" + failing_file )
 *
 * This tool is read-only — it never modifies the database.
 */

'use strict';

const { getDb, queryAll } = require('../db');

const RECALL_SQL = `
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
`;

/**
 * @param {{ signature: string, limit?: number }} input
 * @returns {Promise<{ matches: object[], total_found: number }>}
 */
async function recallFailures(input) {
  const { signature, limit = 5 } = input;

  if (!signature || typeof signature !== 'string') {
    throw new Error('recall_failures: "signature" is required and must be a string');
  }

  await getDb();   // ensure DB is initialised

  const rows = queryAll(RECALL_SQL, [signature, limit]);

  // Normalise resolved: SQLite stores as 0/1 integer; expose as boolean
  const matches = rows.map(row => ({
    ...row,
    resolved: row.resolved === 1,
  }));

  return {
    matches,
    total_found: matches.length,
  };
}

module.exports = { recallFailures };
