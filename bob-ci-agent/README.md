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
- **pytest coverage** for `run_pipeline` — 16 tests, all passing

> Features not yet implemented: MCP wrapper, coverage reader, release
> readiness, Bob hooks, triage subagent, deployment, dashboard.

---

## run_pipeline

### Purpose

Loads, validates, and returns the CI pipeline result for a given run reference.
For the hackathon MVP this always resolves to a local fixture file.

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
  "triggered_at": "2025-01-26T10:00:00Z"
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
│   └── test_ci_client.py     ← 16 pytest tests for run_pipeline
│
├── demo/
│   └── fixtures/
│       └── run-42.json       ← deterministic demo fixture
│
├── conftest.py               ← pytest sys.path configuration
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
python -c "from python.ci_client import run_pipeline; print(run_pipeline('run-42'))"
```

---

## Implementation Log

### 2025-01-26 — run_pipeline implementation

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

Testing:

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
collected 16 items

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
  "triggered_at": "2025-01-26T10:00:00Z",
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
