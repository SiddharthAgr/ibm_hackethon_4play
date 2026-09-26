#!/usr/bin/env node
/**
 * .bob/hooks/triage-trigger.mjs
 * ==============================
 * PostToolUse hook — fires after mcp__ci-intelligence__run_pipeline completes.
 *
 * Bob passes the tool result as JSON on stdin:
 * {
 *   "tool_name": "mcp__ci-intelligence__run_pipeline",
 *   "tool_input": { "ref": "run-42" },
 *   "tool_result": { ... pipeline payload ... }
 * }
 *
 * This hook injects context into Bob's next turn, prompting the triage subagent.
 * Exit 0 = proceed normally; the JSON written to stdout is injected as context.
 */

import { readFileSync } from 'fs';

let input = '';
process.stdin.setEncoding('utf8');
for await (const chunk of process.stdin) {
  input += chunk;
}

let payload;
try {
  payload = JSON.parse(input);
} catch {
  process.exit(0); // Not JSON — ignore silently
}

const result = payload?.tool_result ?? payload?.output ?? {};

// Only inject if the pipeline run has failures
const failures = result?.failures ?? [];
if (!Array.isArray(failures) || failures.length === 0) {
  // No failures: let Bob proceed without triage injection
  process.exit(0);
}

// Inject a context message to trigger the triage subagent
const contextMsg = {
  type: 'context',
  content: [
    `**CI Pipeline Failure Detected** — run_id: \`${result.run_id ?? 'unknown'}\``,
    '',
    `Branch: \`${result.ref ?? 'unknown'}\` | Status: \`${result.status}\``,
    '',
    '**Failures:**',
    ...failures.map(f =>
      `- \`${f.test_name}\` (\`${f.error_type}\`) in \`${f.failing_file}\``
    ),
    '',
    '**Next step:** Spawn the triage subagent. For each failure:',
    '1. Compute SHA-256(test_name + ":" + error_type + ":" + failing_file)',
    '2. Call `recall_failures` with the signature',
    '3. Determine action (revert/rerun/fix/escalate) and confidence',
    '4. Call `store_failure` with the recommendation',
  ].join('\n'),
};

process.stdout.write(JSON.stringify(contextMsg) + '\n');
process.exit(0);
