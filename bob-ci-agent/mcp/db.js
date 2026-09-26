/**
 * mcp/db.js
 * =========
 * SQLite connection using sql.js (pure WASM — no native compile required).
 *
 * sql.js provides a synchronous, in-memory SQLite database backed by WASM.
 * We load the database file from disk at startup and flush changes back on
 * every write via db.export().
 *
 * Database path:
 *   <repo>/bob-ci-agent/memory/failures.db
 *   Resolved relative to __dirname so the path is correct regardless of cwd.
 *
 * Usage:
 *   const { db, flushDb } = require('./db');
 *   const stmt = db.prepare('SELECT ...');
 *   const rows = stmt.getAsObject({}, ...);
 *   // After mutations: flushDb()  ← called automatically by write helpers below
 */

'use strict';

const path      = require('path');
const fs        = require('fs');
const initSqlJs = require('sql.js');

// Paths
const DB_PATH     = path.resolve(__dirname, '..', 'memory', 'failures.db');
const SCHEMA_PATH = path.resolve(__dirname, '..', 'memory', 'schema.sql');
const MEM_DIR     = path.dirname(DB_PATH);

// Ensure memory/ directory exists
if (!fs.existsSync(MEM_DIR)) {
  fs.mkdirSync(MEM_DIR, { recursive: true });
}

// ─── sql.js wrapper ────────────────────────────────────────────────────────
// sql.js is async to initialise (loads WASM) but synchronous after that.
// We expose a lazy-init singleton: callers await getDb() once, then use it.

let _db   = null;
let _SQL  = null;
let _init = null;   // the promise that resolves the singleton

async function getDb() {
  if (_db) return _db;
  if (_init) return _init;

  _init = (async () => {
    // locateFile tells sql.js to look for the WASM binary next to the JS file
    _SQL = await initSqlJs({
      locateFile: (file) => require('path').join(require.resolve('sql.js'), '..', file),
    });

    if (fs.existsSync(DB_PATH)) {
      const buf = fs.readFileSync(DB_PATH);
      _db = new _SQL.Database(buf);
    } else {
      _db = new _SQL.Database();
    }

    // Apply schema idempotently (creates tables/indexes if missing)
    if (fs.existsSync(SCHEMA_PATH)) {
      const schemaSql = fs.readFileSync(SCHEMA_PATH, 'utf8');
      // sql.js does not support PRAGMA inside the same exec block for WAL on WASM
      // Strip WAL pragma (no-op in WASM) and apply the rest
      const cleanedSchema = schemaSql
        .replace(/PRAGMA\s+journal_mode\s*=\s*WAL\s*;/gi, '')
        .replace(/PRAGMA\s+foreign_keys\s*=\s*ON\s*;/gi, '');
      _db.run(cleanedSchema);
    }

    return _db;
  })();

  return _init;
}

/**
 * Persist the in-memory database back to disk.
 * Must be called after every INSERT / UPDATE / DELETE.
 */
function flushDb() {
  if (!_db) return;
  const data = _db.export();
  fs.writeFileSync(DB_PATH, Buffer.from(data));
}

/**
 * Execute a SELECT and return all rows as plain objects.
 * @param {string} sql
 * @param {any[]} params - positional parameters (sql.js uses [val, val, ...])
 * @returns {object[]}
 */
function queryAll(sql, params = []) {
  const stmt   = _db.prepare(sql);
  const rows   = [];
  stmt.bind(params);
  while (stmt.step()) {
    rows.push(stmt.getAsObject());
  }
  stmt.free();
  return rows;
}

/**
 * Execute a SELECT and return the first row, or null.
 */
function queryOne(sql, params = []) {
  const rows = queryAll(sql, params);
  return rows.length > 0 ? rows[0] : null;
}

/**
 * Execute an INSERT / UPDATE / DELETE (no return value).
 * Automatically flushes to disk.
 */
function run(sql, params = []) {
  _db.run(sql, params);
  flushDb();
}

module.exports = { getDb, flushDb, queryAll, queryOne, run };
