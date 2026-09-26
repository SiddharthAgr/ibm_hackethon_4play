/**
 * mcp/tools/store_failure.js
 * ==========================
 * Persists one CI failure triage result to the failure memory store.
 *
 * Contract (from Apurva's memory spec):
 *   Input : {
 *     run_id, session_id, signature,
 *     test_name, error_type, failing_file, failure_message,
 *     action, recommendation, confidence, confidence_score,
 *     resolution?, resolved?
 *   }
 *   Output: { stored: true, failure_id: "f-<uuid>", stored_at: ISO8601 }
 *         | { stored: false, error: string }
 *
 * IMPORTANT CONTRACT POINTS:
 *   - The caller (triage subagent) MUST pre-compute the signature.
 *   - This tool does NOT hash — it is a pure storage layer.
 *   - Use error_type (not error_class) — matches Apurva's schema.
 */

'use strict';

const { v4: uuidv4 } = require('uuid');
const { getDb, queryOne, run } = require('../db');

const INSERT_SQL = `
  INSERT INTO failures (
      id, signature, run_id, session_id,
      test_name, error_type, failing_file, failure_message,
      action, recommendation, confidence, confidence_score,
      resolution, resolved
  ) VALUES (
      ?, ?, ?, ?,
      ?, ?, ?, ?,
      ?, ?, ?, ?,
      ?, ?
  )
`;

const READ_STORED_AT_SQL = `SELECT stored_at FROM failures WHERE id = ?`;

function requireString(obj, field) {
  if (!obj[field] || typeof obj[field] !== 'string') {
    throw new Error(`store_failure: "${field}" is required and must be a non-empty string`);
  }
}

/**
 * @param {object} input
 * @returns {Promise<{ stored: boolean, failure_id?: string, stored_at?: string, error?: string }>}
 */
async function storeFailure(input) {
  try {
    requireString(input, 'signature');
    requireString(input, 'test_name');
    requireString(input, 'error_type');
    requireString(input, 'failing_file');
    requireString(input, 'action');
    requireString(input, 'confidence');

    const validActions = ['rerun', 'fix', 'revert', 'escalate'];
    if (!validActions.includes(input.action)) {
      throw new Error(`store_failure: action must be one of ${validActions.join(', ')}`);
    }

    const validConfidences = ['high', 'medium', 'low'];
    if (!validConfidences.includes(input.confidence)) {
      throw new Error(`store_failure: confidence must be one of ${validConfidences.join(', ')}`);
    }

    await getDb();

    const failureId = `f-${uuidv4()}`;

    run(INSERT_SQL, [
      failureId,
      input.signature,
      input.run_id           ?? null,
      input.session_id       ?? null,
      input.test_name,
      input.error_type,
      input.failing_file,
      input.failure_message  ?? null,
      input.action,
      input.recommendation   ?? null,
      input.confidence,
      input.confidence_score ?? null,
      input.resolution       ?? null,
      input.resolved ? 1 : 0,
    ]);

    const row = queryOne(READ_STORED_AT_SQL, [failureId]);
    return {
      stored:     true,
      failure_id: failureId,
      stored_at:  row?.stored_at ?? new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    };
  } catch (err) {
    return {
      stored: false,
      error:  err.message,
    };
  }
}

module.exports = { storeFailure };
