#!/usr/bin/env python3
"""Fill the ``replace-with-...`` placeholders of a Koda ``.env`` with random secrets.

Koda never authenticates with an unedited ``.env.example`` placeholder, so a
manual install must replace them before the first start.

* New install (no ``.env`` yet): creates ``.env`` from ``.env.example`` with
  mode 0600 and replaces every placeholder.
* Existing install: replaces only the authentication placeholders
  (``CONTROL_PLANE_API_TOKEN``, ``RUNTIME_LOCAL_UI_TOKEN``,
  ``WEB_OPERATOR_SESSION_SECRET``). Postgres and object-storage values must keep
  matching the data already on disk, so they are rotated in those services
  first; pass ``--all`` to replace their placeholders too. Values that were
  already customised are never touched, so re-running is safe.

Only key names are printed, never values.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

PLACEHOLDER_PREFIX = "replace-with-"
PLACEHOLDER_LINE = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>replace-with-[A-Za-z0-9-]*)[ \t]*$", re.MULTILINE)
AUTH_KEYS = frozenset({"CONTROL_PLANE_API_TOKEN", "RUNTIME_LOCAL_UI_TOKEN", "WEB_OPERATOR_SESSION_SECRET"})
# Object-storage access key ids are conventionally 20 alphanumeric characters.
SHORT_KEYS = frozenset({"S3_ACCESS_KEY_ID"})


def _random_value(key: str) -> str:
    return secrets.token_hex(10 if key in SHORT_KEYS else 24)


def fill_placeholders(text: str, *, auth_only: bool = False) -> tuple[str, list[str]]:
    """Return *text* with placeholders replaced and the list of replaced keys."""
    replaced: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        key = match.group("key")
        if auth_only and key not in AUTH_KEYS:
            return match.group(0)
        replaced.append(key)
        return f"{key}={_random_value(key)}"

    return PLACEHOLDER_LINE.sub(_replace, text), replaced


def remaining_placeholders(text: str) -> list[str]:
    """Keys whose value is still a placeholder in any form Koda would reject
    (quoted, upper-case, ``export KEY=...``, trailing comments)."""
    keys: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.split(" #", 1)[0].strip().strip("'\"").strip()
        if value.lower().startswith(PLACEHOLDER_PREFIX):
            keys.append(key)
    return keys


def _write_private(path: Path, text: str) -> None:
    """Atomically replace *path* with *text*, mode 0600 from the first byte."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", default=".env", type=Path)
    parser.add_argument("--template", default=".env.example", type=Path)
    parser.add_argument(
        "--all",
        action="store_true",
        help="on an existing .env, also replace Postgres and object-storage placeholders",
    )
    args = parser.parse_args(argv)

    env_file: Path = args.env_file
    existing = env_file.exists()
    if existing:
        text = env_file.read_text(encoding="utf-8")
    elif args.template.exists():
        text = args.template.read_text(encoding="utf-8")
    else:
        print(f"error: neither {env_file} nor {args.template} exists", file=sys.stderr)
        return 1

    updated, replaced = fill_placeholders(text, auth_only=existing and not args.all)
    if existing and not replaced:
        os.chmod(env_file, 0o600)
        print(f"{env_file}: no placeholders replaced")
    else:
        _write_private(env_file, updated)
        print(f"{env_file}: generated {', '.join(replaced) if replaced else 'no values'} (mode 0600)")

    remaining = remaining_placeholders(updated)
    if remaining:
        print(
            f"{env_file}: placeholders still present (Koda treats them as unset): {', '.join(remaining)}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
