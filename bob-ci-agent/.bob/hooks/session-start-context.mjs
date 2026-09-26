#!/usr/bin/env node
/**
 * .bob/hooks/session-start-context.mjs
 * ======================================
 * SessionStart hook — injects the 5 most recent CI failures from memory
 * into Bob's context at the start of each session.
 *
 * Exit 0 always. Writes context JSON to stdout if DB is available.
 */

import { existsSync, readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __dirname = dirname(fileURLToPath(import.meta.url));
const require   = createRequire(import.meta.url);

const REPO_ROOT = resolve(__dirname, '..', '..');
const DB_PATH   = resolve(REPO_ROOT, 'bob-ci-agent', 'memory', 'failures.db');

if (!existsSync(DB_PATH)) {
  process.exit(0);
}

try {
  const initSqlJs = require('sql.js');
  const SQL    = await initSqlJs();
  const buf    = readFileSync(DB_PATH);
  const db     = new SQL.Database(buf);

  const stmt = db.prepare(`
    SELECT signature, test_name, error_type, action, confidence, stored_at
    FROM failures
    ORDER BY stored_at DESC
    LIMIT 5
  `);

  const recent = [];
  while (stmt.step()) {
    recent.push(stmt.getAsObject());
  }
  stmt.free();
  db.close();

  if (recent.length === 0) {
    process.exit(0);
  }

  const rows = recent.map(r =>
    `- \`${r.test_name}\` (\`${r.error_type}\`) → **${r.action}** [${r.confidence}] — ${r.stored_at}`
  );

  const contextMsg = {
    type: 'context',
    content: [
      '**Failure Memory — Recent CI Failures (last 5):**',
      '',
      ...rows,
      '',
      'Use `recall_failures({ signature })` to look up full history for any failure.',
    ].join('\n'),
  };

  process.stdout.write(JSON.stringify(contextMsg) + '\n');
} catch (err) {
  process.stderr.write(`[session-start-context] Warning: ${err.message}\n`);
}

process.exit(0);
