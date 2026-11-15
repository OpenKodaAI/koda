"""The suite runs with ``--strict-markers``, so a mistyped marker fails collection (TD-181, F-QA-13)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _collect(tmp_path: Path, marker: str) -> subprocess.CompletedProcess[str]:
    test_file = tmp_path / f"test_{marker}.py"
    test_file.write_text(f"import pytest\n\n\n@pytest.mark.{marker}\ndef test_marked():\n    pass\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
        + ["-c", str(ROOT / "pyproject.toml"), "--rootdir", str(tmp_path), str(test_file)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
        check=False,
    )


def test_unknown_marker_fails_collection(tmp_path: Path) -> None:
    result = _collect(tmp_path, "postgress")

    assert result.returncode != 0, result.stdout
    assert "'postgress' not found in `markers` configuration option" in result.stdout + result.stderr


def test_declared_marker_collects(tmp_path: Path) -> None:
    result = _collect(tmp_path, "postgres")

    assert result.returncode == 0, result.stdout + result.stderr
