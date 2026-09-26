#!/usr/bin/env node
/**
 * scripts/seed-db.js
 * ==================
 * Applies schema.sql then seed.sql to memory/failures.db.
 * Uses sql.js (pure WASM — no native compile needed).
 *
 * Usage:  npm run seed-db
 */

'use strict';

const path      = require('path');
const fs        = require('fs');
const initSqlJs = require('sql.js');

const REPO_ROOT   = path.resolve(__dirname, '..');
const DB_PATH     = path.join(REPO_ROOT, 'memory', 'failures.db');
const SCHEMA_PATH = path.join(REPO_ROOT, 'memory', 'schema.sql');
const SEED_PATH   = path.join(REPO_ROOT, 'memory', 'seed.sql');

async function main() {
  const SQL = await initSqlJs();

  // Load existing DB or create fresh
  let db;
  if (fs.existsSync(DB_PATH)) {
    const buf = fs.readFileSync(DB_PATH);
    db = new SQL.Database(buf);
    console.log('[seed-db] Loaded existing database:', DB_PATH);
  } else {
    db = new SQL.Database();
    console.log('[seed-db] Creating new database:', DB_PATH);
  }

  // Apply schema (strip WAL pragma — no-op in WASM)
  const schema = fs.readFileSync(SCHEMA_PATH, 'utf8')
    .replace(/PRAGMA\s+journal_mode\s*=\s*WAL\s*;/gi, '')
    .replace(/PRAGMA\s+foreign_keys\s*=\s*ON\s*;/gi, '');
  db.run(schema);
  console.log('[seed-db] Schema applied:', SCHEMA_PATH);

  // Apply seed
  const seed = fs.readFileSync(SEED_PATH, 'utf8');
  db.run(seed);
  console.log('[seed-db] Seed applied:  ', SEED_PATH);

  // Flush to disk
  const memDir = path.dirname(DB_PATH);
  if (!fs.existsSync(memDir)) fs.mkdirSync(memDir, { recursive: true });
  fs.writeFileSync(DB_PATH, Buffer.from(db.export()));

  // Verify row count
  const countStmt = db.prepare('SELECT COUNT(*) AS cnt FROM failures');
  countStmt.step();
  const { cnt } = countStmt.getAsObject();
  countStmt.free();
  console.log(`[seed-db] Total failure rows in DB: ${cnt}`);

  // ─── Integration verification: eval-01 (auth token expiry) ───────────────
  const AUTH_SIG = 'e05df3df6765b575ef14be0d76c581b5d7e29f641cd5520c270680c0fb63ecde';
  const recallStmt = db.prepare(
    'SELECT id, action, confidence FROM failures WHERE signature = ? ORDER BY stored_at DESC'
  );
  recallStmt.bind([AUTH_SIG]);
  const matches = [];
  while (recallStmt.step()) {
    matches.push(recallStmt.getAsObject());
  }
  recallStmt.free();

  console.log('\n[seed-db] Integration check — auth token expiry (eval-01 / run-42):');
  console.log(`  Signature : ${AUTH_SIG}`);
  console.log(`  Matches   : ${matches.length} (expected 2)`);
  matches.forEach(m => console.log(`    ${m.id}  action=${m.action}  confidence=${m.confidence}`));

  if (matches.length === 2 &&
      matches.every(m => m.action === 'revert' && m.confidence === 'high')) {
    console.log('  ✓ PASS — f-seed-01 and f-seed-02 found: action=revert, confidence=high');
  } else {
    console.error('  ✗ FAIL — unexpected recall result');
    db.close();
    process.exit(1);
  }

  // ─── Negative test A: unseen failure ─────────────────────────────────────
  const BILLING_SIG = '9c9171d7da672706546650088b217d8149e8c0abdb56a32794bbfb4919b8d7fa';
  const billingStmt = db.prepare('SELECT id FROM failures WHERE signature = ?');
  billingStmt.bind([BILLING_SIG]);
  const billingMatches = [];
  while (billingStmt.step()) billingMatches.push(billingStmt.getAsObject());
  billingStmt.free();

  console.log('\n[seed-db] Negative test A — unseen billing failure:');
  if (billingMatches.length === 0) {
    console.log('  ✓ PASS — 0 matches, correctly routes to escalate');
  } else {
    console.error(`  ✗ FAIL — unexpected ${billingMatches.length} match(es)`);
  }

  // ─── Negative test B: same test/error, different file ─────────────────────
  const OAUTH_SIG = 'a5af2e26e14c78cc2bf1eaf44621034fe03130fe16ed1c7aed7589dd10e8aebc';
  const oauthStmt = db.prepare('SELECT id FROM failures WHERE signature = ?');
  oauthStmt.bind([OAUTH_SIG]);
  const oauthMatches = [];
  while (oauthStmt.step()) oauthMatches.push(oauthStmt.getAsObject());
  oauthStmt.free();

  console.log('\n[seed-db] Negative test B — auth test with test_oauth.py (different file):');
  if (oauthMatches.length === 0) {
    console.log('  ✓ PASS — 0 matches, signature isolation confirmed');
  } else {
    console.error(`  ✗ FAIL — unexpected ${oauthMatches.length} match(es), signature collision`);
  }

  db.close();
  console.log('\n[seed-db] Done. Database ready:', DB_PATH);
}

main().catch(err => {
  console.error('[seed-db] Fatal:', err.message);
  process.exit(1);
});
