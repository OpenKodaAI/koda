#!/usr/bin/env python3
"""Assemble the product-only release bundle shipped by the npm CLI."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from release_metadata import build_manifest, build_release_checksums, build_sbom, sync_release_metadata

ROOT = Path(__file__).resolve().parents[1]
CLI_RELEASE_ROOT = ROOT / "packages" / "cli" / "release"


def utc_now_rfc3339() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_manifest(*, published_at: str | None = None) -> dict[str, object]:
    version_drift = sync_release_metadata(write=False)
    if version_drift:
        drift_list = ", ".join(path.relative_to(ROOT).as_posix() for path in version_drift)
        raise RuntimeError(f"release metadata drift detected: {drift_list}")

    metadata = build_manifest(
        str(json.loads((CLI_RELEASE_ROOT / "manifest.json").read_text(encoding="utf-8"))["version"]),
        published_at=published_at,
    )
    return metadata


def build_release_bundle(
    output_dir: Path, *, published_at: str | None = None, archive: bool = False
) -> tuple[Path, Path | None]:
    manifest = load_manifest(published_at=published_at)
    version = str(manifest["version"])
    bundle_dir = output_dir / f"koda-{version}"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(CLI_RELEASE_ROOT / "bundle", bundle_dir / "bundle")
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    sbom = build_sbom(version, created_at=str(manifest["published_at"]))
    (bundle_dir / "bundle" / "sbom.spdx.json").write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    (bundle_dir / "CHECKSUMS.txt").write_text(
        build_release_checksums(version, published_at=str(manifest["published_at"])),
        encoding="utf-8",
    )

    archive_path: Path | None = None
    if archive:
        archive_base = output_dir / bundle_dir.name
        archive_file = shutil.make_archive(str(archive_base), "gztar", root_dir=output_dir, base_dir=bundle_dir.name)
        archive_path = Path(archive_file)

    return bundle_dir, archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "dist" / "release"),
        help="Directory where the assembled release bundle will be written.",
    )
    parser.add_argument(
        "--published-at",
        default=None,
        help="RFC3339 timestamp written into the copied manifest and SBOM. Defaults to the current UTC time.",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Also create a tar.gz archive of the built release directory.",
    )
    args = parser.parse_args()
    published_at = args.published_at or utc_now_rfc3339()
    bundle_dir, archive_path = build_release_bundle(
        Path(args.output_dir).resolve(),
        published_at=published_at,
        archive=args.archive,
    )
    print(bundle_dir)
    if archive_path is not None:
        print(archive_path)


if __name__ == "__main__":
    main()
