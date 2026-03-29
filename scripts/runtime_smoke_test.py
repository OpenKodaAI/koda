#!/usr/bin/env python3
"""Run an operational smoke test for the isolated runtime backend."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("AGENT_TOKEN", "runtime-smoke-token")
os.environ.setdefault("ALLOWED_USER_IDS", "111")
os.environ.setdefault("DEFAULT_WORK_DIR", tempfile.gettempdir())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=None,
        help="Directory used for the smoke runtime artifacts. Defaults to runtime_smoke/<timestamp>.",
    )
    parser.add_argument(
        "--browser-live",
        action="store_true",
        help="Also validate the real browser live stack (Xvfb/noVNC/Playwright) if available.",
    )
    parser.add_argument(
        "--require-browser-live",
        action="store_true",
        help="Fail if browser live cannot be verified on this machine.",
    )
    parser.add_argument(
        "--shell",
        default=None,
        help="Interactive shell used for the operator PTY smoke step. Defaults to $SHELL or /bin/bash.",
    )
    return parser


def main() -> int:
    from koda.services.runtime.smoke import run_runtime_smoke

    parser = _build_parser()
    args = parser.parse_args()
    runtime_root = args.runtime_root or (Path.cwd() / "runtime_smoke" / time.strftime("%Y%m%d-%H%M%S"))
    result = asyncio.run(
        run_runtime_smoke(
            runtime_root=runtime_root,
            include_browser_live=args.browser_live,
            require_browser_live=args.require_browser_live,
            shell=args.shell,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
