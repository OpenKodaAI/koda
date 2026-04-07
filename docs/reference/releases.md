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
2. security: dependency audits, Bandit, Gitleaks, CodeQL, and container scanning that fails on fixable HIGH/CRITICAL findings
3. Docker smoke: the stack boots and serves health, dashboard, and control-plane surfaces
4. packaged-install smoke: the release CLI is packed with `npm pack`, installed from its tarball, and must complete `install`, `doctor`, `auth issue-code`, `update`, and `uninstall`

Only after those gates pass does the workflow:

- push the versioned GHCR images
- publish the scoped npm package with provenance
- create a GitHub Release with the bundle archive, manifest, checksums, SBOM, and npm tarball

Stable releases publish the `latest` tag on npm and the `latest` tag on GHCR. Prereleases publish with the npm
dist-tag `next` and do not overwrite `latest` on the container registry.

## Automatic Release Tag Cut

Merges to `main` do not publish directly. Instead, [`../../.github/workflows/cut-release-tag.yml`](../../.github/workflows/cut-release-tag.yml)
waits for `pr-quality` and `security` to finish successfully on the exact `main` commit.

After those workflows pass, the automation:

- reads the canonical version from `pyproject.toml` and verifies the synced release metadata files
- checks whether the matching semantic tag `v<version>` already exists
- pushes that tag only when it does not already exist
- dispatches [`../../.github/workflows/release.yml`](../../.github/workflows/release.yml) in `publish` mode for that tag

The extra dispatch step is intentional. GitHub does not start a new `push` workflow when a workflow pushes a tag with
the repository `GITHUB_TOKEN`, so `cut-release-tag` explicitly starts the publish run after creating the tag.

This keeps release publication idempotent:

- if `v<version>` already exists on the current commit and the GitHub release already exists, the tag-cut workflow exits without creating a duplicate release
- if `v<version>` already exists on the current commit but the GitHub release is still missing, the tag-cut workflow dispatches `release.yml` again for recovery
- if `v<version>` already exists on an older commit, the workflow exits without retagging or publishing a duplicate package
- to ship a new public release, bump the repository version first, then merge to `main`

For backfills, recovery, or operator-controlled releases, you can still:

- run `cut-release-tag` with `workflow_dispatch`
- run [`../../.github/workflows/release.yml`](../../.github/workflows/release.yml) with `mode=publish` from the ref you want to release
- push a matching `v<version>` tag manually
- run [`../../.github/workflows/release.yml`](../../.github/workflows/release.yml) in `dry-run` mode before publishing

When `release.yml` runs in `publish` mode from `main` or another non-tag ref, it validates the ref, creates
`v<version>` when needed, and then publishes from that same run after all gates pass.

Example manual publish from `main` with GitHub CLI:

```bash
gh workflow run release.yml --ref main -f mode=publish -f release_ref=main
```

Validation-only dry run from `main`:

```bash
gh workflow run release.yml --ref main -f mode=dry-run -f release_ref=main
```

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

The preferred npm path is trusted publishing tied to the automatic caller workflow. In this repository,
`cut-release-tag.yml` is the workflow that dispatches `release.yml`, so npm trusted publishing should be configured
against `OpenKodaAI/koda` and `cut-release-tag.yml`. The `release.yml` publish job still needs `id-token: write`
because it is the workflow that actually runs `npm publish`.

If that path is not yet configured and the repository Actions secret `NPM_TOKEN` is present, the workflow falls
back to that token only after the trusted-publishing attempt fails.

Recommended GitHub setup:

- create a `release` environment in the repository settings before the first public publish
- protect a `release` environment and require manual approval if your team wants a final human gate
- configure npm trusted publishing for `OpenKodaAI/koda` and [cut-release-tag.yml](../../.github/workflows/cut-release-tag.yml)
- keep `NPM_TOKEN` only as a fallback or transition mechanism if trusted publishing is not enabled yet
- use [release.yml](../../.github/workflows/release.yml) directly for dry runs or operator-controlled publish recovery, but
  expect trusted publishing to come from `cut-release-tag.yml` on the automatic path

If a fork or dry-run cannot publish, the workflow should still complete all validation and artifact build steps
without pushing npm or GHCR assets.
