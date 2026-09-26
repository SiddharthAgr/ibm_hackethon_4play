"""conftest.py — pytest root configuration for bob-ci-agent.

Adds the bob-ci-agent directory to sys.path so that `from python.ci_client
import ...` works when running pytest from the bob-ci-agent directory.
"""

import sys
from pathlib import Path

# Insert the bob-ci-agent directory (parent of this file) at the front of
# sys.path so that the `python` package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
