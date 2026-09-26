# IBM Bob 2.0 Hackathon — CI Intelligence Agent
## Project: Team 4Play (`bob-ci-agent`)

### What this project does
This workspace implements an AI-powered CI/CD intelligence agent built on IBM Bob 2.0.
Bob autonomously triages CI pipeline failures, recalls historical failure patterns from a
failure memory store, recommends actions (rerun / fix / revert / escalate), and blocks unsafe
deployments before they reach production.

### Key capabilities
- **`/triage <run-id>`** — Run the full triage flow: fetch pipeline failures, recall history, recommend action, store result.
- **Failure Memory** — SQLite-backed store at `bob-ci-agent/memory/failures.db`. 10 seeded historical failures across auth, Redis, imports, type errors, DNS flakes, and coverage gates.
- **Coverage subagent** — Reads `reports/coverage-<ref>.json`; blocks deploy if coverage < 80%.
- **Deploy guard** — PreToolUse hook blocks `kubectl apply`, `helm upgrade`, or `git push` to `main`/`staging` without a PASS from `check_release_readiness`.
- **Session memory** — Stop hook writes `memory/sessions.jsonl` for audit.

### Architecture
```
User /triage run-42
  → Bob calls run_pipeline("run-42")
  → PostToolUse hook (triage-trigger.mjs) fires
  → Bob spawns triage subagent
  → subagent calls recall_failures(signature)
  → SQLite memory returns historical matches
  → subagent returns recommendation (action + confidence)
  → Bob calls store_failure(...)
  → Stop hook writes session log
```

### MCP tools (ci-intelligence server)
| Tool | Purpose |
|------|---------|
| `run_pipeline` | Fetch CI run failures (fixture or GitHub API) |
| `recall_failures` | Query failure memory by SHA-256 signature |
| `store_failure` | Persist triage result to memory |
| `check_release_readiness` | Coverage + blocker gate checks |
| `get_coverage_report` | Per-file coverage breakdown |

### Failure signature formula
```
signature = SHA-256(test_name + ":" + error_type + ":" + failing_file)
```
The triage subagent computes this. The MCP layer is a pure storage/retrieval layer.

### Setup
```bash
cd bob-ci-agent
npm install
npm run seed-db     # populates memory/failures.db with 10 historical failures
# Open Bob — MCP server starts automatically via .bob/mcp.json
```

### Important contracts
- Use `error_type` (not `error_class`) in all SQL queries and tool inputs.
- The MCP server resolves `memory/failures.db` relative to its own file location, not `process.cwd()`.
- The triage subagent must call `recall_failures` BEFORE returning a recommendation.
- The triage subagent must NEVER call `execute_command`, `kubectl`, `git revert`, or any mutating OS command.

### Team ownership
| Person | Scope |
|--------|-------|
| Himanshu | IBM Bob 2.0 config, hooks, subagents |
| Bhavya | MCP server, all 5 tools, Node.js layer |
| Python Dev | `ci_client.py`, `coverage_reader.py`, `release_checks.py` |
| Apurva | Failure memory schema/seed, evaluation framework, metrics |
