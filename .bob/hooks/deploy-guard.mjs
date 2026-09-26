#!/usr/bin/env node
/**
 * .bob/hooks/deploy-guard.mjs
 * ============================
 * PreToolUse hook — fires before execute_command.
 *
 * Blocks dangerous deploy commands unless check_release_readiness returned PASS.
 *
 * Bob passes the pending tool call as JSON on stdin:
 * { "tool_name": "execute_command", "tool_input": { "command": "..." } }
 *
 * Exit codes:
 *   0 = allow the command to proceed
 *   2 = block the command (Bob will surface the stderr message to the user)
 */

import { readFileSync } from 'fs';

// Patterns that are blocked without an explicit release gate pass
const BLOCKED_PATTERNS = [
  /kubectl\s+apply/i,
  /kubectl\s+create/i,
  /kubectl\s+delete/i,
  /helm\s+upgrade/i,
  /helm\s+install/i,
  /git\s+push\s+.*\b(main|staging|production|prod)\b/i,
  /git\s+push\s+--force/i,
  /docker\s+push/i,
  /ibmcloud\s+ce\s+app\s+update/i,
];

// Commands that should always be allowed (monitoring, read-only)
const ALLOWED_PATTERNS = [
  /kubectl\s+get/i,
  /kubectl\s+describe/i,
  /kubectl\s+logs/i,
  /kubectl\s+rollout\s+status/i,
];

let input = '';
process.stdin.setEncoding('utf8');
for await (const chunk of process.stdin) {
  input += chunk;
}

let payload;
try {
  payload = JSON.parse(input);
} catch {
  process.exit(0);
}

const command = payload?.tool_input?.command ?? payload?.command ?? '';

// Allow if it matches a safe read-only pattern
if (ALLOWED_PATTERNS.some(p => p.test(command))) {
  process.exit(0);
}

// Block if it matches a dangerous deploy pattern
const blocked = BLOCKED_PATTERNS.find(p => p.test(command));
if (blocked) {
  process.stderr.write(
    `[deploy-guard] BLOCKED: "${command}"\n` +
    `Reason: Deploy commands require a PASS from check_release_readiness first.\n` +
    `Run: Ask Bob to call check_release_readiness({ ref: "<branch>", target_env: "staging" })\n` +
    `and verify overall == "PASS" before deploying.\n`
  );
  process.exit(2);
}

process.exit(0);
