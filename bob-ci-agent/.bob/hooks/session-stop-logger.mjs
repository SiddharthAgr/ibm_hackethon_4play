#!/usr/bin/env node
/**
 * .bob/hooks/session-stop-logger.mjs
 * ====================================
 * Stop hook — writes one JSON line to memory/sessions.jsonl after each Bob session.
 * Also inserts/updates the sessions table in failures.db via sql.js.
 *
 * Bob passes session metadata as JSON on stdin:
 * { "session_id": "...", "summary": "...", "started_at": "..." }
 *
 * Exit 0 always — logging must never block session end.
 */

import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __dirname = dirname(fileURLToPath(import.meta.url));
const require   = createRequire(import.meta.url);

const REPO_ROOT  = resolve(__dirname, '..', '..');
const DB_PATH    = resolve(REPO_ROOT, 'bob-ci-agent', 'memory', 'failures.db');
const JSONL_PATH = resolve(REPO_ROOT, 'bob-ci-agent', 'memory', 'sessions.jsonl');

let input = '';
process.stdin.setEncoding('utf8');
try {
  for await (const chunk of process.stdin) {
    input += chunk;
  }
} catch {
  process.exit(0);
}

let payload;
try {
  payload = JSON.parse(input);
} catch {
  payload = {};
}

const sessionId = payload?.session_id ?? `session-${Date.now()}`;
const summary   = payload?.summary    ?? 'Session ended';
const startedAt = payload?.started_at ?? null;
const stoppedAt = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');

function inferOutcome(s) {
  if (!s) return 'no_action';
  if (/escalat/i.test(s)) return 'escalated';
  if (/store|stored|recommend/i.test(s)) return 'recommendation_stored';
  return 'no_action';
}

const outcome = payload?.outcome ?? inferOutcome(summary);

const logEntry = {
  session_id:         sessionId,
  outcome,
  summary,
  started_at:         startedAt,
  stopped_at:         stoppedAt,
  failures_processed: payload?.failures_processed ?? 0,
};

// Write JSONL line
try {
  const dir = dirname(JSONL_PATH);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  appendFileSync(JSONL_PATH, JSON.stringify(logEntry) + '\n', 'utf8');
} catch (err) {
  process.stderr.write(`[session-stop-logger] Warning: could not write JSONL: ${err.message}\n`);
}

// Write to SQLite via sql.js (async)
if (existsSync(DB_PATH)) {
  try {
    const initSqlJs = require('sql.js');
    const SQL = await initSqlJs();
    const buf = readFileSync(DB_PATH);
    const db  = new SQL.Database(buf);

    db.run(`
      INSERT OR REPLACE INTO sessions
        (session_id, failures_processed, outcome, summary, started_at, stopped_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `, [
      logEntry.session_id,
      logEntry.failures_processed,
      logEntry.outcome,
      logEntry.summary,
      logEntry.started_at,
      logEntry.stopped_at,
    ]);

    writeFileSync(DB_PATH, Buffer.from(db.export()));
    db.close();
  } catch (err) {
    process.stderr.write(`[session-stop-logger] Warning: could not write to SQLite: ${err.message}\n`);
  }
}

process.stderr.write(`[session-stop-logger] Session ${sessionId} logged — outcome: ${outcome}\n`);
process.exit(0);
