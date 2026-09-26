# IBM Bob CI/CD Intelligence Agent

## Project Overview

This project is an agentic CI/CD intelligence system built around IBM Bob 2.0.
IBM Bob will use an MCP tool called `run_pipeline(ref)` to inspect CI pipeline
results, surface failures, and support triage decisions — all without leaving
the developer's conversation context.

The system is designed to be modular: a clean Python core handles data
retrieval and validation, and a separate MCP layer (implemented by a
teammate) exposes it to Bob.

---

## Current Implementation

The current implementation includes:

- **Python CI pipeline client** (`python/ci_client.py`)
- **Deterministic local fixture support** (`demo/fixtures/run-42.json`)
- **Structured pipeline result** conforming to the project failure schema
- **Input validation** and **schema validation** for all pipeline results
- **Custom error handling** with three distinct exception types
- **pytest test suite** for `run_pipeline` — 18 tests, all passing

> **Not yet implemented:** MCP wrapper, coverage reader, release readiness,
> Bob hooks, triage subagent, deployment, dashboard, GitHub Actions integration.

---

## Python Version

**Project target:** Python 3.11

**Local verification environment:** Python 3.14.3

The implementation uses only standard-library APIs available in Python 3.11.
The `from __future__ import annotations` import is included in all source
files to ensure forward-reference annotations are compatible with Python 3.11.
No Python 3.12+ syntax is used.

A `.python-version` file containing `3.11` is present for tools that respect
it (e.g. pyenv). The active virtual environment (`.venv`) was created with
the locally installed Python 3.14.3 interpreter; to use Python 3.11 exactly,
recreate the venv with a 3.11 interpreter if required.

---

## run_pipeline

### Purpose

Loads, validates, and returns the CI pipeline result for a given run reference.
For the hackathon MVP this **always resolves to a local fixture file**.

- Does **not** require GitHub Actions
- Does **not** require network access
- Does **not** require `CI_API_TOKEN`
- `run_pipeline("run-42")` reads `demo/fixtures/run-42.json` from disk

Live CI provider support is a **future extension** — the `CI_API_TOKEN`
environment variable is checked as a placeholder stub but has no effect in
the current implementation (the fixture path is always used).

### Function signature

```python
def run_pipeline(ref: str) -> dict:
    ...
```

### Input

| Parameter | Type  | Description                                                   |
|-----------|-------|---------------------------------------------------------------|
| `ref`     | `str` | Pipeline run identifier, e.g. `"run-42"`. Whitespace stripped. |

Validation rules:
- Must be a non-empty string after stripping whitespace.
- Path separator characters (`/`, `\`) are rejected to prevent traversal.

### Output

A `dict` matching the project failure schema:

```json
{
  "run_id":       "run-42",
  "ref":          "feat/auth",
  "status":       "failed",
  "failures": [
    {
      "test":        "test_auth_token_expiry",
      "error":       "AssertionError: expected 401, got 500",
      "file":        "tests/test_auth.py",
      "line":        88,
      "duration_ms": 1203
    }
  ],
  "triggered_at": "2026-09-26T10:00:00Z"
}
```

Supported statuses: `passed`, `failed`.

Any additional fields present in the fixture are preserved in the returned dict.

### Fixture location

```
bob-ci-agent/demo/fixtures/<ref>.json
```

Example: `run_pipeline("run-42")` reads `demo/fixtures/run-42.json`.

### Error behavior

| Exception                        | When raised                                            |
|----------------------------------|--------------------------------------------------------|
| `InvalidPipelineReferenceError`  | `ref` is empty, whitespace-only, non-string, or contains path separators |
| `PipelineFixtureNotFoundError`   | No fixture file exists for the given `ref`             |
| `InvalidPipelineResultError`     | Fixture exists but fails schema validation             |

### Example usage

```python
from python.ci_client import run_pipeline

result = run_pipeline("run-42")

print(result["status"])        # "failed"
print(result["failures"][0])   # {"test": ..., "error": ..., "file": ..., ...}
```

---

## Project Structure

```
bob-ci-agent/
│
├── python/
│   ├── __init__.py
│   └── ci_client.py          ← public run_pipeline() function
│
├── tests/
│   └── test_ci_client.py     ← 18 pytest tests for run_pipeline
│
├── demo/
│   └── fixtures/
│       └── run-42.json       ← deterministic demo fixture
│
├── conftest.py               ← pytest sys.path configuration
├── .python-version           ← project target: 3.11
├── requirements-dev.txt      ← pytest, pytest-cov
└── README.md
```

---

## Running Tests

```bash
# From bob-ci-agent/
.venv\Scripts\activate
pytest tests/test_ci_client.py -v
```

## Smoke Test

```bash
python -c "from python.ci_client import run_pipeline; import json; print(json.dumps(run_pipeline('run-42'), indent=2))"
```

---

## Implementation Log

### 2026-09-26 — run_pipeline implementation

Implemented:
- `python/ci_client.py`
- `demo/fixtures/run-42.json`
- `tests/test_ci_client.py`
- `conftest.py` (pytest sys.path fix)

Behavior:
- Validates pipeline references (empty, whitespace, non-string, path traversal)
- Loads deterministic fixture from `demo/fixtures/<ref>.json`
- Validates result schema (required fields, supported status, failure object structure)
- Normalizes pipeline data (preserves extra fixture fields)
- Handles missing fixtures (`PipelineFixtureNotFoundError`)
- Handles malformed fixtures (`InvalidPipelineResultError`)

Testing (16 tests at time of initial implementation):

```
platform win32 -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
collected 16 items

16 passed in 0.14s
```

Smoke test:

```
$ python -c "from python.ci_client import run_pipeline; import json; print(json.dumps(run_pipeline('run-42'), indent=2))"
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
  "triggered_at": "2026-09-26T10:00:00Z",
  "branch": "feat/auth",
  "commit_sha": "a3f9c1d"
}
```

Notes:
- `conftest.py` was required to make `from python.ci_client import ...` work
  when pytest is invoked from the `bob-ci-agent/` directory.
- The `CI_API_TOKEN` environment variable path is stubbed (no-op) and ready
  for a future live GitHub Actions provider.
- `python/coverage_reader.py`, `python/release_checks.py`, and their test
  files are empty stubs created by the repo scaffold — they are intentionally
  left unchanged by this task.

---

### 2026-09-26 — run_pipeline verification and documentation correction

Changes made:
- Corrected README implementation-log date from `2025-01-26` to `2026-09-26`
- Updated fixture `triggered_at` from `2025-01-26T10:00:00Z` to `2026-09-26T10:00:00Z`
- Added `.python-version` file declaring project target `3.11`
- Added Python version section to README: target 3.11, verified environment 3.14.3
- Changed "pytest coverage" wording to "pytest test suite" in Current Implementation section
- Clarified in `run_pipeline` section that live CI / GitHub Actions / `CI_API_TOKEN` are
  NOT used — fixture path is always the active path for the MVP
- Updated example output in README to use 2026 timestamp
- Added two path-separator tests (`test_path_separator_forward_slash_raises`,
  `test_path_separator_backslash_raises`) to `tests/test_ci_client.py`
- Updated test count in README from 16 to 18

Verification — pytest result:

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0 -- D:\IBM_Hackathon_4play\bob-ci-agent\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\IBM_Hackathon_4play\bob-ci-agent
plugins: cov-7.1.0
collecting ... collected 18 items

tests/test_ci_client.py::test_run_pipeline_returns_dict PASSED
tests/test_ci_client.py::test_run_pipeline_run_id PASSED
tests/test_ci_client.py::test_run_pipeline_status_failed PASSED
tests/test_ci_client.py::test_run_pipeline_failures_present PASSED
tests/test_ci_client.py::test_run_pipeline_failure_has_required_fields PASSED
tests/test_ci_client.py::test_empty_ref_raises PASSED
tests/test_ci_client.py::test_whitespace_ref_raises PASSED
tests/test_ci_client.py::test_unknown_ref_raises_fixture_not_found PASSED
tests/test_ci_client.py::test_malformed_fixture_missing_fields[tmp_fixture0] PASSED
tests/test_ci_client.py::test_malformed_fixture_bad_status[tmp_fixture0] PASSED
tests/test_ci_client.py::test_malformed_fixture_failure_missing_fields[tmp_fixture0] PASSED
tests/test_ci_client.py::test_no_network_required PASSED
tests/test_ci_client.py::test_result_is_json_serializable PASSED
tests/test_ci_client.py::test_extra_fields_preserved[tmp_fixture0] PASSED
tests/test_ci_client.py::test_non_string_ref_raises PASSED
tests/test_ci_client.py::test_whitespace_stripped_from_valid_ref PASSED
tests/test_ci_client.py::test_path_separator_forward_slash_raises PASSED
tests/test_ci_client.py::test_path_separator_backslash_raises PASSED

18 passed in 0.15s
```

Smoke test:

```
$ python -c "from python.ci_client import run_pipeline; import json; print(json.dumps(run_pipeline('run-42'), indent=2))"
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
  "triggered_at": "2026-09-26T10:00:00Z",
  "branch": "feat/auth",
  "commit_sha": "a3f9c1d"
}
```

Python version: `Python 3.14.3` (local environment).
Project target: `3.11` (`.python-version`).

Notes:
- `ci_client.py` is Python 3.11 compatible: uses `from __future__ import annotations`,
  standard library only, no 3.12+ syntax.
- No network access was required at any point.
- No credentials were required.
