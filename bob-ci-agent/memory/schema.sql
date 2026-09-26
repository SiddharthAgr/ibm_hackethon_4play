-- =============================================================================
-- Failure Memory Store — schema.sql
-- Database: SQLite (memory/failures.db)
-- Used by: mcp/tools/store_failure.js, mcp/tools/recall_failures.js
-- =============================================================================

PRAGMA journal_mode = WAL;   -- safe for concurrent reads during demo
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- failures
-- One row per stored CI failure event. Populated by store_failure, queried
-- by recall_failures.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS failures (
    -- surrogate primary key — MCP layer generates this as 'f-<uuidv4>'
    id                  TEXT PRIMARY KEY,

    -- Stable lookup key: SHA-256(test_name + ":" + error_type + ":" + failing_file)
    -- Computed by the triage subagent BEFORE calling store_failure / recall_failures.
    -- This must be identical across runs to guarantee recall hits the right rows.
    signature           TEXT NOT NULL,

    -- CI run context
    run_id              TEXT,                   -- e.g. "run-42", "gh-run-9876543"
    session_id          TEXT,                   -- Bob session / task ID

    -- Failure identity fields (used for human-readable display in Bob chat)
    test_name           TEXT,                   -- e.g. "test_auth_token_expiry"
    error_type          TEXT,                   -- e.g. "AssertionError", "ImportError"
    failing_file        TEXT,                   -- e.g. "tests/test_auth.py"
    failure_message     TEXT,                   -- full first-line error message (≤500 chars)

    -- Triage outcome
    -- action: one of  'rerun' | 'fix' | 'revert' | 'escalate'
    action              TEXT CHECK(action IN ('rerun','fix','revert','escalate')),
    recommendation      TEXT,                   -- human-readable recommendation text
    -- confidence: one of  'high' | 'medium' | 'low'
    confidence          TEXT CHECK(confidence IN ('high','medium','low')),
    confidence_score    REAL CHECK(confidence_score BETWEEN 0.0 AND 1.0),

    -- Resolution tracking (filled by the Stop hook once a session outcome is known)
    resolution          TEXT,                   -- e.g. "reverted commit abc123", "added mock for redis"
    resolved            INTEGER DEFAULT 0 CHECK(resolved IN (0, 1)),  -- boolean

    -- Audit
    stored_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT
);

-- Primary recall index — all recall_failures queries hit this
CREATE INDEX IF NOT EXISTS idx_signature
    ON failures (signature);

-- Secondary index for chronological scans (session start injection of last 5)
CREATE INDEX IF NOT EXISTS idx_stored_at
    ON failures (stored_at DESC);

-- ---------------------------------------------------------------------------
-- sessions
-- One row per Bob session. Written by the Stop hook via session-stop-logger.mjs
-- and mirrored to memory/sessions.jsonl for quick human inspection.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id          TEXT PRIMARY KEY,
    failures_processed  INTEGER DEFAULT 0,
    -- outcome: one of  'recommendation_stored' | 'escalated' | 'no_action'
    outcome             TEXT,
    summary             TEXT,
    started_at          TEXT,
    stopped_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ---------------------------------------------------------------------------
-- schema_migrations
-- Simple version tracking so db.js can apply migrations idempotently.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version             INTEGER PRIMARY KEY,
    applied_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);
