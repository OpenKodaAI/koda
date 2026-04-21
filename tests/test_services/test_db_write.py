"""Tests for database write validation internals in db_manager."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Write query validation
# ---------------------------------------------------------------------------


class TestWriteValidation:
    def test_validate_insert(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("INSERT INTO users (name) VALUES ('Alice')") == ""

    def test_validate_update(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("UPDATE users SET active = true WHERE id = 1") == ""

    def test_validate_delete(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("DELETE FROM sessions WHERE expires_at < now()") == ""

    def test_block_select(self):
        from koda.services.db_manager import _validate_write_query

        assert "INSERT, UPDATE, DELETE" in _validate_write_query("SELECT * FROM users")

    def test_block_drop(self):
        from koda.services.db_manager import _validate_write_query

        result = _validate_write_query("DROP TABLE users")
        assert result != ""

    def test_block_alter(self):
        from koda.services.db_manager import _validate_write_query

        result = _validate_write_query("ALTER TABLE users ADD COLUMN age int")
        assert result != ""

    def test_block_truncate(self):
        from koda.services.db_manager import _validate_write_query

        result = _validate_write_query("TRUNCATE TABLE users")
        assert result != ""

    def test_block_ddl_keyword_in_write(self):
        from koda.services.db_manager import _validate_write_query

        assert "DDL" in _validate_write_query("DELETE FROM users WHERE name = 'DROP TABLE test'")

    def test_block_multi_statement(self):
        from koda.services.db_manager import _validate_write_query

        assert "Multi-statement" in _validate_write_query("DELETE FROM a; DELETE FROM b")

    def test_allow_trailing_semicolon(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("INSERT INTO users (name) VALUES ('x');") == ""

    def test_block_comments_dashes(self):
        from koda.services.db_manager import _validate_write_query

        assert "comments" in _validate_write_query("DELETE FROM users -- all of them")

    def test_block_comments_block(self):
        from koda.services.db_manager import _validate_write_query

        assert "comments" in _validate_write_query("DELETE FROM users /* danger */")

    def test_empty_sql(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("") != ""

    def test_whitespace_only(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("   ") != ""


# ---------------------------------------------------------------------------
# WHERE clause enforcement
# ---------------------------------------------------------------------------


class TestWhereRequired:
    def test_update_without_where(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("UPDATE users SET active = false") is not None

    def test_update_with_where(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("UPDATE users SET active = false WHERE id = 1") is None

    def test_delete_without_where(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("DELETE FROM users") is not None

    def test_delete_with_where(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("DELETE FROM users WHERE id = 1") is None

    def test_insert_no_where_needed(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("INSERT INTO users (name) VALUES ('x')") is None


# ---------------------------------------------------------------------------
# Affected rows parsing
# ---------------------------------------------------------------------------


class TestParseAffectedRows:
    def test_insert(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows("INSERT 0 5") == 5

    def test_update(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows("UPDATE 3") == 3

    def test_delete(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows("DELETE 2") == 2

    def test_none(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows(None) == 0

    def test_empty(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows("") == 0


# ---------------------------------------------------------------------------
# Tool prompt
# ---------------------------------------------------------------------------


class TestDbWritePrompt:
    def test_db_write_tools_not_advertised(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        prompt = build_agent_tools_prompt()
        assert "Database Write" not in prompt
        assert "db_execute" not in prompt
        assert "db_transaction" not in prompt
        assert "db_query" not in prompt
