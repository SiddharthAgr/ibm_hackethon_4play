"""
bridge.py — CLI entry point for invoking run_pipeline from an external process.

Usage
-----
    python -m python.bridge <ref>

    e.g.  python -m python.bridge run-42

Contract
--------
stdout  : On success, a single line containing the JSON-serialized pipeline
          result dict.  Nothing else is written to stdout.
stderr  : On failure, a human-readable error message.
exit 0  : Success.
exit 1  : Any failure (invalid ref, fixture not found, schema error, etc.).

This module is intentionally thin.  All validation, fixture loading, and
business logic live in python.ci_client.run_pipeline; this file only handles
I/O and process exit codes.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    """Run the bridge; return the exit code.

    Parameters
    ----------
    argv:
        Argument list (defaults to ``sys.argv[1:]``).  The first element must
        be the pipeline reference string.

    Returns
    -------
    int
        0 on success, 1 on any error.
    """
    args = sys.argv[1:] if argv is None else argv

    if len(args) != 1:
        print(
            f"Usage: python -m python.bridge <ref>\n"
            f"Expected exactly 1 argument, got {len(args)}.",
            file=sys.stderr,
        )
        return 1

    ref: str = args[0]

    # Import here so that import errors (if the package is broken) also go to
    # stderr rather than polluting stdout.
    try:
        from python.ci_client import run_pipeline  # noqa: PLC0415
    except ImportError as exc:
        print(f"ImportError: {exc}", file=sys.stderr)
        return 1

    try:
        result = run_pipeline(ref)
    except Exception as exc:  # noqa: BLE001
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
