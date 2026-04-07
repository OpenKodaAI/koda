#!/usr/bin/env python3
"""Build the publishable npm and GitHub release artifacts for Koda."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from build_release_bundle import build_release_bundle
from release_metadata import NPM_PACKAGE_NAME, load_release_metadata, sync_release_metadata

ROOT = Path(__file__).resolve().parents[1]
CLI_PACKAGE_DIR = ROOT / "packages" / "cli"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def utc_now_rfc3339() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def build_npm_tarball(output_dir: Path, *, bundle_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stage_dir = output_dir / ".npm-pack-stage"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)

    try:
        shutil.copytree(CLI_PACKAGE_DIR / "bin", stage_dir / "bin")
        shutil.copy2(CLI_PACKAGE_DIR / "package.json", stage_dir / "package.json")
        shutil.copytree(bundle_dir, stage_dir / "release")

        result = run(["npm", "pack", "--pack-destination", str(output_dir)], cwd=stage_dir)
        tarball_name = result.stdout.strip().splitlines()[-1]
        tarball_path = output_dir / tarball_name
        if not tarball_path.exists():
            raise RuntimeError(f"npm pack did not produce {tarball_path}")
        return tarball_path
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def build_release_artifacts(output_dir: Path, *, published_at: str | None = None) -> dict[str, object]:
    drift = sync_release_metadata(write=False)
    if drift:
        raise RuntimeError(
            "release metadata drift detected: " + ", ".join(path.relative_to(ROOT).as_posix() for path in drift)
        )

    published = published_at or utc_now_rfc3339()
    metadata = load_release_metadata(published_at=published)
    release_dir = output_dir / "release"
    npm_dir = output_dir / "npm"
    bundle_dir, bundle_archive = build_release_bundle(release_dir, published_at=published, archive=True)
    if bundle_archive is None:
        raise RuntimeError("build_release_bundle did not return the expected archive path")
    npm_tarball = build_npm_tarball(npm_dir, bundle_dir=bundle_dir)

    asset_paths = [
        bundle_archive,
        bundle_dir / "manifest.json",
        bundle_dir / "CHECKSUMS.txt",
        bundle_dir / "bundle" / "sbom.spdx.json",
        npm_tarball,
    ]
    sha_lines = [f"{sha256_file(path)}  {path.relative_to(output_dir).as_posix()}" for path in asset_paths]
    checksum_path = output_dir / "SHA256SUMS.txt"
    checksum_path.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")

    payload = {
        "published_at": published,
        "version": metadata["version"],
        "product": metadata["product"],
        "npm_package_name": NPM_PACKAGE_NAME,
        "bundle_dir": bundle_dir.relative_to(output_dir).as_posix(),
        "bundle_archive": bundle_archive.relative_to(output_dir).as_posix(),
        "npm_tarball": npm_tarball.relative_to(output_dir).as_posix(),
        "asset_checksums": checksum_path.relative_to(output_dir).as_posix(),
        "manifest": (bundle_dir / "manifest.json").relative_to(output_dir).as_posix(),
        "sbom": (bundle_dir / "bundle" / "sbom.spdx.json").relative_to(output_dir).as_posix(),
        "images": metadata["images"],
    }
    (output_dir / "release-artifacts.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "dist" / "release-artifacts"),
        help="Directory where the built release artifacts should be written.",
    )
    parser.add_argument(
        "--published-at",
        default=None,
        help="Optional RFC3339 timestamp for manifest/SBOM metadata.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    payload = build_release_artifacts(Path(args.output_dir).resolve(), published_at=args.published_at)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
