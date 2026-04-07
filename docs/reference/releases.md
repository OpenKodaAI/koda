# Release Distribution

Koda ships one product release contract across npm, GHCR, and GitHub Releases.

## Official Download Channels

- npm package: `@openkodaai/koda`
- executable command after install: `koda`
- container images: `ghcr.io/openkodaai/koda-app`, `ghcr.io/openkodaai/koda-web`, `ghcr.io/openkodaai/koda-memory`, `ghcr.io/openkodaai/koda-security`
- release archive: `koda-<version>.tar.gz`

Install or update through npm:

```bash
npm install -g @openkodaai/koda
koda install
```

Or run it directly:

```bash
npx @openkodaai/koda@latest install
npx @openkodaai/koda@latest update
```

The npm package contains only the product-facing CLI and the product-only release bundle. It does not ship the
source tree, tests, CI helpers, or development overlays.

## Version Source Of Truth

Release versioning is anchored to [`pyproject.toml`](../../pyproject.toml).

The release metadata sync step keeps these files aligned to that version:

- [`../../koda/__init__.py`](../../koda/__init__.py)
- [`../../packages/cli/package.json`](../../packages/cli/package.json)
- [`../../packages/cli/release/manifest.json`](../../packages/cli/release/manifest.json)
- [`../../packages/cli/release/bundle/sbom.spdx.json`](../../packages/cli/release/bundle/sbom.spdx.json)
- [`../../docs/openapi/control-plane.json`](../../docs/openapi/control-plane.json)

Run:

```bash
python3 scripts/release_metadata.py
python3 scripts/release_metadata.py --write
```

## Release Workflow

The release workflow is designed to publish only after these gates pass:

1. quality: `ruff`, format check, `mypy`, `pytest --cov`, web lint/test/build, repo-map/docs hygiene, Rust checks
2. security: dependency audits, Bandit, Gitleaks, CodeQL, and container scanning
3. Docker smoke: the stack boots and serves health, dashboard, and control-plane surfaces
4. packaged-install smoke: the release CLI is packed with `npm pack`, installed from its tarball, and must complete `install`, `doctor`, `auth issue-code`, `update`, and `uninstall`

Only after those gates pass does the workflow:

- push the versioned GHCR images
- publish the scoped npm package with provenance
- create a GitHub Release with the bundle archive, manifest, checksums, SBOM, and npm tarball

## Artifact Build Commands

Build the releasable assets locally:

```bash
python3 scripts/build_release_artifacts.py --output-dir dist/release-artifacts
```

This creates:

- `release/koda-<version>/`
- `release/koda-<version>.tar.gz`
- `npm/<packed-cli>.tgz`
- `SHA256SUMS.txt`
- `release-artifacts.json`

## Packaged Smoke Test

To validate the published-install path from the npm tarball:

```bash
python3 scripts/release_smoke_test.py \
  --cli-tarball dist/release-artifacts/npm/<packed-cli>.tgz
```

The smoke test builds the local release images with the tags declared in the manifest, installs the CLI tarball
into a temporary npm prefix, and verifies the operator flow without needing the source repository as the runtime.

## Required Secrets And Permissions

The publish workflow expects:

- GitHub `packages: write` for GHCR
- GitHub `contents: write` for the GitHub Release
- GitHub `id-token: write` for npm provenance
- npm authentication configured for the `@openkodaai` scope

The preferred npm path is trusted publishing tied to the repository workflow itself. If that path is not yet
configured and the repository Actions secret `NPM_TOKEN` is present, the workflow falls back to that token only
after the trusted-publishing attempt fails.

Recommended GitHub setup:

- protect a `release` environment and require manual approval if your team wants a final human gate
- configure npm trusted publishing for `OpenKodaAI/koda` and [release.yml](../../.github/workflows/release.yml)
- keep `NPM_TOKEN` only as a fallback or transition mechanism if trusted publishing is not enabled yet

If a fork or dry-run cannot publish, the workflow should still complete all validation and artifact build steps
without pushing npm or GHCR assets.
