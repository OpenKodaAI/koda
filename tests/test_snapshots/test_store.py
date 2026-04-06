"""Tests for snapshot store: save, load, list, delete, diff."""

import os

import pytest

from koda.snapshots.store import SnapshotStore


@pytest.fixture()
def store(tmp_path):
    s = SnapshotStore()
    s._base_dir = str(tmp_path)
    return s


SCOPE = 42


class TestSave:
    @pytest.mark.asyncio
    async def test_save_and_load(self, store):
        data = {"scope_id": SCOPE, "subsystems": {"filesystem": {"count": 3}}}
        err = await store.save(SCOPE, "test1", data)
        assert err is None
        loaded = store.load(SCOPE, "test1")
        assert isinstance(loaded, dict)
        assert loaded["subsystems"]["filesystem"]["count"] == 3

    @pytest.mark.asyncio
    async def test_save_invalid_name(self, store):
        err = await store.save(SCOPE, "bad name!", {})
        assert err is not None
        assert "Invalid" in err

    @pytest.mark.asyncio
    async def test_save_empty_name(self, store):
        err = await store.save(SCOPE, "", {})
        assert err is not None

    @pytest.mark.asyncio
    async def test_file_permissions(self, store, tmp_path):
        await store.save(SCOPE, "perm-test", {"x": 1})
        d = store._get_dir(SCOPE)
        path = os.path.join(d, "perm-test.json")
        mode = oct(os.stat(path).st_mode & 0o777)
        assert mode == "0o600"


class TestLoad:
    def test_load_missing(self, store):
        result = store.load(SCOPE, "nope")
        assert isinstance(result, str)
        assert "not found" in result

    def test_load_invalid_name(self, store):
        result = store.load(SCOPE, "bad name!")
        assert isinstance(result, str)
        assert "Invalid" in result


class TestList:
    def test_list_empty(self, store):
        snapshots = store.list_snapshots(SCOPE)
        assert snapshots == []

    @pytest.mark.asyncio
    async def test_list_with_snapshots(self, store):
        await store.save(SCOPE, "alpha", {"a": 1})
        await store.save(SCOPE, "beta", {"b": 2})
        snapshots = store.list_snapshots(SCOPE)
        assert len(snapshots) == 2
        names = [s["name"] for s in snapshots]
        assert "alpha" in names
        assert "beta" in names
        for s in snapshots:
            assert "size" in s
            assert "age_hours" in s


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_existing(self, store):
        await store.save(SCOPE, "del-me", {"x": 1})
        err = store.delete(SCOPE, "del-me")
        assert err is None
        result = store.load(SCOPE, "del-me")
        assert isinstance(result, str)
        assert "not found" in result

    def test_delete_missing(self, store):
        err = store.delete(SCOPE, "nope")
        assert err is not None
        assert "not found" in err

    def test_delete_invalid_name(self, store):
        err = store.delete(SCOPE, "bad name!")
        assert err is not None
        assert "Invalid" in err


class TestDiff:
    @pytest.mark.asyncio
    async def test_diff_identical(self, store):
        data = {"subsystems": {"fs": {"count": 1}}}
        await store.save(SCOPE, "a", data)
        await store.save(SCOPE, "b", data)
        result = store.diff(SCOPE, "a", "b")
        assert isinstance(result, dict)
        assert result["changes"] == {}

    @pytest.mark.asyncio
    async def test_diff_changed(self, store):
        await store.save(SCOPE, "before", {"subsystems": {"fs": {"count": 1}}})
        await store.save(SCOPE, "after", {"subsystems": {"fs": {"count": 5}}})
        result = store.diff(SCOPE, "before", "after")
        assert isinstance(result, dict)
        assert result["changes"]["fs"]["status"] == "changed"

    @pytest.mark.asyncio
    async def test_diff_added_removed(self, store):
        await store.save(SCOPE, "x", {"subsystems": {"fs": {}}})
        await store.save(SCOPE, "y", {"subsystems": {"browser": {}}})
        result = store.diff(SCOPE, "x", "y")
        assert isinstance(result, dict)
        assert result["changes"]["fs"]["status"] == "removed"
        assert result["changes"]["browser"]["status"] == "added"

    @pytest.mark.asyncio
    async def test_diff_missing_snapshot(self, store):
        await store.save(SCOPE, "exists", {"subsystems": {}})
        result = store.diff(SCOPE, "exists", "nope")
        assert isinstance(result, str)
        assert "not found" in result
