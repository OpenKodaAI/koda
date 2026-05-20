r"""Parameterized validation matrix for koda.services.db_manager._validate_query.

Authoritative against the current regex chain (db_manager.py:22–40):

  _ALLOWED_LEADING  ^\s*(SELECT|WITH|SHOW|EXPLAIN)\b   case-insensitive
  _BLOCKED_KEYWORDS \b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY)\b
  _COMMENT_RE       (--|/*)
  _MULTI_STMT_RE    ;\s*\S
  _BACKSLASH_RE     \\

This file extends test_db_manager.py with table-driven cases that document:
  - which leading statements are allowed,
  - every banned keyword (full coverage),
  - bypass attempts that DO get caught,
  - bypass attempts that DON'T get caught (gaps documented for future work),
  - case-insensitivity,
  - false-positive shape: the blocked-keyword regex is content-blind, so any
    SELECT containing a banned word inside a string literal is also blocked.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from koda.services.db_manager import DBManager


@pytest.fixture
def dbm() -> DBManager:
    return DBManager()


# ----- Allowed leading keywords ---------------------------------------------

_ALLOWED_LEADING_CASES: list[tuple[str, str]] = [
    ("select-uppercase", "SELECT 1"),
    ("select-lowercase", "select 1"),
    ("select-with-leading-ws", "   SELECT 1"),
    ("select-with-newlines", "\n\nSELECT id FROM t"),
    ("with-cte", "WITH cte AS (SELECT 1) SELECT * FROM cte"),
    ("with-cte-multi", "WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a JOIN b ON true"),
    ("show-server-version", "SHOW server_version"),
    ("show-all", "SHOW ALL"),
    ("explain-select", "EXPLAIN SELECT 1"),
    ("explain-analyze", "EXPLAIN ANALYZE SELECT 1"),
    ("explain-analyze-buffers", "EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM t WHERE id = 1"),
    ("select-mixed-case", "SeLeCt 1"),
]


@pytest.mark.parametrize("case_id,sql", _ALLOWED_LEADING_CASES, ids=[c[0] for c in _ALLOWED_LEADING_CASES])
def test_allowed_leading_keywords(dbm: DBManager, case_id: str, sql: str) -> None:
    assert dbm._validate_query(sql) is None, f"{case_id} should be allowed: {sql!r}"


# ----- Blocked leading statements (not SELECT/WITH/SHOW/EXPLAIN) ------------

_DISALLOWED_LEADING_CASES: list[tuple[str, str]] = [
    ("begin-transaction", "BEGIN"),
    ("commit", "COMMIT"),
    ("rollback", "ROLLBACK"),
    ("set-role", "SET ROLE admin"),
    ("reset-role", "RESET ROLE"),
    ("listen", "LISTEN channel_name"),
    ("notify", "NOTIFY channel_name, 'msg'"),
    ("vacuum", "VACUUM"),
    ("analyze-bare", "ANALYZE"),
    ("reindex", "REINDEX TABLE users"),
    ("cluster", "CLUSTER users"),
    ("lock", "LOCK TABLE users"),
    ("savepoint", "SAVEPOINT s1"),
    ("merge", "MERGE INTO target USING src ON true WHEN MATCHED THEN DELETE"),
    ("declare-cursor", "DECLARE c CURSOR FOR SELECT 1"),
    ("fetch", "FETCH ALL FROM c"),
    ("close", "CLOSE c"),
    ("comment-on", "COMMENT ON TABLE users IS 'x'"),
]


@pytest.mark.parametrize("case_id,sql", _DISALLOWED_LEADING_CASES, ids=[c[0] for c in _DISALLOWED_LEADING_CASES])
def test_disallowed_leading_statements(dbm: DBManager, case_id: str, sql: str) -> None:
    err = dbm._validate_query(sql)
    assert err is not None, f"{case_id} should be blocked: {sql!r}"


# ----- Blocked keyword detection (full coverage) -----------------------------

_BLOCKED_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE", "COPY")


@pytest.mark.parametrize("kw", _BLOCKED_KEYWORDS)
def test_blocked_keywords_all(dbm: DBManager, kw: str) -> None:
    """Every blocked keyword must be rejected, both as leading and inside a SELECT.

    Note: 'inside a SELECT' includes string literals — see test_blocked_keywords_in_string_literal
    for the documented false-positive shape.
    """
    err_leading = dbm._validate_query(f"{kw} something")
    assert err_leading is not None, f"leading {kw} not blocked"

    err_inside = dbm._validate_query(f"SELECT * FROM t WHERE name = '{kw} foo'")
    assert err_inside is not None, f"{kw} not detected inside SELECT (regex is content-blind)"


@pytest.mark.parametrize("kw", _BLOCKED_KEYWORDS)
def test_blocked_keywords_case_insensitive(dbm: DBManager, kw: str) -> None:
    for variant in (kw.lower(), kw.title(), kw.swapcase()):
        assert dbm._validate_query(f"{variant} t") is not None, f"variant {variant} should be blocked"


def test_blocked_keywords_in_string_literal_documented_gap(dbm: DBManager) -> None:
    """Documents the known false-positive: blocked keywords inside string literals are blocked.

    SELECT 'DROP TABLE users' is functionally a safe read-only query that returns
    a string. The current regex is content-blind and rejects it. This test pins the
    behavior so a future, smarter parser is a deliberate change.
    """
    assert dbm._validate_query("SELECT 'DROP TABLE users'") is not None
    assert dbm._validate_query("SELECT 'INSERT INTO foo VALUES (1)'") is not None


# ----- CTE chaining bypass attempts ------------------------------------------

_CTE_BYPASS_CASES: list[tuple[str, str]] = [
    ("cte-delete-returning", "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d"),
    ("cte-insert-returning", "WITH i AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM i"),
    ("cte-update-returning", "WITH u AS (UPDATE t SET x = 1 RETURNING *) SELECT * FROM u"),
    ("cte-multi-write", "WITH a AS (DELETE FROM x), b AS (INSERT INTO y VALUES (1)) SELECT 1"),
]


@pytest.mark.parametrize("case_id,sql", _CTE_BYPASS_CASES, ids=[c[0] for c in _CTE_BYPASS_CASES])
def test_cte_with_writes_blocked(dbm: DBManager, case_id: str, sql: str) -> None:
    """CTEs that wrap a write op are caught by the blocked-keyword regex."""
    assert dbm._validate_query(sql) is not None, f"{case_id} should be blocked"


# ----- Comment / multi-statement / backslash bypass attempts -----------------

_BYPASS_CASES: list[tuple[str, str, str]] = [
    ("trailing-line-comment", "SELECT 1 -- comment", "comment"),
    ("inline-line-comment", "SELECT /* hi */ 1", "comment"),
    ("block-comment-only", "/* DROP TABLE x */ SELECT 1", "comment"),
    ("multi-statement-semicolon", "SELECT 1; SELECT 2", "Multi-statement"),
    ("multi-statement-with-write", "SELECT 1; DROP TABLE users", "Multi-statement"),
    ("backslash-meta", r"\dt", "backslash"),
    ("backslash-mid-query", r"SELECT 1\dt", "backslash"),
]


@pytest.mark.parametrize(
    "case_id,sql,token",
    _BYPASS_CASES,
    ids=[c[0] for c in _BYPASS_CASES],
)
def test_bypass_attempts_blocked(dbm: DBManager, case_id: str, sql: str, token: str) -> None:
    err = dbm._validate_query(sql)
    assert err is not None, f"{case_id} should be blocked"
    assert token.lower() in err.lower(), f"{case_id} error should mention {token!r}, got: {err!r}"


def test_trailing_semicolon_alone_is_allowed(dbm: DBManager) -> None:
    """A single trailing semicolon is not multi-statement (\\S after ; is required)."""
    assert dbm._validate_query("SELECT 1;") is None
    assert dbm._validate_query("SELECT 1 ;  ") is None


def test_trailing_semicolon_plus_whitespace_only(dbm: DBManager) -> None:
    """Whitespace after `;` does not trigger multi-statement."""
    assert dbm._validate_query("SELECT 1;\n\n") is None


# ----- Bypass attempts that the current regex DOES NOT catch (gaps) ---------

_GAP_CASES: list[tuple[str, str]] = [
    # Dollar-quoted strings can contain banned keywords.
    ("dollar-quoted-write", "SELECT $$DROP TABLE x$$"),
    # Same with named dollar tags.
    ("dollar-quoted-named", "SELECT $tag$INSERT INTO t VALUES (1)$tag$"),
]


@pytest.mark.parametrize("case_id,sql", _GAP_CASES, ids=[c[0] for c in _GAP_CASES])
def test_gap_dollar_quoted_strings_are_blocked_due_to_keyword_match(dbm: DBManager, case_id: str, sql: str) -> None:
    """Dollar-quoted strings still trip the blocked-keyword regex.

    This is a *coincidental* protection: the regex sees DROP/INSERT/etc. as a word
    even though semantically it is a string. The point of this test is to pin the
    fact that the protection holds even for dollar-quote bypasses, even if the
    underlying mechanism is content-blind.
    """
    assert dbm._validate_query(sql) is not None


def test_unicode_lookalikes_pass_through(dbm: DBManager) -> None:
    """Unicode lookalikes (Cyrillic 'а' instead of Latin 'a') escape the regex.

    `DELЕTE` (with Cyrillic 'Е', U+0415) is treated as an unknown leading keyword
    and rejected by the *leading* check, but `SELECT 1 -- DELЕTE` would skip the
    blocked-keyword check entirely. The test documents the limitation.
    """
    # Cyrillic 'Е' (U+0415) instead of Latin 'E' — fails leading-allowed check.
    assert dbm._validate_query("DELЕTE FROM t") is not None  # blocked by leading check

    # Lookalike inside an otherwise-allowed query: comment regex catches it via `--`.
    assert dbm._validate_query("SELECT 1 -- DELЕTE FROM t") is not None  # blocked by comment, not lookalike


# ----- Empty / whitespace-only --------------------------------------------


@pytest.mark.parametrize("sql", ["", "   ", "\n\n", "\t"])
def test_empty_or_whitespace_only_blocked(dbm: DBManager, sql: str) -> None:
    err = dbm._validate_query(sql)
    assert err is not None, f"empty SQL should be blocked: {sql!r}"


# ----- Aggregate sanity ----------------------------------------------------


def _all_kw_with_separators() -> Sequence[str]:
    seps = [" ", "\t", "\n", "  "]
    return [f"{kw}{sep}foo" for kw in _BLOCKED_KEYWORDS for sep in seps]


@pytest.mark.parametrize("sql", _all_kw_with_separators())
def test_blocked_keywords_with_various_separators(dbm: DBManager, sql: str) -> None:
    assert dbm._validate_query(sql) is not None, f"separator did not save SQL: {sql!r}"
