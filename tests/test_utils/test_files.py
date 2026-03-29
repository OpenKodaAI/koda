"""Tests for file operations with path traversal protection."""

from koda.utils.files import list_directory, safe_resolve


class TestSafeResolve:
    def test_relative_path_inside(self, tmp_path):
        (tmp_path / "file.txt").touch()
        result = safe_resolve("file.txt", str(tmp_path))
        assert result is not None
        assert result.name == "file.txt"

    def test_absolute_path_inside(self, tmp_path):
        target = tmp_path / "file.txt"
        target.touch()
        result = safe_resolve(str(target), str(tmp_path))
        assert result is not None

    def test_traversal_blocked(self, tmp_path):
        result = safe_resolve("../../etc/passwd", str(tmp_path))
        assert result is None

    def test_absolute_path_outside(self, tmp_path):
        result = safe_resolve("/etc/passwd", str(tmp_path))
        assert result is None

    def test_subdirectory(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").touch()
        result = safe_resolve("sub/file.txt", str(tmp_path))
        assert result is not None
        assert result.name == "file.txt"


class TestListDirectory:
    def test_list_work_dir(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b").mkdir()
        listing, success = list_directory(None, str(tmp_path))
        assert success
        assert "a.txt" in listing
        assert "b/" in listing

    def test_list_subdirectory(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").touch()
        listing, success = list_directory("sub", str(tmp_path))
        assert success
        assert "file.txt" in listing

    def test_traversal_denied(self, tmp_path):
        listing, success = list_directory("../../etc", str(tmp_path))
        assert not success
        assert "Access denied" in listing

    def test_not_found(self, tmp_path):
        listing, success = list_directory("nonexistent", str(tmp_path))
        assert not success

    def test_empty_directory(self, tmp_path):
        sub = tmp_path / "empty"
        sub.mkdir()
        listing, success = list_directory("empty", str(tmp_path))
        assert success
        assert "empty" in listing.lower()
