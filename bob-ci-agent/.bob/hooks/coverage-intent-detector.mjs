#!/usr/bin/env node
/**
 * .bob/hooks/coverage-intent-detector.mjs
 * =========================================
 * UserPromptSubmit hook — detects coverage-related prompts and injects
 * a reminder to use the coverage subagent + MCP get_coverage_report tool.
 *
 * Bob passes the user prompt JSON on stdin:
 * { "prompt": "..." }
 *
 * If coverage intent is detected, writes a context injection to stdout.
 * Exit 0 always — this hook never blocks.
 */

const COVERAGE_PATTERNS = [
  /\bcoverage\b/i,
  /\buncovered\b/i,
  /\btest\s+coverage\b/i,
  /\bcoverage\s+report\b/i,
  /\bcoverage\s+threshold\b/i,
  /\bcoverage\s+gate\b/i,
  /\b(68|80)\s*%/,
  /\bci_client\.py\b/i,
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

const detected = COVERAGE_PATTERNS.some(p => p.test(prompt));
if (!detected) {
  process.exit(0);
}

const contextMsg = {
  type: 'context',
  content: [
    '**Coverage context detected.**',
    '',
    'Available MCP tools for coverage analysis:',
    '- `get_coverage_report({ ref: "feat/auth" })` — fetch per-file coverage breakdown',
    '- `check_release_readiness({ ref: "feat/auth", target_env: "staging" })` — run all gates including 80% threshold',
    '',
    'Seeded report: `reports/coverage-feat-auth.json` (total: 68% — below 80% threshold → BLOCKER)',
  ].join('\n'),
};

process.stdout.write(JSON.stringify(contextMsg) + '\n');
process.exit(0);
