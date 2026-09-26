#!/usr/bin/env node
/**
 * mcp/server.js
 * =============
 * IBM Bob 2.0 Hackathon — CI Intelligence MCP Server
 * Team: 4Play | Owner: Bhavya (MCP layer)
 *
 * Transport : STDIO (Bob connects via .bob/mcp.json)
 * Runtime   : Node.js 20+
 *
 * Tools registered:
 *   1. run_pipeline           — fetch/trigger CI pipeline run (fixture or API)
 *   2. recall_failures        — query failure memory by SHA-256 signature
 *   3. store_failure          — persist triage result to failure memory
 *   4. check_release_readiness — run coverage + blocker gates
 *   5. get_coverage_report    — fetch coverage report for a ref
 *
 * Integration contract with Apurva's memory layer:
 *   - DB path resolved relative to __dirname in db.js (not process.cwd())
 *   - Signature: SHA-256(test_name + ":" + error_type + ":" + failing_file)
 *   - Signature computed by CALLER (triage subagent), NOT by this server
 *   - Use error_type column (NOT error_class)
 */

'use strict';

const { Server }               = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} = require('@modelcontextprotocol/sdk/types.js');

// Tool handlers
const { runPipeline }           = require('./tools/run_pipeline');
const { recallFailures }        = require('./tools/recall_failures');
const { storeFailure }          = require('./tools/store_failure');
const { checkReleaseReadiness } = require('./tools/check_release_readiness');
const { getCoverageReport }     = require('./tools/get_coverage_report');

// ---------------------------------------------------------------------------
// Tool definitions (JSON Schema for Bob's tool-call interface)
// ---------------------------------------------------------------------------

const TOOLS = [
  {
    name:        'run_pipeline',
    description: 'Fetch or trigger a CI pipeline run by ref (run ID or git ref). Returns the run status and any failure details. Uses demo/fixtures/<ref>.json if available, falls back to GitHub Actions API if CI_API_TOKEN is set.',
    inputSchema: {
      type:       'object',
      properties: {
        ref: {
          type:        'string',
          description: 'Git ref, run ID, or fixture name (e.g. "run-42", "feat/auth")',
        },
      },
      required: ['ref'],
    },
  },
  {
    name:        'recall_failures',
    description: 'Retrieve historical CI failures matching a SHA-256 signature from the failure memory store. Returns up to `limit` matches ordered by most recent first. The signature must be pre-computed: SHA-256(test_name + ":" + error_type + ":" + failing_file).',
    inputSchema: {
      type:       'object',
      properties: {
        signature: {
          type:        'string',
          description: 'SHA-256 hex digest: SHA-256(test_name + ":" + error_type + ":" + failing_file)',
        },
        limit: {
          type:        'integer',
          description: 'Maximum number of historical matches to return (default: 5)',
          default:     5,
        },
      },
      required: ['signature'],
    },
  },
  {
    name:        'store_failure',
    description: 'Persist a CI failure triage result to the failure memory store. The signature must be pre-computed by the caller. Returns the new failure_id and stored_at timestamp.',
    inputSchema: {
      type:       'object',
      properties: {
        signature:        { type: 'string',  description: 'SHA-256(test_name + ":" + error_type + ":" + failing_file) — pre-computed by caller' },
        test_name:        { type: 'string',  description: 'Test function name, e.g. "test_auth_token_expiry"' },
        error_type:       { type: 'string',  description: 'Error class, e.g. "AssertionError", "TimeoutError"' },
        failing_file:     { type: 'string',  description: 'Relative path to the failing test file' },
        action:           { type: 'string',  enum: ['rerun', 'fix', 'revert', 'escalate'], description: 'Recommended action' },
        confidence:       { type: 'string',  enum: ['high', 'medium', 'low'], description: 'Confidence level' },
        confidence_score: { type: 'number',  description: 'Numeric confidence 0.0–1.0', minimum: 0, maximum: 1 },
        run_id:           { type: 'string',  description: 'CI run identifier, e.g. "run-42"' },
        session_id:       { type: 'string',  description: 'Bob session / task ID' },
        failure_message:  { type: 'string',  description: 'First-line error message (≤500 chars)' },
        recommendation:   { type: 'string',  description: 'Human-readable recommendation text' },
        resolution:       { type: 'string',  description: 'How the failure was resolved' },
        resolved:         { type: 'boolean', description: 'true if already resolved', default: false },
      },
      required: ['signature', 'test_name', 'error_type', 'failing_file', 'action', 'confidence'],
    },
  },
  {
    name:        'check_release_readiness',
    description: 'Run release gates for a ref and return PASS, WARNING, or BLOCKER. Checks: coverage threshold (≥80%), open unresolved escalations in failure memory, and valid target environment.',
    inputSchema: {
      type:       'object',
      properties: {
        ref: {
          type:        'string',
          description: 'Git ref or branch name, e.g. "feat/auth"',
        },
        target_env: {
          type:        'string',
          enum:        ['staging', 'dev'],
          description: 'Deployment target environment',
          default:     'staging',
        },
      },
      required: ['ref'],
    },
  },
  {
    name:        'get_coverage_report',
    description: 'Fetch the latest test coverage report for a git ref. Returns total coverage percentage and per-file breakdown. Reads from reports/coverage-<ref>.json.',
    inputSchema: {
      type:       'object',
      properties: {
        ref: {
          type:        'string',
          description: 'Git ref or branch name, e.g. "feat/auth"',
        },
      },
      required: ['ref'],
    },
  },
];

// ---------------------------------------------------------------------------
// Dispatch table (all handlers are async)
// ---------------------------------------------------------------------------

const HANDLERS = {
  run_pipeline:            (args) => Promise.resolve(runPipeline(args)),
  recall_failures:         (args) => recallFailures(args),
  store_failure:           (args) => storeFailure(args),
  check_release_readiness: (args) => checkReleaseReadiness(args),
  get_coverage_report:     (args) => Promise.resolve(getCoverageReport(args)),
};

// ---------------------------------------------------------------------------
// Server setup
// ---------------------------------------------------------------------------

const server = new Server(
  { name: 'ci-intelligence', version: '1.0.0' },
  { capabilities: { tools: {} } },
);

// List tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: TOOLS };
});

// Call tool
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  const handler = HANDLERS[name];
  if (!handler) {
    return {
      content: [{ type: 'text', text: JSON.stringify({ error: `Unknown tool: ${name}` }) }],
      isError: true,
    };
  }

  try {
    const result = await handler(args ?? {});
    return {
      content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
    };
  } catch (err) {
    return {
      content: [{ type: 'text', text: JSON.stringify({ error: err.message }) }],
      isError: true,
    };
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write('[ci-intelligence] MCP server started — waiting for requests\n');
}

main().catch((err) => {
  process.stderr.write(`[ci-intelligence] Fatal: ${err.message}\n`);
  process.exit(1);
});
