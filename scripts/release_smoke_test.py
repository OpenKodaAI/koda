#!/usr/bin/env python3
"""Smoke-test the packaged npm CLI against the release bundle contract."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(
    cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        check=True,
        text=True,
        capture_output=True,
        env=merged_env,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_local_release_images(manifest: dict[str, object]) -> None:
    images = manifest["images"]
    run(["docker", "build", "-t", str(images["app"]), "."], cwd=ROOT)
    run(["docker", "build", "-f", "apps/web/Dockerfile", "-t", str(images["web"]), "."], cwd=ROOT)
    run(["docker", "build", "-f", "Dockerfile.memory", "-t", str(images["memory"]), "."], cwd=ROOT)
    run(["docker", "build", "-f", "Dockerfile.security", "-t", str(images["security"]), "."], cwd=ROOT)


def install_cli(cli_tarball: Path, prefix_dir: Path) -> Path:
    run(["npm", "install", "--global", "--prefix", str(prefix_dir), str(cli_tarball)], cwd=ROOT)
    koda_bin = prefix_dir / "bin" / "koda"
    if not koda_bin.exists():
        raise RuntimeError(f"Expected CLI binary at {koda_bin}")
    return koda_bin


def run_smoke(
    cli_tarball: Path, install_dir: Path, *, prefix_dir: Path | None = None, build_images: bool = True
) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="koda-release-smoke-", dir=str(ROOT / "output")))
    prefix = prefix_dir or (temp_root / "npm-prefix")
    manifest = read_json(ROOT / "packages" / "cli" / "release" / "manifest.json")
    koda_bin = None

    try:
        if build_images:
            build_local_release_images(manifest)
        prefix.mkdir(parents=True, exist_ok=True)
        install_dir.mkdir(parents=True, exist_ok=True)
        koda_bin = install_cli(cli_tarball, prefix)

        run([str(koda_bin), "version", "--dir", str(install_dir)], cwd=ROOT)
        run([str(koda_bin), "install", "--dir", str(install_dir), "--headless"], cwd=ROOT, env={"CI": "true"})
        run([str(koda_bin), "doctor", "--dir", str(install_dir)], cwd=ROOT)
        run([str(koda_bin), "auth", "issue-code", "--dir", str(install_dir)], cwd=ROOT)
        run([str(koda_bin), "update", "--dir", str(install_dir)], cwd=ROOT, env={"CI": "true"})
        run([str(koda_bin), "uninstall", "--dir", str(install_dir), "--purge"], cwd=ROOT)
    finally:
        if koda_bin is not None:
            with suppress(Exception):
                run([str(koda_bin), "down", "--dir", str(install_dir)], cwd=ROOT)
            with suppress(Exception):
                run([str(koda_bin), "uninstall", "--dir", str(install_dir), "--purge"], cwd=ROOT)
        shutil.rmtree(temp_root, ignore_errors=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli-tarball", type=Path, required=True, help="Path to the packed npm CLI tarball.")
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=ROOT / "output" / "release-smoke-install",
        help="Directory where the CLI should install the product bundle during the smoke test.",
    )
    parser.add_argument(
        "--prefix-dir",
        type=Path,
        default=None,
        help="Optional npm global prefix to use instead of a temporary one.",
    )
    parser.add_argument(
        "--skip-build-images",
        action="store_true",
        help="Reuse already-built local images instead of building them before the smoke run.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    run_smoke(
        args.cli_tarball.resolve(),
        args.install_dir.resolve(),
        prefix_dir=args.prefix_dir.resolve() if args.prefix_dir else None,
        build_images=not args.skip_build_images,
    )


if __name__ == "__main__":
    main()
