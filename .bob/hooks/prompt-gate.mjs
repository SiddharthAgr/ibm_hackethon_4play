#!/usr/bin/env node
/**
 * .bob/hooks/prompt-gate.mjs
 * ===========================
 * UserPromptSubmit hook — safety gate for prompt patterns that suggest
 * destructive operations. Blocks prompts that try to bypass the deploy guard
 * or request direct production mutations.
 *
 * Bob passes the user prompt JSON on stdin:
 * { "prompt": "..." }
 *
 * Exit codes:
 *   0 = allow the prompt through
 *   2 = block the prompt (Bob will surface the message to the user)
 */

const BLOCKED_PROMPT_PATTERNS = [
  { pattern: /deploy\s+to\s+prod(uction)?/i,    reason: 'Direct production deploys are not permitted. Use the triage + release readiness flow.' },
  { pattern: /skip\s+the\s+(deploy\s+)?guard/i, reason: 'The deploy guard cannot be bypassed. Run check_release_readiness first.' },
  { pattern: /ignore\s+(coverage|tests)/i,       reason: 'Coverage and test gates are required. Cannot ignore them.' },
  { pattern: /force\s+push\s+to\s+main/i,        reason: 'Force pushing to main is blocked. Use a PR.' },
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

const prompt = payload?.prompt ?? payload?.message ?? '';

const blocked = BLOCKED_PROMPT_PATTERNS.find(({ pattern }) => pattern.test(prompt));
if (blocked) {
  process.stderr.write(`[prompt-gate] BLOCKED: ${blocked.reason}\n`);
  process.exit(2);
}

process.exit(0);
