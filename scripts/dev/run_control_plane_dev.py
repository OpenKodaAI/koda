from __future__ import annotations

import os
import site
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
WATCH_PATHS = (
    ROOT_DIR / "koda",
    ROOT_DIR / "agent.py",
    ROOT_DIR / "pyproject.toml",
    ROOT_DIR / "requirements.txt",
    ROOT_DIR / "docs" / "openapi",
)


def ensure_watchfiles() -> None:
    try:
        import watchfiles  # noqa: F401

        return
    except ImportError:
        env = os.environ.copy()
        env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--user", "--no-cache-dir", "watchfiles>=1.1"],
            env=env,
        )
    site.addsitedir(site.getusersitepackages())


def run_control_plane() -> None:
    ensure_watchfiles()
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = str(ROOT_DIR) if not pythonpath else f"{ROOT_DIR}:{pythonpath}"
    subprocess.run([sys.executable, "-m", "koda.control_plane"], cwd=ROOT_DIR, env=env, check=False)


def main() -> None:
    ensure_watchfiles()
    from watchfiles import DefaultFilter, run_process

    class KodaDevFilter(DefaultFilter):
        allowed_suffixes = {".py", ".json", ".md", ".toml", ".txt", ".yaml", ".yml"}
        allowed_names = {".env", ".env.local"}

        def __call__(self, change, path: str) -> bool:
            if not super().__call__(change, path):
                return False
            candidate = Path(path)
            return candidate.name in self.allowed_names or candidate.suffix.lower() in self.allowed_suffixes

    print(f"[koda-dev] watching backend sources from {ROOT_DIR}", flush=True)
    run_process(*WATCH_PATHS, target=run_control_plane, watch_filter=KodaDevFilter())


if __name__ == "__main__":
    main()
