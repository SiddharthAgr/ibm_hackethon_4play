/**
 * mcp/tools/run_pipeline.js
 * =========================
 * Trigger or fetch a CI pipeline run; returns the failure payload.
 *
 * For the hackathon demo this tool operates in two modes:
 *   1. FIXTURE MODE  (default): reads demo/fixtures/<ref>.json — no network needed.
 *   2. API MODE      (optional): calls the GitHub Actions API when CI_API_TOKEN is set
 *                                AND the ref looks like a live run ID.
 *
 * Output schema (same in both modes):
 *   {
 *     run_id:       string,
 *     ref:          string,
 *     status:       "passed" | "failed" | "running" | "unknown",
 *     failures:     [ { test_name, error_type, failing_file, failure_message } ],
 *     triggered_at: ISO8601 string,
 *     source:       "fixture" | "api"
 *   }
 */

'use strict';

const path = require('path');
const fs   = require('fs');

const FIXTURES_DIR = path.resolve(__dirname, '..', '..', 'demo', 'fixtures');

/**
 * @param {{ ref: string }} input
 * @returns {object} pipeline run payload
 */
function runPipeline(input) {
  const { ref } = input;
  if (!ref || typeof ref !== 'string') {
    throw new Error('run_pipeline: "ref" is required');
  }

  // ---------- FIXTURE MODE ----------
  // Normalise the ref to a safe filename: "run-42" → "run-42.json"
  const safeRef      = ref.replace(/[^a-zA-Z0-9._-]/g, '_');
  const fixturePath  = path.join(FIXTURES_DIR, `${safeRef}.json`);

  if (fs.existsSync(fixturePath)) {
    const data = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
    return { ...data, source: 'fixture' };
  }

  // ---------- API MODE (optional) ----------
  const token = process.env.CI_API_TOKEN;
  const repo  = process.env.GITHUB_REPO; // e.g. "SiddharthAgr/ibm_hackethon_4play"

  if (token && repo) {
    // Real GitHub Actions run lookup — synchronous via child_process for STDIO transport
    const { execSync } = require('child_process');
    try {
      const apiUrl = `https://api.github.com/repos/${repo}/actions/runs/${ref}`;
      const raw = execSync(
        `curl -sf -H "Authorization: Bearer ${token}" -H "Accept: application/vnd.github+json" "${apiUrl}"`,
        { timeout: 10_000 }
      ).toString();
      const run = JSON.parse(raw);
      return {
        run_id:       String(run.id),
        ref:          run.head_sha,
        status:       run.conclusion === 'success' ? 'passed' : run.conclusion === null ? 'running' : 'failed',
        failures:     [], // GitHub API does not expose per-test failures; agents parse logs separately
        triggered_at: run.run_started_at ?? run.created_at,
        source:       'api',
        _raw:         { workflow: run.name, html_url: run.html_url },
      };
    } catch (apiErr) {
      // Fall through to "unknown" response rather than crashing
      console.error('[run_pipeline] API call failed:', apiErr.message);
    }
  }

  // ---------- UNKNOWN RUN ----------
  return {
    run_id:       ref,
    ref,
    status:       'unknown',
    failures:     [],
    triggered_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    source:       'unknown',
    _hint:        `No fixture found at ${fixturePath}. Add demo/fixtures/${safeRef}.json or set CI_API_TOKEN + GITHUB_REPO env vars.`,
  };
}

module.exports = { runPipeline };
