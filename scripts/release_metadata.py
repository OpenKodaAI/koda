#!/usr/bin/env python3
"""Keep release metadata aligned across package, manifest, docs, and runtime version files."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = ROOT / "pyproject.toml"
PACKAGE_JSON_PATH = ROOT / "packages" / "cli" / "package.json"
MANIFEST_PATH = ROOT / "packages" / "cli" / "release" / "manifest.json"
SBOM_PATH = ROOT / "packages" / "cli" / "release" / "bundle" / "sbom.spdx.json"
OPENAPI_PATH = ROOT / "docs" / "openapi" / "control-plane.json"
INIT_PATH = ROOT / "koda" / "__init__.py"

PRODUCT_NAME = "koda"
NPM_PACKAGE_NAME = "@openkodaai/koda"
NPM_BIN_NAME = "koda"
GHCR_NAMESPACE = "ghcr.io/openkodaai"
UNPUBLISHED_TIMESTAMP = "1970-01-01T00:00:00Z"
REPOSITORY_URL = "https://github.com/OpenKodaAI/koda"

VERSION_RE = re.compile(r'(__version__\s*=\s*")([^"]+)(")')


def load_project_version() -> str:
    payload = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def load_init_version() -> str:
    text = INIT_PATH.read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if match is None:
        raise RuntimeError(f"Could not find __version__ in {INIT_PATH}")
    return match.group(2)


def render_init_text(version: str) -> str:
    text = INIT_PATH.read_text(encoding="utf-8")
    return VERSION_RE.sub(rf"\g<1>{version}\g<3>", text, count=1)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def image_refs(version: str) -> dict[str, str]:
    return {
        "app": f"{GHCR_NAMESPACE}/koda-app:{version}",
        "web": f"{GHCR_NAMESPACE}/koda-web:{version}",
        "memory": f"{GHCR_NAMESPACE}/koda-memory:{version}",
        "security": f"{GHCR_NAMESPACE}/koda-security:{version}",
        "postgres": "pgvector/pgvector:pg16",
        "seaweedfs": "chrislusf/seaweedfs:4.05",
        "awscli": "amazon/aws-cli:2.27.41",
    }


def build_package_json(version: str) -> dict:
    return {
        "name": NPM_PACKAGE_NAME,
        "version": version,
        "description": "Official Koda Docker-first installer and lifecycle CLI",
        "license": "Apache-2.0",
        "type": "module",
        "bin": {
            NPM_BIN_NAME: "./bin/koda.mjs",
        },
        "files": [
            "bin",
            "release",
        ],
        "engines": {
            "node": ">=20",
        },
        "keywords": [
            "koda",
            "ai",
            "agents",
            "control-plane",
            "docker",
        ],
        "repository": {
            "type": "git",
            "url": f"git+{REPOSITORY_URL}.git",
        },
        "homepage": f"{REPOSITORY_URL}#readme",
        "bugs": {
            "url": f"{REPOSITORY_URL}/issues",
        },
        "publishConfig": {
            "access": "public",
            "provenance": True,
        },
    }


def build_manifest(version: str, *, published_at: str | None = None) -> dict:
    current = read_json(MANIFEST_PATH)
    return {
        "schema_version": 1,
        "product": PRODUCT_NAME,
        "version": version,
        "published_at": published_at or str(current.get("published_at") or UNPUBLISHED_TIMESTAMP),
        "distribution": {
            "npm_package": NPM_PACKAGE_NAME,
            "npm_bin": NPM_BIN_NAME,
            "github_release_tag": f"v{version}",
            "release_bundle_archive": f"{PRODUCT_NAME}-{version}.tar.gz",
        },
        "bundle": {
            "compose_file": "bundle/docker-compose.release.yml",
            "env_template": "bundle/.env.bootstrap",
            "migration_notes": "bundle/MIGRATION.md",
            "sbom": "bundle/sbom.spdx.json",
            "proxy_templates": [
                "bundle/proxy/nginx.conf",
            ],
            "checksums_file": "CHECKSUMS.txt",
        },
        "images": image_refs(version),
    }


def build_sbom(version: str, *, created_at: str | None = None) -> dict:
    current = read_json(SBOM_PATH)
    created = created_at or str(current.get("creationInfo", {}).get("created") or UNPUBLISHED_TIMESTAMP)
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "koda-release-bundle",
        "documentNamespace": f"https://openkoda.ai/spdx/koda-release-bundle-{version}",
        "creationInfo": {
            "created": created,
            "creators": [
                "Organization: OpenKodaAI",
            ],
        },
        "packages": [
            {
                "name": "koda-release-bundle",
                "SPDXID": "SPDXRef-Package-KodaReleaseBundle",
                "downloadLocation": "NOASSERTION",
                "licenseConcluded": "Apache-2.0",
                "licenseDeclared": "Apache-2.0",
                "filesAnalyzed": False,
                "versionInfo": version,
                "supplier": "Organization: OpenKodaAI",
            }
        ],
    }


def build_openapi(version: str) -> dict:
    payload = deepcopy(read_json(OPENAPI_PATH))
    payload.setdefault("info", {})["version"] = version
    return payload


def load_release_metadata(*, published_at: str | None = None) -> dict:
    version = load_project_version()
    return {
        "product": PRODUCT_NAME,
        "version": version,
        "npm_package_name": NPM_PACKAGE_NAME,
        "npm_bin_name": NPM_BIN_NAME,
        "ghcr_namespace": GHCR_NAMESPACE,
        "manifest": build_manifest(version, published_at=published_at),
        "sbom": build_sbom(version, created_at=published_at),
        "images": image_refs(version),
    }


def sync_release_metadata(*, write: bool, published_at: str | None = None) -> list[Path]:
    version = load_project_version()
    expected_payloads = {
        PACKAGE_JSON_PATH: dump_json(PACKAGE_JSON_PATH, build_package_json(version)),
        MANIFEST_PATH: dump_json(MANIFEST_PATH, build_manifest(version, published_at=published_at)),
        SBOM_PATH: dump_json(SBOM_PATH, build_sbom(version, created_at=published_at)),
        OPENAPI_PATH: dump_json(OPENAPI_PATH, build_openapi(version)),
        INIT_PATH: render_init_text(version),
    }
    changed: list[Path] = []

    if load_init_version() != version:
        changed.append(INIT_PATH)

    for path, expected_text in expected_payloads.items():
        actual_text = path.read_text(encoding="utf-8")
        if actual_text != expected_text and path not in changed:
            changed.append(path)
        if write and actual_text != expected_text:
            path.write_text(expected_text, encoding="utf-8")

    return changed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="Rewrite files in place to match the canonical release metadata."
    )
    parser.add_argument(
        "--published-at",
        default=None,
        help="Optional RFC3339 timestamp used when materializing manifest/SBOM metadata.",
    )
    parser.add_argument("--json", action="store_true", help="Print the computed canonical metadata as JSON.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.json:
        print(json.dumps(load_release_metadata(published_at=args.published_at), indent=2, ensure_ascii=False))
        return 0

    changed = sync_release_metadata(write=args.write, published_at=args.published_at)
    if changed and not args.write:
        print("Release metadata drift detected in:")
        for path in changed:
            print(f"- {path.relative_to(ROOT).as_posix()}")
        return 1
    if args.write:
        if changed:
            print("Updated release metadata:")
            for path in changed:
                print(f"- {path.relative_to(ROOT).as_posix()}")
        else:
            print("Release metadata already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
