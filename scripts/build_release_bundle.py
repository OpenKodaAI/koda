#!/usr/bin/env python3
"""Assemble the product-only release bundle shipped by the npm CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_RELEASE_ROOT = ROOT / "packages" / "cli" / "release"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def load_manifest() -> dict[str, object]:
    return json.loads((CLI_RELEASE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def build_release_bundle(output_dir: Path) -> Path:
    manifest = load_manifest()
    version = str(manifest["version"])
    bundle_dir = output_dir / f"koda-{version}"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(CLI_RELEASE_ROOT / "manifest.json", bundle_dir / "manifest.json")
    shutil.copytree(CLI_RELEASE_ROOT / "bundle", bundle_dir / "bundle")

    checksum_lines: list[str] = []
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file() or path.name == "CHECKSUMS.txt":
            continue
        relative_path = path.relative_to(bundle_dir).as_posix()
        checksum_lines.append(f"{sha256_file(path)}  {relative_path}")

    (bundle_dir / "CHECKSUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return bundle_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "dist" / "release"),
        help="Directory where the assembled release bundle will be written.",
    )
    args = parser.parse_args()
    bundle_dir = build_release_bundle(Path(args.output_dir).resolve())
    print(bundle_dir)


if __name__ == "__main__":
    main()
