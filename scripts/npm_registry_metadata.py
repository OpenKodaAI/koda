#!/usr/bin/env python3
"""Read npm registry package metadata for release automation."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _load_packument(package_name: str) -> dict[str, Any]:
    url = "https://registry.npmjs.org/" + urllib.parse.quote(package_name, safe="")
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        raise


def _command_exists(args: argparse.Namespace) -> int:
    versions = _load_packument(args.package).get("versions") or {}
    print("true" if args.version in versions else "false")
    return 0


def _command_state(args: argparse.Namespace) -> int:
    payload = _load_packument(args.package)
    versions = payload.get("versions") or {}
    dist_tags = payload.get("dist-tags") or {}
    version_state = str((versions.get(args.version) or {}).get("version", ""))
    dist_tag_version = str(dist_tags.get(args.dist_tag, ""))
    print(version_state)
    print(dist_tag_version)
    return 0


def _command_dist_tags(args: argparse.Namespace) -> int:
    payload = _load_packument(args.package)
    print(json.dumps(payload.get("dist-tags") or {}, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    exists = subparsers.add_parser("exists", help="Return whether a version exists")
    exists.add_argument("--package", required=True)
    exists.add_argument("--version", required=True)
    exists.set_defaults(func=_command_exists)

    state = subparsers.add_parser("state", help="Return package version and dist-tag state")
    state.add_argument("--package", required=True)
    state.add_argument("--version", required=True)
    state.add_argument("--dist-tag", required=True)
    state.set_defaults(func=_command_state)

    dist_tags = subparsers.add_parser("dist-tags", help="Print dist-tags as JSON")
    dist_tags.add_argument("--package", required=True)
    dist_tags.set_defaults(func=_command_dist_tags)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
