# Bob-Centric CI/CD Intelligence Agent — Hackathon Plan

> **Context Intake Summary**
> | Field | Value |
> |---|---|
> | Team | 3–4 people — Python, Node.js, IBM Cloud/Kubernetes |
> | Repo | Greenfield — designed from scratch |
> | Access | IBM Bob 2.0 · watsonx Orchestrate · IBM Cloud (IKS / Code Engine) |
> | Hours remaining | 48 (full window) |
> | Judging weights | Innovation 30% · Technical Implementation 30% · Business Value 20% · Demo Quality 20% |
> | Demo language | Python (primary services) + Node.js (MCP server) **[ASSUMED: Python preferred; last intake field unanswered]** |

---

## 1. Developer Problem Definition

**Persona:** Senior software engineer at a mid-size product company. Responsible for merging PRs, watching pipelines, and deciding whether a build failure is a known flake or a real regression.

**Current workflow:**
1. Open CI dashboard → scan 10–40 failed test lines manually.
2. Search Slack/Confluence for "has this failed before?"
3. Decide: re-run, fix forward, or revert.
4. If fixing, context-switch into the IDE, reproduce locally, patch, push.
5. Repeat for every PR.

**Pain:**
- The same five failure signatures recur every sprint; engineers hand-diagnose them every time.
- No structured memory of past failures means tribal knowledge is lost at team churn.
- Deployment gates are informal ("looks green enough"); rollbacks happen reactively.

**Success metrics (how to measure, not a claimed result):**
- Time from pipeline failure to actionable recommendation — measured via timestamped webhook receipt vs. Bob `Stop` hook timestamp.
- Percentage of failures auto-classified vs. escalated — measured by counting `classified: true` vs. `escalated: true` in the failure memory store.
- Demo: one full failure→triage→recommendation cycle visible end-to-end in under 90 seconds.

---

## 2. Bob-Centric Solution Design

**Capability map:**

| User intent | Bob capability used |
|---|---|
| "Analyse this test failure" | Bob agent mode + subagent for isolated investigation |
| Automatic failure intake | `PostToolUse` hook fires after MCP `run_pipeline` tool returns a failure payload |
| Structured triage context | `SessionStart` hook injects failure memory into every new conversation |
| Coverage gap detection | `UserPromptSubmit` hook classifies prompt intent; routes to Coverage subagent |
| Safe deployment gate | `PreToolUse` hook on `execute_command` blocks `kubectl apply` unless release checks pass |
| Memory write/read | MCP server exposes `store_failure` and `recall_failures` tools |
| Failure pattern replay | Bob reads stored JSON signature and runs the investigation sequence again |

**ASCII architecture:**

```
Developer / CI webhook
        |
        v
  [MCP Server: ci-intelligence]  (Node.js, STDIO)
        |    |    |
        |    |    +-- recall_failures(signature) -> failure memory store (JSON file / SQLite)
        |    +------- store_failure(payload)     -> failure memory store
        +------------ run_pipeline(ref)           -> CI API (GitHub Actions / Tekton)
                      get_coverage_report(ref)    -> Coverage API
                      check_release_readiness()   -> Checks runner

        ^
        | MCP tool results feed Bob context
        |
  [IBM Bob 2.0]
    Hooks:
      SessionStart  -> inject last 5 failure signatures into context
      PostToolUse   -> after run_pipeline: trigger Triage subagent if status=failed
      PreToolUse    -> before execute_command matching 'kubectl apply': block if release gate open
      Stop          -> write session outcome to memory store

    Subagents:
      coverage-subagent  (explore type) -> reads coverage report, returns gap list
      triage-subagent    (general type) -> runs investigation sequence, returns recommendation

        |
        v
  [watsonx Orchestrate]  -- Justified inclusion: see Section 13
  Human-facing decision flow: receives Bob's recommendation, routes to on-call engineer via chat
```

---

## 3. Working Prototype Definition

**MUST (demo will fail without these):**
- MCP server with four tools: `run_pipeline`, `store_failure`, `recall_failures`, `check_release_readiness`
- Bob `PostToolUse` hook that fires after `run_pipeline` returns `status: "failed"` and triggers the triage subagent
- Bob `PreToolUse` hook that blocks `kubectl apply` when `check_release_readiness` returns blockers
- Failure memory store (SQLite via `better-sqlite3` or a JSON file) with at least 3 seeded historical failures
- A `SessionStart` hook that injects the last 5 failure signatures as context

**SHOULD (strengthens demo and judging scores):**
- Coverage subagent that reads a seeded `coverage.json` and returns a gap summary
- `Stop` hook that writes the session recommendation to the memory store
- watsonx Orchestrate skill that receives the triage recommendation and sends a formatted Slack notification
- Bob slash command `/triage <run-id>` for one-shot demo convenience

**OPTIONAL (only if time permits after MUST is solid):**
- Deploy MCP server to IBM Code Engine (remote Streamable HTTP transport)
- Live GitHub Actions webhook (instead of manual trigger)
- Metrics dashboard (count of auto-classified vs. escalated)

**Data flow:**

```
1. Developer runs /triage <run-id>  (or PostToolUse hook fires automatically)
2. Bob calls MCP run_pipeline(ref=run-id)  -> returns { status:"failed", failures:[...] }
3. Bob spawns triage-subagent with failure payload
4. triage-subagent calls recall_failures(signature) -> returns similar past failures
5. triage-subagent returns: { recommendation, confidence, action: "rerun|fix|revert" }
6. Bob calls store_failure(payload + recommendation) -> persisted
7. Stop hook writes session summary to memory
8. (SHOULD) Orchestrate skill is called with recommendation -> Slack DM to on-call
```

---

## 4. Business Value Experiment

**Before state (baseline — to be measured during demo setup):**
- Manually seed 10 simulated past failures into the memory store.
- Record: time for a human to read the raw CI log and decide an action (ask a team member to time themselves — target: 3–8 minutes per failure).

**After state (Bob-assisted):**
- Run the same 10 failures through the triage subagent.
- Record: time from `run_pipeline` call to displayed recommendation (measurable from hook timestamps in the session log).

**What to present to judges:**
- A before/after table with measured seconds (not invented numbers — fill in at demo time).
- The failure memory hit-rate: `matched_past_failures / total_failures` from the demo run.
- Evidence that every autonomous action produced a visible artifact (stored JSON, displayed recommendation, blocked deploy).

> **No invented performance numbers appear in this plan.** The experiment design is defined; results are filled at demo time.

---

## 5. 3-Minute Demo Script

| Time | Action | What judges see |
|---|---|---|
| 0:00–0:15 | Show the empty-state terminal, repo structure, and `.bob/` config | Bob is configured; MCP server is running |
| 0:15–0:30 | Type `/triage run-42` in Bob chat | Bob calls `run_pipeline`; failure payload appears |
| 0:30–0:55 | Bob automatically spawns triage-subagent (visible in transcript) | Subagent calls `recall_failures`; similar past failure shown |
| 0:55–1:20 | Subagent returns recommendation: "Revert commit abc123 — matches 3 prior failures" | Structured recommendation card in Bob chat |
| 1:20–1:35 | Developer types "deploy the fix" — Bob calls `execute_command kubectl apply` | `PreToolUse` hook fires; deploy is BLOCKED — release gate open |
| 1:35–1:50 | Bob calls `check_release_readiness`; shows blockers | Blocker list visible; Bob explains why deploy was stopped |
| 1:50–2:10 | Show failure memory store (SQLite or JSON file) populated with this session | Persistent evidence artifact |
| 2:10–2:30 | (SHOULD) Show watsonx Orchestrate Slack notification delivered to on-call | End-to-end human notification |
| 2:30–3:00 | Q&A setup: show `.bob/settings.json` hooks, MCP config, subagent rules | Config is real, not simulated |

**Fallback recordings for risky parts:**
- Triage subagent call: pre-recorded screen capture of a successful run stored as `demo/fallback-triage.mp4`.
- Orchestrate Slack notification: screenshot stored as `demo/fallback-slack.png` if live instance is unavailable.
- `run_pipeline` tool: if CI API is down, the MCP tool returns a hardcoded fixture from `demo/fixtures/run-42.json`.

---

## 6. Bob Evidence Strategy

- [ ] Screenshot of `.bob/settings.json` showing all four hooks configured with correct event names and matchers.
- [ ] Screenshot of `.bob/mcp.json` showing the `ci-intelligence` server registration.
- [ ] Screenshot of `AGENTS.md` / `.bob/rules/` files loaded in context (use `/memory show`).
- [ ] Session transcript showing `PostToolUse` hook firing after `run_pipeline`.
- [ ] Session transcript showing `PreToolUse` hook blocking `kubectl apply`.
- [ ] Populated failure memory store (`memory/failures.db` or `memory/failures.json`) committed to repo.
- [ ] README section: "How Bob is used" with annotated screenshots.
- [ ] Subagent invocation visible in the Bob transcript (tool call + summary returned).
- [ ] `Stop` hook output: last session outcome written to `memory/sessions.jsonl`.

---

## 7. Prompt Gate Design

**Task-contract schema** — every Bob session that touches a deployment MUST include this context (injected by `SessionStart` hook):

```json
{
  "contract_version": "1.0",
  "allowed_deploy_targets": ["staging", "dev"],
  "blocked_commands": ["kubectl apply.*production", "helm upgrade.*prod"],
  "require_release_check_before_deploy": true,
  "failure_memory_path": "memory/failures.db"
}
```

**Hook/service architecture for the gate:**

```
UserPromptSubmit hook
  -> reads prompt text
  -> if prompt matches /deploy|release|rollout/i
     -> runs .bob/hooks/prompt-gate.mjs
     -> injects: "Before any deploy, call check_release_readiness. Contract requires PASS."

PreToolUse hook (matcher: ^execute_command$)
  -> runs .bob/hooks/deploy-guard.mjs
  -> parses tool_input.command
  -> if command matches blocked_commands pattern:
       -> exit 2 (blocks tool call)
       -> stderr: "Blocked: deploy to production requires manual approval outside Bob"
```

The `deploy-guard.mjs` script reads the contract from `.bob/rules/deploy-contract.json` at runtime — it does not hard-code the block pattern, making it updatable without redeploying Bob.

---

## 8. Trigger 1 — Coverage Subagent

**Exact hook:**

```json
"UserPromptSubmit": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "node .bob/hooks/coverage-intent-detector.mjs",
        "timeout": 5
      }
    ]
  }
]
```

**Matcher:** none (fires on every prompt; the script self-filters).

**Script behavior (`coverage-intent-detector.mjs`):**
- Reads `prompt` from stdin JSON.
- If prompt matches `/coverage|uncovered|test gap/i`, writes to stdout:
  ```
  Coverage analysis requested. Bob will spawn the coverage subagent using get_coverage_report.
  ```
- This stdout is added to model context by Bob (SessionStart/UserPromptSubmit stdout contract).
- Bob then calls `get_coverage_report` MCP tool and spawns the coverage subagent.

**Coverage subagent workflow:**
1. Receives: `{ ref, coverage_report_json }`.
2. Reads the coverage report (explore type — read-only).
3. Returns: `{ uncovered_files: [...], lowest_coverage_modules: [...], suggested_test_targets: [...] }`.
4. Bob displays the gap list and optionally generates test stubs.

**Evidence produced:** Coverage gap report displayed in chat + optionally written to `reports/coverage-gaps-<timestamp>.json`.

---

## 9. Trigger 2 — Triage Subagent

**Failure schema (what `run_pipeline` returns on failure):**

```json
{
  "run_id": "run-42",
  "ref": "feat/auth",
  "status": "failed",
  "failures": [
    {
      "test": "test_auth_token_expiry",
      "error": "AssertionError: expected 401, got 500",
      "file": "tests/test_auth.py",
      "line": 88,
      "duration_ms": 1203
    }
  ],
  "triggered_at": "2025-01-01T10:00:00Z"
}
```

**Trigger mechanism:**

```json
"PostToolUse": [
  {
    "matcher": "^mcp__ci-intelligence__run_pipeline$",
    "hooks": [
      {
        "type": "command",
        "command": "node .bob/hooks/triage-trigger.mjs",
        "timeout": 10
      }
    ]
  }
]
```

**`triage-trigger.mjs` behavior:**
- Parses `tool_response` from stdin.
- If `status === "failed"`, writes to stdout:
  ```
  Pipeline failed. Spawn triage-subagent with the failure payload. Call recall_failures for each failure signature before recommending action.
  ```
- Bob acts on this context injection by spawning the triage subagent.

**Investigation sequence (triage subagent — general type):**
1. For each failure in payload, compute `signature = hash(test_name + error_type)`.
2. Call `recall_failures(signature)` → returns historical matches.
3. If ≥ 2 historical matches with same action outcome: high-confidence recommendation.
4. If 0 matches: low-confidence — recommend manual review, store as new failure.
5. Return structured result:
   ```json
   {
     "recommendation": "Revert commit abc123",
     "confidence": "high",
     "action": "revert",
     "matched_past_failures": 3,
     "evidence": ["failure-id-7", "failure-id-12"]
   }
   ```

**Approval boundary:** The subagent NEVER executes a revert or deploy — it only produces a recommendation. Any actual `git revert` or `kubectl` command requires explicit developer approval in Bob's main conversation.

---

## 10. MCP Layer

**Server name:** `ci-intelligence`
**Transport:** STDIO (local for demo; Code Engine for optional deployed variant)
**Runtime:** Node.js 20

### Tool specifications:

#### `run_pipeline`
- **Purpose:** Trigger or fetch a CI pipeline run; returns failure payload.
- **Input:** `{ "ref": string }` — git ref or run ID.
- **Output:** `{ run_id, ref, status, failures[], triggered_at }` (see Section 9 schema).
- **Source:** GitHub Actions REST API or fixture file `demo/fixtures/<run-id>.json` if API unavailable.
- **Example call:** `run_pipeline({ ref: "run-42" })`

#### `store_failure`
- **Purpose:** Persist a failure + recommendation to the memory store.
- **Input:** `{ run_id, signature, failures[], recommendation, action, confidence, session_id }`.
- **Output:** `{ stored: true, failure_id: "f-<uuid>" }`.
- **Source:** Writes to `memory/failures.db` (SQLite).
- **Example call:** `store_failure({ run_id: "run-42", signature: "sha256:abc", ... })`

#### `recall_failures`
- **Purpose:** Retrieve past failures matching a signature.
- **Input:** `{ signature: string, limit?: number }`.
- **Output:** `{ matches: [{ failure_id, action, confidence, stored_at }] }`.
- **Source:** Reads from `memory/failures.db`.
- **Example call:** `recall_failures({ signature: "sha256:abc", limit: 5 })`

#### `check_release_readiness`
- **Purpose:** Run a set of release gates and return PASS/WARNING/BLOCKER status.
- **Input:** `{ ref: string, target_env: "staging" | "dev" }`.
- **Output:** `{ overall: "PASS" | "WARNING" | "BLOCKER", checks: [{ name, status, detail }] }`.
- **Source:** Runs shell sub-checks (git log count, test pass rate from last run, coverage threshold from `coverage.json`).
- **Example call:** `check_release_readiness({ ref: "feat/auth", target_env: "staging" })`

#### `get_coverage_report`
- **Purpose:** Fetch the latest coverage report for a ref.
- **Input:** `{ ref: string }`.
- **Output:** `{ ref, total_coverage_pct, files: [{ path, coverage_pct, uncovered_lines[] }] }`.
- **Source:** Reads `reports/coverage-<ref>.json` or calls coverage API endpoint **[ASSUMED: file-based for demo]**.
- **Example call:** `get_coverage_report({ ref: "feat/auth" })`

**MCP registration (`.bob/mcp.json`):**
```json
{
  "mcpServers": {
    "ci-intelligence": {
      "command": "node",
      "args": ["mcp/server.js"],
      "cwd": ".",
      "env": {
        "CI_API_TOKEN": "${CI_API_TOKEN}"
      },
      "alwaysAllow": ["recall_failures", "get_coverage_report"]
    }
  }
}
```

---

## 11. Failure Memory System

**Failure signature:** `SHA-256(test_name + ":" + error_class + ":" + failing_file)`
- Computed in the triage subagent before calling `recall_failures`.
- Stable across runs with the same test/error; not dependent on line numbers (which shift with refactoring).

**Storage:** SQLite database at `memory/failures.db`.

Schema:
```sql
CREATE TABLE failures (
  id          TEXT PRIMARY KEY,
  signature   TEXT NOT NULL,
  run_id      TEXT,
  test_name   TEXT,
  error_class TEXT,
  action      TEXT,   -- 'rerun' | 'fix' | 'revert'
  confidence  TEXT,
  stored_at   TEXT,
  session_id  TEXT
);
CREATE INDEX idx_signature ON failures(signature);
```

**Seeded data:** 3 pre-seeded failures in `memory/seed.sql` committed to the repo so the demo shows matches on first run.

**Retrieval:** `recall_failures` queries `WHERE signature = ? ORDER BY stored_at DESC LIMIT ?`.

**Example replay:** Given a new failure with `signature = "sha256:abc"`, `recall_failures` returns:
```json
{
  "matches": [
    { "failure_id": "f-007", "action": "revert", "confidence": "high", "stored_at": "2025-01-01" },
    { "failure_id": "f-012", "action": "revert", "confidence": "high", "stored_at": "2025-01-03" }
  ]
}
```
The triage subagent reads these and returns: `"action": "revert", "confidence": "high"` — matching history drives the recommendation.

**Session log:** `Stop` hook writes to `memory/sessions.jsonl` (one JSON line per session):
```json
{ "session_id": "task-123", "outcome": "recommendation_stored", "failures_processed": 1, "timestamp": "..." }
```

---

## 12. Release Readiness Agent

**Implemented as the `check_release_readiness` MCP tool** — not a separate Bob conversation. It runs checks synchronously and returns a structured gate result.

**Checks performed:**

| Check | PASS condition | WARNING | BLOCKER |
|---|---|---|---|
| Test pass rate | last run 100% pass | 90–99% pass | < 90% pass |
| Coverage threshold | ≥ 80% total | 70–79% | < 70% |
| Unresolved blockers in memory | 0 failures with `action=blocker` in last 24h | — | ≥ 1 such failure |
| Branch behind main | 0 commits behind | 1–5 behind | > 5 behind |

**Gate logic:** If any check is BLOCKER → overall `BLOCKER`. If any WARNING and no BLOCKER → overall `WARNING`. All PASS → `PASS`.

**How Bob uses it:**
- The `PreToolUse` hook's `deploy-guard.mjs` calls `check_release_readiness` internally before blocking.
- Bob's main conversation can also call it explicitly when asked "is this ready to deploy?"

---

## 13. watsonx Orchestrate Decision

**Decision: Justified inclusion (narrowly scoped).**

**Why included (not automatic):**
- watsonx Orchestrate is confirmed available (Context Intake).
- The one gap Bob cannot fill is delivering a structured, human-readable recommendation to a person who is NOT in the Bob IDE — specifically, an on-call engineer receiving a Slack notification.
- Orchestrate's skill-based routing is the natural bridge between Bob's machine-readable output and a human notification channel.

**Scope — exactly one Orchestrate skill:**
- Skill name: `NotifyOnCall`
- Input: `{ recommendation, action, confidence, run_id, ref }`
- Action: Formats a Slack block-kit message and sends it via Slack API.
- Triggered: Bob calls a `notify_oncall` MCP tool (or HTTP endpoint) after `store_failure` completes.

**Why NOT used for anything else:**
- Bob handles all triage, memory, coverage, and gate logic autonomously — Orchestrate adding a second reasoning layer there would duplicate capability without adding value.
- Dropping Orchestrate entirely was considered, but losing the human-notification channel weakens the Business Value judging criterion (20%).

---

## 14. Deployment Safety + Rollback

**Health checks (for Code Engine deployment of MCP server, if OPTIONAL path taken):**
- HTTP GET `/health` on the MCP server returns `{ status: "ok", db_connected: true }`.
- Code Engine liveness probe: GET `/health`, failure threshold 3, period 10s.

**Rollback trigger/mechanism:**
- If `check_release_readiness` returns `overall: "BLOCKER"`, Bob's `PreToolUse` hook blocks the deploy command.
- If a post-deploy failure is detected (simulated in demo): triage subagent recommends `action: "revert"`.
- Bob proposes: `git revert <commit> && git push` — requires explicit developer approval before execution.

**Demo failure scenario (pre-planned):**
1. Developer asks Bob to "deploy feat/auth to staging."
2. Bob calls `check_release_readiness({ ref: "feat/auth", target_env: "staging" })`.
3. Tool returns `BLOCKER: coverage 68% < 80% threshold`.
4. `PreToolUse` hook on `execute_command` blocks `kubectl apply staging`.
5. Bob explains the blocker and suggests: "Run the coverage subagent to identify gaps first."

This scenario is scripted and reproducible — it does not depend on a live environment being broken.

---

## 15. Security Gates

**Real checks (will be demonstrated):**

| Gate | Implementation | Blocking? |
|---|---|---|
| Blocked deploy patterns | `deploy-guard.mjs` `PreToolUse` hook; regexp match on `kubectl apply.*production` | Blocking — exits 2 |
| MCP server API token | `CI_API_TOKEN` passed as env var; not in any committed file | Non-blocking (build-time) |
| Release readiness gate | `check_release_readiness` BLOCKER result → deploy blocked | Blocking via hook |
| Session outcome log | `Stop` hook writes to `memory/sessions.jsonl` | Audit trail only |

**Simulated checks (labeled honestly for judges):**

| Gate | Why simulated | Label in demo |
|---|---|---|
| Secret scanning on write | No secret scanner in scope; would use a real `PostToolUse` hook in production | "Production would add: `gitleaks` PostToolUse hook" |
| RBAC on memory store | Single-user demo; SQLite has no auth layer | "Production: Db2 or PostgreSQL with role-based access" |
| TLS for MCP server | Local STDIO transport used for demo | "Code Engine deployment uses HTTPS + IBM Cloud cert" |

Every simulated gate is explicitly labeled "simulated" in the demo README.

---

## 16. Final MVP Architecture & Execution Plan

### A. Final MVP

The minimum viable product is a Bob-configured CI intelligence loop that:
1. Receives a failed pipeline run (via MCP tool or slash command).
2. Matches it against failure memory.
3. Returns a structured recommendation (rerun / fix / revert).
4. Blocks unsafe deploys via hooks.
5. Stores every session outcome for future recall.

### B. Optional (if time permits)

- Code Engine remote deployment of MCP server.
- Orchestrate Slack notification.
- Live GitHub Actions webhook.
- Coverage subagent integration in the demo.

### C. Explicitly Dropped

- Web UI dashboard — adds build time with no judging weight.
- Multi-workspace support — single repo demo is sufficient.
- User authentication on the MCP server — out of scope for 48-hour demo.
- Fine-tuned model — watsonx foundation models via Orchestrate are used as-is.

### D. Tech Stack

| Layer | Technology | Owner |
|---|---|---|
| Bob configuration | IBM Bob 2.0 (hooks, MCP, subagents, rules, slash commands) | All |
| MCP server | Node.js 20, `@modelcontextprotocol/sdk` | Node.js dev |
| CI API client | Python 3.11 (called by MCP server via child process, or Node HTTP) | Python dev |
| Failure memory | SQLite via `better-sqlite3` (Node) | Node.js dev |
| Orchestrate skill | watsonx Orchestrate (no-code skill builder + Slack API) | IBM Cloud dev |
| Deployment | IBM Code Engine (optional) | IBM Cloud dev |
| Demo fixtures | Static JSON in `demo/fixtures/` | All |

### E. Repo Structure

```
bob-ci-agent/
├── .bob/
│   ├── settings.json          # hooks configuration
│   ├── mcp.json               # MCP server registration
│   ├── rules/
│   │   ├── 01-project.md      # AGENTS.md-style project context
│   │   └── deploy-contract.json
│   ├── rules-agent/
│   │   └── 01-triage.md       # triage mode instructions
│   ├── hooks/
│   │   ├── coverage-intent-detector.mjs
│   │   ├── triage-trigger.mjs
│   │   ├── deploy-guard.mjs
│   │   ├── prompt-gate.mjs
│   │   └── session-stop-logger.mjs
│   └── commands/
│       └── triage.md          # /triage slash command
├── mcp/
│   ├── server.js              # MCP server entry point
│   ├── tools/
│   │   ├── run_pipeline.js
│   │   ├── store_failure.js
│   │   ├── recall_failures.js
│   │   ├── check_release_readiness.js
│   │   └── get_coverage_report.js
│   └── db.js                  # SQLite connection
├── memory/
│   ├── failures.db            # runtime (gitignored)
│   └── seed.sql               # committed seed data
├── reports/
│   └── coverage-feat-auth.json  # seeded coverage report
├── demo/
│   ├── fixtures/
│   │   └── run-42.json        # seeded failure fixture
│   ├── fallback-triage.mp4
│   └── fallback-slack.png
├── AGENTS.md                  # root project context for Bob
├── README.md
└── package.json
```

### F. API Design

All inter-component communication goes through the MCP tool interface (Section 10). No REST API is exposed by the demo app. The MCP server is the only network boundary:

- Local demo: STDIO transport — no network port.
- Optional Code Engine: Streamable HTTP on port 3000, path `/mcp`, token via `Authorization: Bearer`.

### G. Bob Configuration

**`.bob/settings.json` (workspace scope):**
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "^startup$",
        "hooks": [
          {
            "type": "command",
            "command": "node .bob/hooks/session-start-context.mjs",
            "timeout": 5
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node .bob/hooks/coverage-intent-detector.mjs",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "node .bob/hooks/prompt-gate.mjs",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "^mcp__ci-intelligence__run_pipeline$",
        "hooks": [
          {
            "type": "command",
            "command": "node .bob/hooks/triage-trigger.mjs",
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "^execute_command$",
        "hooks": [
          {
            "type": "command",
            "command": "node .bob/hooks/deploy-guard.mjs",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node .bob/hooks/session-stop-logger.mjs",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

**`.bob/mcp.json`:** See Section 10.

**Subagent rules** (`.bob/rules-agent/01-triage.md`):
```
When spawning the triage subagent:
- Always pass the full failure payload including signature.
- The subagent must call recall_failures before making a recommendation.
- The subagent must never call execute_command, kubectl, git revert, or any mutating command.
- Return a structured JSON recommendation only.
```

**Slash command** (`.bob/commands/triage.md`):
```markdown
---
description: Triage a CI pipeline failure by run ID
argument-hint: <run-id>
---
Call run_pipeline with ref=$1. If status is failed, spawn the triage subagent with the failure payload. Show the recommendation and store the result.
```

### H. Data Flow

```
1. /triage run-42
        |
        v
2. Bob → mcp__ci-intelligence__run_pipeline({ ref: "run-42" })
        |
        v (PostToolUse hook fires — triage-trigger.mjs injects context)
        |
3. Bob spawns triage-subagent
   triage-subagent → mcp__ci-intelligence__recall_failures({ signature: "sha256:abc" })
        |
        v
4. recall_failures returns 2 historical matches with action="revert"
        |
        v
5. triage-subagent returns { recommendation, action: "revert", confidence: "high" }
        |
        v
6. Bob → mcp__ci-intelligence__store_failure({ ... + recommendation })
        |
        v
7. Stop hook → session-stop-logger.mjs → appends to memory/sessions.jsonl
        |
        v
8. (SHOULD) Bob → mcp__ci-intelligence__notify_oncall({ ... })
   → watsonx Orchestrate NotifyOnCall skill → Slack DM to on-call
```

### I. Security Model

| Concern | Control | Reality level |
|---|---|---|
| No deploy to production | `deploy-guard.mjs` PreToolUse hook blocks matching commands | Real (demo) |
| No secrets in repo | `CI_API_TOKEN` via env var; `.env` in `.gitignore` | Real |
| Triage subagent read-only | Rules file instructs: no mutating tools | Convention (enforced by rules, not sandbox) |
| Audit trail | `Stop` hook writes session log | Real |
| MCP server token | `alwaysAllow` only for read tools; write tools require approval | Real |

### J. Failure Modes + Fallbacks

| Failure | Detection | Fallback |
|---|---|---|
| `run_pipeline` CI API down | MCP tool returns error JSON | Return fixture from `demo/fixtures/<run-id>.json` |
| `recall_failures` DB missing | `db.js` checks file existence on init | Return empty matches; triage proceeds as "new failure" |
| triage subagent times out | Bob shows timeout in transcript | Pre-recorded fallback-triage.mp4 used in demo |
| Orchestrate unavailable | `notify_oncall` returns error | fallback-slack.png shown; described as "live in production" |
| Hook script missing | Bob fails open (hooks error ≠ block) | Demo proceeds; note in README |

### K. Demo Repo Spec

The repo is self-contained and reproducible from a fresh clone:

```bash
npm install          # installs MCP server deps
npm run seed-db      # runs memory/seed.sql to populate failures.db
npm run start-mcp    # starts MCP server (STDIO — Bob connects automatically)
# Open Bob in the repo directory; hooks and MCP config load automatically
```

Seeded data:
- 3 historical failures in `memory/seed.sql` (two reverts, one rerun).
- 1 failure fixture in `demo/fixtures/run-42.json` matching one of the seeded signatures.
- 1 coverage report in `reports/coverage-feat-auth.json` with total coverage 68% (triggers BLOCKER).

### L. Team Task Distribution

| Person | Role | Owns |
|---|---|---|
| P1 (Python) | Core services | `run_pipeline` tool (CI API client), `check_release_readiness` logic, coverage report reader |
| P2 (Node.js) | MCP server + hooks | `mcp/server.js`, all five tool handlers, all five hook scripts, SQLite schema |
| P3 (IBM Cloud) | Deployment + Orchestrate | `.bob/settings.json`, `.bob/mcp.json`, Code Engine deploy (optional), Orchestrate skill |
| P4 (any, if present) | Demo + docs | `demo/` fixtures, seed SQL, README, evidence screenshots, slash command, AGENTS.md |

If team is 3 people: P4's work is split between P1 (fixtures, seed) and P3 (docs, screenshots).

### M. 48-Hour Phase Plan

| Phase | Hours | Objective | Key Tasks | Owner | Dependencies | Effort | DoD | Risk |
|---|---|---|---|---|---|---|---|---|
| 0 — Setup | 0–3h | Repo, Bob init, skeleton running | Create repo; run `/init`; scaffold `mcp/server.js` with stub tools; write `AGENTS.md`; verify Bob loads MCP | P2, P3 | None | Low | `node mcp/server.js` starts; Bob shows tools in context | MCP SDK version mismatch |
| 1 — MCP core | 3–10h | All 5 MCP tools return correct shapes | Implement `run_pipeline` (fixture), `store_failure`, `recall_failures`, `check_release_readiness`, `get_coverage_report`; SQLite schema + seed | P1, P2 | Phase 0 | High | Each tool callable from Bob; seed data returns matches | SQLite on Windows (P2 machine) |
| 2 — Hooks | 10–16h | All 5 hooks wired and tested | Write hook scripts; add to `.bob/settings.json`; test each by piping JSON to the script directly; verify PostToolUse fires after run_pipeline | P2, P3 | Phase 1 | Medium | Each hook exits correctly on representative input | Matcher regex for PostToolUse MCP tool name |
| 3 — Subagents | 16–22h | Triage + coverage subagents return structured results | Write triage subagent rules; write coverage subagent; test with seeded data; verify recall→recommendation chain | P1, P2 | Phase 2 | High | Triage subagent returns `action` field from recall match | Subagent context window size |
| 4 — Gates | 22–27h | Deploy gate blocks correctly | Implement `deploy-guard.mjs`; test block on `kubectl apply staging`; test PASS on allowed commands; write `/triage` slash command | P2, P3 | Phase 2 | Medium | `/triage run-42` demo flow runs end-to-end | Hook exit-2 behavior on Windows |
| 5 — Orchestrate (SHOULD) | 27–33h | Slack notification delivered | Build `NotifyOnCall` Orchestrate skill; wire `notify_oncall` MCP tool; test Slack DM | P3 | Phase 3 | Medium | Slack message received with recommendation text | Orchestrate instance availability |
| 6 — Demo prep | 33–42h | Full demo script runs in ≤3 min | Record fallback videos/screenshots; rehearse 3 times; populate all evidence artifacts; write README | P4 / All | Phase 5 | Low | Demo runs clean 2/3 rehearsals | Live CI API dependency |
| 7 — Polish + submission | 42–48h | All judging evidence committed | README evidence section; annotated screenshots; final repo push; submission form | All | Phase 6 | Low | Repo is public/shared; all evidence files present | — |

### N. Judging-Criteria Mapping

| Criterion | Weight | Evidence | Where to find it |
|---|---|---|---|
| **Innovation** | 30% | Bob hooks driving autonomous triage (not a simple chatbot); failure memory creating a learning CI loop; PreToolUse gate pattern for deploy safety | Bob transcript screenshots; hook scripts in `.bob/hooks/`; Section 8–9 of this plan |
| **Technical Implementation** | 30% | Working MCP server with 5 tools; 5 real hooks with correct event semantics; subagent chain with structured output; SQLite memory with indexed signature lookup | `mcp/` source; `.bob/settings.json`; live demo run; `memory/failures.db` |
| **Business Value** | 20% | Before/after time measurement (Section 4); failure memory hit-rate from demo run; explicit deploy gate preventing a real class of incident | Before/after table in README; `memory/sessions.jsonl` counts; deploy block shown live |
| **Demo Quality** | 20% | Timestamped script (Section 5); fallback recordings for every risky step; one clean end-to-end flow ≤ 3 min; config shown openly | `demo/` folder; rehearsal ≥ 2x; README annotated |

### O. Go/No-Go Checklist

Before starting the demo clock, verify:

- [ ] `node mcp/server.js` starts cleanly and Bob shows all 5 tools in context.
- [ ] `npm run seed-db` runs without error; `recall_failures({ signature: "sha256:abc" })` returns 2 matches.
- [ ] `/triage run-42` produces a recommendation in Bob chat (from fixture).
- [ ] `kubectl apply staging` is blocked by the PreToolUse hook (verify exit 2 message in transcript).
- [ ] `memory/sessions.jsonl` is written after a session ends (Stop hook).
- [ ] `PostToolUse` hook fires after `run_pipeline` (visible in transcript or hook log).
- [ ] Fallback recordings are playable.
- [ ] `CI_API_TOKEN` is set in environment (not committed).
- [ ] README evidence section has all screenshots from Section 6.

---

## The First 6 Hours

**Chronological, concrete, no coding yet — establish the foundation before writing a line.**

**Hour 0:00–0:30 — Team sync**
- All 3–4 people read this plan.
- Assign roles per Section 16L.
- Create a shared Slack channel or group chat for async hand-offs.
- P3: verify IBM Cloud credentials, Bob 2.0 license, and Orchestrate instance access before anything else is built.

**Hour 0:30–1:00 — Repo creation (P2 leads)**
- Create `bob-ci-agent` repo on GitHub (or IBM Cloud Git).
- P2 creates the directory scaffold from Section 16E — empty files, correct paths, no code yet.
- P3 opens the repo in Bob and runs `/init` to generate `AGENTS.md`.
- Commit the scaffold with message `chore: initial scaffold`.

**Hour 1:00–1:30 — Bob verification (P3)**
- Write `.bob/mcp.json` with stub `mcp/server.js` (a Node script that exits 0 immediately).
- Verify Bob shows `ci-intelligence` in its tool list (this confirms MCP wiring works before any tool logic is written).
- Write a minimal `.bob/settings.json` with one `Stop` hook that echoes "hook ok" — verify it runs.
- Screenshot both verifications — these are early evidence artifacts.

**Hour 1:30–2:30 — SQLite schema + seed (P2)**
- Write `memory/seed.sql` with 3 rows (two `action=revert`, one `action=rerun`) using the signature for `run-42`.
- Write `mcp/db.js` — open/create `memory/failures.db`, run the schema migration.
- Run `npm run seed-db` manually; confirm rows are inserted.
- This is the foundation all tools depend on — no tool works until the DB is ready.

**Hour 2:30–3:30 — Fixture creation (P4 / P1)**
- Write `demo/fixtures/run-42.json` using the exact schema from Section 9.
- Write `reports/coverage-feat-auth.json` with `total_coverage_pct: 68` (triggers BLOCKER gate).
- Write a simple `run_pipeline` tool stub that reads from the fixture if no live API is reachable — this makes Phase 1 testable offline immediately.
- Commit all fixtures.

**Hour 3:30–5:00 — Hook scripts skeleton (P2)**
- Write the five hook scripts as stubs: each reads stdin, logs the event name, and exits 0.
- Add all five to `.bob/settings.json` with correct event names and matchers (from Section 16G).
- Test each by piping the representative JSON from the hooks skill documentation (Section 3 of the skill) into each script.
- **Do not implement logic yet** — confirm the event fires and the script receives input.

**Hour 5:00–6:00 — First integration test (all)**
- P2 runs a full Bob session: type `/triage run-42`.
- Observe: `run_pipeline` stub called → `PostToolUse` hook fires → triage-trigger stub logs to stdout → Bob adds context.
- Nothing needs to produce a real result yet — this confirms the entire event chain is wired.
- Take a screenshot of the transcript. This is the first meaningful evidence artifact.
- Brief team check-in: confirm Phase 0 DoD is met before Phase 1 begins.

---

*Plan status: [ ] pending implementation — switch to Agent mode to begin.*