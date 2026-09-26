# Failure Memory Store

> **Owner:** Apurva (memory + evaluation)
> **Consumers:** `mcp/tools/store_failure.js`, `mcp/tools/recall_failures.js` (Node.js MCP layer — teammate's scope)

---

## Directory layout

```
memory/
├── schema.sql        ← run once on first startup to create tables
├── seed.sql          ← 10 seeded historical failures for demo + evaluation
├── failures.db       ← SQLite runtime database (gitignored)
└── sessions.jsonl    ← one JSON line per Bob session (written by Stop hook, gitignored)
```

`failures.db` and `sessions.jsonl` are generated at runtime and are not committed.
Seed the database before the first demo run:

```bash
# Option A — via npm script (recommended)
npm run seed-db

# Option B — raw SQLite
sqlite3 memory/failures.db < memory/schema.sql
sqlite3 memory/failures.db < memory/seed.sql
```

---

## Schema

### `failures` table

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | MCP-generated `f-<uuidv4>` |
| `signature` | TEXT NOT NULL | `SHA-256(test_name + ":" + error_type + ":" + failing_file)` — the primary recall key |
| `run_id` | TEXT | CI run identifier, e.g. `run-42` |
| `session_id` | TEXT | Bob task/session ID |
| `test_name` | TEXT | e.g. `test_auth_token_expiry` |
| `error_type` | TEXT | e.g. `AssertionError`, `ImportError`, `TimeoutError` |
| `failing_file` | TEXT | Relative path to the test file |
| `failure_message` | TEXT | First-line error message (≤500 chars) |
| `action` | TEXT | One of `rerun`, `fix`, `revert`, `escalate` |
| `recommendation` | TEXT | Human-readable recommendation string |
| `confidence` | TEXT | One of `high`, `medium`, `low` |
| `confidence_score` | REAL | 0.0–1.0 (used by evaluation benchmark) |
| `resolution` | TEXT | How the failure was actually resolved (filled by Stop hook) |
| `resolved` | INTEGER | `1` if resolved, `0` if open |
| `stored_at` | TEXT | ISO-8601 UTC timestamp (auto-set on INSERT) |
| `updated_at` | TEXT | ISO-8601 UTC timestamp (set on UPDATE) |

### `sessions` table

Written by `session-stop-logger.mjs` (Stop hook). Each row and each `.jsonl` line record one Bob session outcome.

| Column | Type | Description |
|---|---|---|
| `session_id` | TEXT PK | Bob task ID |
| `failures_processed` | INTEGER | Count of failures triaged in the session |
| `outcome` | TEXT | `recommendation_stored` \| `escalated` \| `no_action` |
| `summary` | TEXT | Free-text summary |
| `started_at` | TEXT | Session start timestamp |
| `stopped_at` | TEXT | Session end timestamp (auto-set) |

---

## Signature computation

The signature is computed **by the triage subagent** before calling either MCP tool:

```
signature = SHA-256( test_name + ":" + error_type + ":" + failing_file )
```

Properties:
- **Stable across runs** — does not depend on line numbers, timestamps, or run IDs.
- **Deterministic** — two failures with identical test name, error class, and file always produce the same signature.
- **Collision-safe for demo scale** — 256-bit hash space with 10 seed rows has negligible collision probability.

Node.js snippet (for reference in `store_failure.js` / `recall_failures.js`):

```js
const crypto = require('crypto');

function computeSignature(testName, errorType, failingFile) {
  return crypto
    .createHash('sha256')
    .update(`${testName}:${errorType}:${failingFile}`)
    .digest('hex');
}
```

---

## Interface contract

### `store_failure`

Stores one failure event (after triage, before or after resolution).

**Input JSON** (received by the MCP tool from Bob/triage-subagent):

```json
{
  "run_id":          "run-42",
  "session_id":      "task-abc123",
  "signature":       "a3f1c2d4e5b6a7f8...",
  "test_name":       "test_auth_token_expiry",
  "error_type":      "AssertionError",
  "failing_file":    "tests/test_auth.py",
  "failure_message": "AssertionError: expected 401, got 500",
  "action":          "revert",
  "recommendation":  "Revert commit d4f9a12 — matches 2 prior failures",
  "confidence":      "high",
  "confidence_score": 0.92,
  "resolution":      null,
  "resolved":        false
}
```

All fields except `run_id`, `session_id`, `resolution`, `resolved` are required.
`signature` **must be pre-computed** by the caller — this layer does not hash.

**Output JSON** (returned to Bob by the MCP tool):

```json
{
  "stored":     true,
  "failure_id": "f-9a3b1c2d-4e5f-6789-abcd-ef0123456789",
  "stored_at":  "2025-09-27T14:30:00Z"
}
```

On error:

```json
{
  "stored":  false,
  "error":   "SQLITE_CONSTRAINT: signature cannot be null"
}
```

**SQL executed** (parameterised):

```sql
INSERT INTO failures (
    id, signature, run_id, session_id,
    test_name, error_type, failing_file, failure_message,
    action, recommendation, confidence, confidence_score,
    resolution, resolved
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

---

### `recall_failures`

Retrieves historical failures matching a given signature, most recent first.

**Input JSON**:

```json
{
  "signature": "a3f1c2d4e5b6a7f8...",
  "limit":     5
}
```

`limit` is optional; defaults to `5`.

**Output JSON**:

```json
{
  "matches": [
    {
      "failure_id":       "f-seed-01",
      "test_name":        "test_auth_token_expiry",
      "error_type":       "AssertionError",
      "failing_file":     "tests/test_auth.py",
      "action":           "revert",
      "recommendation":   "Revert commit d4f9a12 — JWT middleware change ...",
      "confidence":       "high",
      "confidence_score": 0.92,
      "resolution":       "Reverted commit d4f9a12 on feat/auth branch.",
      "resolved":         true,
      "stored_at":        "2025-09-20T08:14:00Z"
    },
    {
      "failure_id":       "f-seed-02",
      "action":           "revert",
      "confidence":       "high",
      "confidence_score": 0.88,
      "stored_at":        "2025-09-17T11:45:00Z"
    }
  ],
  "total_found": 2
}
```

When no matches exist:

```json
{
  "matches":     [],
  "total_found": 0
}
```

**SQL executed** (parameterised):

```sql
SELECT
    id            AS failure_id,
    test_name,
    error_type,
    failing_file,
    action,
    recommendation,
    confidence,
    confidence_score,
    resolution,
    resolved,
    stored_at
FROM failures
WHERE signature = ?
ORDER BY stored_at DESC
LIMIT ?;
```

---

## How the triage subagent uses these two calls

```
1. Compute signature = SHA-256(test_name + ":" + error_type + ":" + failing_file)
2. Call  recall_failures({ signature, limit: 5 })
3. If total_found >= 2 AND all matches have the same action:
       → confidence = "high",  action = matches[0].action
4. If total_found == 1:
       → confidence = "medium", action = matches[0].action
5. If total_found == 0:
       → confidence = "low",   action = "escalate"
6. Call  store_failure({ ..., action, confidence, confidence_score })
7. Return structured recommendation to Bob
```

The memory layer is **stateless** — it never computes signatures, never decides confidence, and never chooses an action. All intelligence sits in the triage subagent. This keeps the SQL layer simple and the MCP tools fast.

---

## Indexes

| Index | Column(s) | Purpose |
|---|---|---|
| `idx_signature` | `signature` | Fast recall lookup (primary query path) |
| `idx_stored_at` | `stored_at DESC` | Session-start context injection (last 5 failures) |

Both indexes are created by `schema.sql` and survive across re-seeds.
