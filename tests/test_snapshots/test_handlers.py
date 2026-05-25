"""Tests for snapshot tool dispatcher handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import ToolContext


def _make_ctx(**overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir="/tmp",
        user_data={
            "work_dir": "/tmp",
            "model": "claude-sonnet-4-6",
            "session_id": "sess-1",
            "total_cost": 0.0,
            "query_count": 5,
        },
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


class TestSnapshotDisabled:
    """All snapshot handlers should return failure when SNAPSHOT_ENABLED is False."""

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", False)
    async def test_save_disabled(self):
        from koda.services.tool_dispatcher import _handle_snapshot_save

        result = await _handle_snapshot_save({"name": "test"}, _make_ctx())
        assert not result.success
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", False)
    async def test_restore_disabled(self):
        from koda.services.tool_dispatcher import _handle_snapshot_restore

        result = await _handle_snapshot_restore({"name": "test"}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", False)
    async def test_list_disabled(self):
        from koda.services.tool_dispatcher import _handle_snapshot_list

        result = await _handle_snapshot_list({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", False)
    async def test_diff_disabled(self):
        from koda.services.tool_dispatcher import _handle_snapshot_diff

        result = await _handle_snapshot_diff({"from": "a", "to": "b"}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", False)
    async def test_delete_disabled(self):
        from koda.services.tool_dispatcher import _handle_snapshot_delete

        result = await _handle_snapshot_delete({"name": "test"}, _make_ctx())
        assert not result.success


class TestSnapshotMissingParams:
    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", True)
    async def test_save_missing_name(self):
        from koda.services.tool_dispatcher import _handle_snapshot_save

        result = await _handle_snapshot_save({}, _make_ctx())
        assert not result.success
        assert "Missing" in result.output

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", True)
    async def test_restore_missing_name(self):
        from koda.services.tool_dispatcher import _handle_snapshot_restore

        result = await _handle_snapshot_restore({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", True)
    async def test_diff_missing_params(self):
        from koda.services.tool_dispatcher import _handle_snapshot_diff

        result = await _handle_snapshot_diff({"from": "a"}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", True)
    async def test_delete_missing_name(self):
        from koda.services.tool_dispatcher import _handle_snapshot_delete

        result = await _handle_snapshot_delete({}, _make_ctx())
        assert not result.success


class TestSnapshotSuccess:
    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", True)
    async def test_save_and_restore(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_snapshot_restore, _handle_snapshot_save
        from koda.snapshots.store import get_snapshot_store

        store = get_snapshot_store()
        store._base_dir = str(tmp_path)

        ctx = _make_ctx(work_dir=str(tmp_path))
        result = await _handle_snapshot_save({"name": "test-snap"}, ctx)
        assert result.success
        assert "test-snap" in result.output

        result = await _handle_snapshot_restore({"name": "test-snap"}, ctx)
        assert result.success
        assert "test-snap" in result.output
        # Reset store
        store._base_dir = ""

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", True)
    async def test_list_snapshots(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_snapshot_list, _handle_snapshot_save
        from koda.snapshots.store import get_snapshot_store

        store = get_snapshot_store()
        store._base_dir = str(tmp_path)

        ctx = _make_ctx(work_dir=str(tmp_path))
        await _handle_snapshot_save({"name": "snap-a"}, ctx)
        result = await _handle_snapshot_list({}, ctx)
        assert result.success
        assert "snap-a" in result.output
        store._base_dir = ""

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", True)
    async def test_delete_snapshot(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_snapshot_delete, _handle_snapshot_save
        from koda.snapshots.store import get_snapshot_store

        store = get_snapshot_store()
        store._base_dir = str(tmp_path)

        ctx = _make_ctx(work_dir=str(tmp_path))
        await _handle_snapshot_save({"name": "to-delete"}, ctx)
        result = await _handle_snapshot_delete({"name": "to-delete"}, ctx)
        assert result.success
        assert "deleted" in result.output
        store._base_dir = ""

    @pytest.mark.asyncio
    @patch("koda.services.tool_dispatcher.SNAPSHOT_ENABLED", True)
    async def test_diff_snapshots(self, tmp_path):
        from koda.services.tool_dispatcher import _handle_snapshot_diff, _handle_snapshot_save
        from koda.snapshots.store import get_snapshot_store

        store = get_snapshot_store()
        store._base_dir = str(tmp_path)

        ctx = _make_ctx(work_dir=str(tmp_path))
        await _handle_snapshot_save({"name": "before"}, ctx)
        await _handle_snapshot_save({"name": "after"}, ctx)
        result = await _handle_snapshot_diff({"from": "before", "to": "after"}, ctx)
        assert result.success
        store._base_dir = ""
