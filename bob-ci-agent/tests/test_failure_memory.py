"""
tests/test_failure_memory.py
============================
Regression tests for the Failure Memory component.

Scope  : bob-ci-agent/memory/ (schema.sql, seed.sql)
Owner  : Apurva
Runner : python -m unittest bob-ci-agent/tests/test_failure_memory.py
Deps   : stdlib only (unittest, sqlite3, hashlib, pathlib)
"""

import hashlib
import pathlib
import sqlite3
import unittest

# ---------------------------------------------------------------------------
# Locate schema.sql relative to this file so the tests run from any cwd
# ---------------------------------------------------------------------------
_TESTS_DIR  = pathlib.Path(__file__).resolve().parent
_MEMORY_DIR = _TESTS_DIR.parent / "memory"
_SCHEMA_SQL = _MEMORY_DIR / "schema.sql"


def _build_in_memory_db() -> sqlite3.Connection:
    """Create a fresh :memory: SQLite DB with the project schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA_SQL.read_text(encoding="utf-8"))
    return conn


def _insert_failure(conn: sqlite3.Connection, **kwargs) -> None:
    """Insert one row into failures; any column can be overridden via kwargs."""
    defaults = dict(
        id="t-001",
        signature="aabbcc",
        run_id="run-99",
        session_id="sess-01",
        test_name="test_example",
        error_type="AssertionError",
        failing_file="tests/test_example.py",
        failure_message="AssertionError: 1 != 2",
        action="rerun",
        recommendation="Re-run the pipeline.",
        confidence="high",
        confidence_score=0.90,
        resolution=None,
        resolved=0,
        stored_at="2025-09-20T10:00:00Z",
        updated_at=None,
    )
    defaults.update(kwargs)
    conn.execute(
        """
        INSERT INTO failures (
            id, signature, run_id, session_id,
            test_name, error_type, failing_file, failure_message,
            action, recommendation, confidence, confidence_score,
            resolution, resolved, stored_at, updated_at
        ) VALUES (
            :id, :signature, :run_id, :session_id,
            :test_name, :error_type, :failing_file, :failure_message,
            :action, :recommendation, :confidence, :confidence_score,
            :resolution, :resolved, :stored_at, :updated_at
        )
        """,
        defaults,
    )
    conn.commit()


class TestSchemaTablesExist(unittest.TestCase):
    """Test 1 — required tables are created by schema.sql."""

    def setUp(self):
        self.conn = _build_in_memory_db()

    def tearDown(self):
        self.conn.close()

    def _table_names(self):
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {r[0] for r in rows}

    def test_failures_table_exists(self):
        self.assertIn("failures", self._table_names())

    def test_sessions_table_exists(self):
        self.assertIn("sessions", self._table_names())

    def test_schema_migrations_table_exists(self):
        self.assertIn("schema_migrations", self._table_names())


class TestSchemaIndexesExist(unittest.TestCase):
    """Test 2 — required indexes are created by schema.sql."""

    def setUp(self):
        self.conn = _build_in_memory_db()

    def tearDown(self):
        self.conn.close()

    def _index_names(self):
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        return {r[0] for r in rows}

    def test_idx_signature_exists(self):
        self.assertIn("idx_signature", self._index_names())

    def test_idx_stored_at_exists(self):
        self.assertIn("idx_stored_at", self._index_names())


class TestActionConstraint(unittest.TestCase):
    """Tests 3 & 4 — valid actions accepted, invalid action rejected."""

    def setUp(self):
        self.conn = _build_in_memory_db()

    def tearDown(self):
        self.conn.close()

    def test_action_rerun_accepted(self):
        _insert_failure(self.conn, id="a-rerun", action="rerun")
        row = self.conn.execute("SELECT action FROM failures WHERE id='a-rerun'").fetchone()
        self.assertEqual(row[0], "rerun")

    def test_action_fix_accepted(self):
        _insert_failure(self.conn, id="a-fix", action="fix")
        row = self.conn.execute("SELECT action FROM failures WHERE id='a-fix'").fetchone()
        self.assertEqual(row[0], "fix")

    def test_action_revert_accepted(self):
        _insert_failure(self.conn, id="a-revert", action="revert")
        row = self.conn.execute("SELECT action FROM failures WHERE id='a-revert'").fetchone()
        self.assertEqual(row[0], "revert")

    def test_action_escalate_accepted(self):
        _insert_failure(self.conn, id="a-escalate", action="escalate")
        row = self.conn.execute("SELECT action FROM failures WHERE id='a-escalate'").fetchone()
        self.assertEqual(row[0], "escalate")

    def test_invalid_action_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            _insert_failure(self.conn, id="a-bad", action="deploy")


class TestConfidenceScoreConstraint(unittest.TestCase):
    """Test 5 — confidence_score outside [0.0, 1.0] is rejected."""

    def setUp(self):
        self.conn = _build_in_memory_db()

    def tearDown(self):
        self.conn.close()

    def test_score_below_zero_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            _insert_failure(self.conn, id="cs-low", confidence_score=-0.01)

    def test_score_above_one_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            _insert_failure(self.conn, id="cs-high", confidence_score=1.01)

    def test_score_zero_accepted(self):
        _insert_failure(self.conn, id="cs-0", confidence_score=0.0)
        row = self.conn.execute("SELECT confidence_score FROM failures WHERE id='cs-0'").fetchone()
        self.assertEqual(row[0], 0.0)

    def test_score_one_accepted(self):
        _insert_failure(self.conn, id="cs-1", confidence_score=1.0)
        row = self.conn.execute("SELECT confidence_score FROM failures WHERE id='cs-1'").fetchone()
        self.assertEqual(row[0], 1.0)


class TestRecallOrdering(unittest.TestCase):
    """Test 6 — recall query returns rows ordered by stored_at DESC."""

    def setUp(self):
        self.conn = _build_in_memory_db()
        sig = "same-signature"
        _insert_failure(self.conn, id="r-old", signature=sig, stored_at="2025-09-01T10:00:00Z")
        _insert_failure(self.conn, id="r-mid", signature=sig, stored_at="2025-09-10T10:00:00Z")
        _insert_failure(self.conn, id="r-new", signature=sig, stored_at="2025-09-20T10:00:00Z")

    def tearDown(self):
        self.conn.close()

    def test_recall_returns_most_recent_first(self):
        rows = self.conn.execute(
            """
            SELECT id FROM failures
            WHERE signature = 'same-signature'
            ORDER BY stored_at DESC
            LIMIT 5
            """
        ).fetchall()
        ids = [r[0] for r in rows]
        self.assertEqual(ids, ["r-new", "r-mid", "r-old"])

    def test_recall_limit_is_respected(self):
        rows = self.conn.execute(
            """
            SELECT id FROM failures
            WHERE signature = 'same-signature'
            ORDER BY stored_at DESC
            LIMIT 2
            """
        ).fetchall()
        self.assertEqual(len(rows), 2)


class TestSignatureConvention(unittest.TestCase):
    """Tests 7 & 8 — SHA-256(test_name:error_type:failing_file) convention."""

    def _sig(self, test_name: str, error_type: str, failing_file: str) -> str:
        raw = f"{test_name}:{error_type}:{failing_file}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def test_known_signature_matches_seed_eval01(self):
        """The eval-01 / run-42 signature must equal the value in seed.sql and fixtures."""
        expected = "e05df3df6765b575ef14be0d76c581b5d7e29f641cd5520c270680c0fb63ecde"
        actual = self._sig("test_auth_token_expiry", "AssertionError", "tests/test_auth.py")
        self.assertEqual(actual, expected)

    def test_different_failing_file_produces_different_signature(self):
        """Changing only failing_file must change the signature (verifies hash isolation)."""
        sig_auth  = self._sig("test_auth_token_expiry", "AssertionError", "tests/test_auth.py")
        sig_oauth = self._sig("test_auth_token_expiry", "AssertionError", "tests/test_oauth.py")
        self.assertNotEqual(sig_auth, sig_oauth)

    def test_signature_is_64_hex_chars(self):
        """SHA-256 output is always 64 lowercase hex characters."""
        sig = self._sig("test_foo", "ValueError", "tests/test_foo.py")
        self.assertEqual(len(sig), 64)
        self.assertRegex(sig, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
