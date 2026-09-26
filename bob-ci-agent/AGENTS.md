# CI Intelligence Agent — AGENTS.md
# IBM Bob 2.0 Hackathon | Team 4Play

## What this project does

This workspace is an AI-powered CI/CD intelligence agent built on IBM Bob 2.0.
Bob autonomously triages CI pipeline failures, recalls historical failure patterns
from a persistent SQLite memory store, recommends actions (rerun / fix / revert /
escalate), and blocks unsafe deployments before they reach production.

---

## Quick start

```bash
cd bob-ci-agent
npm install
npm run seed-db      # seeds memory/failures.db with 10 historical failures
# Open Bob — MCP server starts automatically via .bob/mcp.json
```

Demo trigger: `/triage run-42`

---

## Architecture

```
User /triage run-42
  → Bob calls run_pipeline("run-42")           [MCP: ci-intelligence]
  → PostToolUse hook (triage-trigger.mjs) fires
  → Bob spawns triage subagent
  → subagent computes SHA-256 signature
  → subagent calls recall_failures(signature)  [MCP: ci-intelligence]
  → SQLite memory returns historical matches
  → subagent returns { action, confidence, recommendation }
  → Bob calls store_failure(...)               [MCP: ci-intelligence]
  → Stop hook writes memory/sessions.jsonl
```

---

## MCP Tools — `ci-intelligence` server

| Tool | Purpose |
|------|---------|
| `run_pipeline({ ref })` | Fetch CI run failures — fixture or GitHub API |
| `recall_failures({ signature, limit })` | Query failure memory by SHA-256 signature |
| `store_failure({ ... })` | Persist triage result + recommendation |
| `check_release_readiness({ ref, target_env })` | Coverage + blocker + env gate checks |
| `get_coverage_report({ ref })` | Per-file coverage breakdown |

---

## Bob Hooks

| Event | Script | Effect |
|-------|--------|--------|
| `SessionStart` | `session-start-context.mjs` | Injects last 5 failures from memory into context |
| `UserPromptSubmit` | `coverage-intent-detector.mjs` | Detects coverage prompts; injects tool hints |
| `UserPromptSubmit` | `prompt-gate.mjs` | Blocks prompts requesting direct production deploys |
| `PostToolUse` | `triage-trigger.mjs` | After `run_pipeline` returns failures → triggers triage subagent |
| `PreToolUse` | `deploy-guard.mjs` | Blocks `kubectl apply`, `helm upgrade`, `git push --force`, `docker push` |
| `Stop` | `session-stop-logger.mjs` | Writes session outcome to `memory/sessions.jsonl` + SQLite |

---

## Subagents

### Triage Subagent (`.bob/subagents/triage.md`)
- **Type:** general
- **Trigger:** spawned by Bob after `PostToolUse` hook fires on `run_pipeline` failure
- **Inputs:** failure payload from `run_pipeline`
- **Mandatory steps:**
  1. Compute `signature = SHA-256(test_name + ":" + error_type + ":" + failing_file)`
  2. Call `recall_failures({ signature })`
  3. Decide action based on match count + confidence score
  4. Return structured JSON recommendation
  5. Call `store_failure(...)` with the result
- **Hard constraint:** NEVER calls `execute_command`, `kubectl`, `git revert`, or any mutating command

### Coverage Subagent (`.bob/subagents/coverage.md`)
- **Type:** explore (read-only)
- **Trigger:** spawned when coverage-related prompt detected OR after `get_coverage_report` is called
- **Inputs:** `{ ref, coverage_report_json }`
- **Returns:** `{ uncovered_files, lowest_coverage_modules, suggested_test_targets }`

---

## Failure Signature Formula

```
signature = SHA-256(test_name + ":" + error_type + ":" + failing_file)
```

- Computed by the **triage subagent** — never by the MCP server
- Stable across runs with same test/error/file
- Use `error_type` (NOT `error_class`) in all tool calls

---

## Deploy Safety Contract

Enforced by `deploy-guard.mjs` (`PreToolUse` hook):

- ❌ `kubectl apply` — blocked
- ❌ `kubectl create` / `kubectl delete` — blocked
- ❌ `helm upgrade` / `helm install` — blocked
- ❌ `git push` to `main` / `staging` / `production` — blocked
- ❌ `git push --force` — blocked
- ❌ `docker push` — blocked
- ❌ `ibmcloud ce app update` — blocked
- ✅ `kubectl get` / `describe` / `logs` / `rollout status` — always allowed

To unlock a deploy: call `check_release_readiness({ ref, target_env: "staging" })` and verify `overall == "PASS"`.

---

## Failure Memory

- **Location:** `memory/failures.db` (SQLite via sql.js)
- **Seeded with:** 10 historical failures covering auth, Redis flake, ImportError, TypeError, DNS flake, coverage gate, AttributeError, k8s ValidationError
- **Session log:** `memory/sessions.jsonl` (one JSON line per session, written by Stop hook)

Seed data: `memory/seed.sql` — run `npm run seed-db` to repopulate.

---

## Team Ownership

| Person | Scope |
|--------|-------|
| **Himanshu** | IBM Bob config (`.bob/settings.json`, `.bob/mcp.json`), hooks, subagent rules, `AGENTS.md`, `/triage` command |
| **Bhavya** | MCP server (`mcp/server.js`), all 5 tool handlers, `mcp/db.js`, Node.js layer |
| **Python Dev** | `python/ci_client.py`, `python/coverage_reader.py`, `python/release_checks.py` |
| **Apurva** | Failure memory schema/seed, `evaluation/benchmark.py`, metrics |

---

## Repo Layout (your scope)

```
bob-ci-agent/
├── AGENTS.md                        ← this file (Himanshu)
├── .bob/
│   ├── settings.json                ← hook wiring (Himanshu)
│   ├── mcp.json                     ← MCP server registration (Himanshu)
│   ├── hooks/
│   │   ├── user_prompt_submit       ← coverage + deploy gate docs (Himanshu)
│   │   ├── pre_tool_use             ← deploy block docs (Himanshu)
│   │   ├── post_tool_use            ← triage trigger docs (Himanshu)
│   │   └── stop                     ← session logger docs (Himanshu)
│   ├── subagents/
│   │   ├── triage.md                ← triage subagent rules (Himanshu)
│   │   └── coverage.md              ← coverage subagent rules (Himanshu)
│   └── commands/
│       └── triage.md                ← /triage slash command (Himanshu)
```
