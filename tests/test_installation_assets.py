"""Tests for Docker-first installation assets and public quickstart docs."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_env_example_is_bootstrap_only() -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    web_env_text = (ROOT / "apps" / "web" / ".env.example").read_text(encoding="utf-8")

    assert "CONTROL_PLANE_API_TOKEN=" in env_text
    assert "RUNTIME_LOCAL_UI_TOKEN=" in env_text
    assert "WEB_OPERATOR_SESSION_SECRET=" in env_text
    assert "WEB_PORT=" in env_text
    assert "POSTGRES_PASSWORD=" in env_text
    assert "KNOWLEDGE_V2_S3_BUCKET=" in env_text
    assert "infrastructure/bootstrap concerns" in env_text
    assert "AGENT_TOKEN=" not in env_text
    assert "ALLOWED_USER_IDS=" not in env_text
    assert "CONTROL_PLANE_MASTER_KEY=" not in env_text
    assert "CONTROL_PLANE_API_TOKEN=" not in web_env_text


def test_docker_compose_quickstart_stack_includes_core_services() -> None:
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    for service_name in ("app:", "web:", "postgres:", "seaweedfs:", "seaweedfs-init:"):
        assert service_name in compose_text
    assert 'command: ["python", "-m", "koda.control_plane"]' in compose_text
    assert 'CONTROL_PLANE_BASE_URL: "http://app:8090"' in compose_text
    assert (
        'WEB_OPERATOR_SESSION_SECRET: "${WEB_OPERATOR_SESSION_SECRET:?Set WEB_OPERATOR_SESSION_SECRET in .env}"'
        in compose_text
    )
    assert "${WEB_PORT:-3000}:3000" in compose_text
    assert "http://seaweedfs:8333" in compose_text
    assert 'CONTROL_PLANE_API_TOKEN: "${CONTROL_PLANE_API_TOKEN:-}"' not in compose_text
    assert (
        "CONTROL_PLANE_API_TOKEN: ${CONTROL_PLANE_API_TOKEN}" not in compose_text.split("web:")[1].split("security:")[0]
    )
    assert "env_file: .env" not in compose_text.split("web:")[1].split("postgres:")[0]
    assert "/api/health" in compose_text
    assert "postgres_password:" not in compose_text
    assert "s3_access_key:" not in compose_text
    assert "s3_secret_key:" not in compose_text


def test_install_script_bootstraps_compose_and_doctor() -> None:
    script_text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert "npm install -g" in script_text
    assert "koda install" in script_text
    assert ".koda-release" in script_text
    assert "/setup?token=" not in script_text
    assert "/release/manifest.json" in script_text


def test_public_docs_cover_quickstart_and_vps() -> None:
    assert (ROOT / "docs" / "README.md").exists()
    assert (ROOT / "docs" / "install" / "local.md").exists()
    assert (ROOT / "docs" / "install" / "vps.md").exists()
    assert (ROOT / "docs" / "install" / "object-storage-migration.md").exists()
    assert (ROOT / "docs" / "config" / "reference.md").exists()
    assert (ROOT / "docs" / "architecture" / "overview.md").exists()
    assert (ROOT / "docs" / "architecture" / "runtime.md").exists()
    assert (ROOT / "docs" / "reference" / "api.md").exists()
    assert (ROOT / "docs" / "reference" / "releases.md").exists()
    assert (ROOT / "CONTRIBUTING.md").exists()
    assert (ROOT / "SECURITY.md").exists()
    assert (ROOT / "CODE_OF_CONDUCT.md").exists()
    assert (ROOT / "LICENSE").exists()
    assert (ROOT / "apps" / "web" / "package.json").exists()
    assert (ROOT / "apps" / "web" / ".env.example").exists()
    assert (ROOT / "apps" / "web" / "Dockerfile").exists()
    assert (ROOT / "packages" / "cli" / "package.json").exists()
    assert (ROOT / "packages" / "cli" / "README.md").exists()
    assert (ROOT / "packages" / "cli" / "bin" / "koda.mjs").exists()
    assert (ROOT / "packages" / "cli" / "release" / "manifest.json").exists()
    assert (ROOT / "scripts" / "build_release_bundle.py").exists()
    assert (ROOT / "scripts" / "build_release_artifacts.py").exists()
    assert (ROOT / "scripts" / "npm_registry_metadata.py").exists()
    assert (ROOT / "scripts" / "release_metadata.py").exists()
    assert (ROOT / "scripts" / "release_smoke_test.py").exists()
    assert (ROOT / "scripts" / "sync_npm_readme.py").exists()
    assert (ROOT / "docs" / "assets" / "brand" / "koda-logo.svg").exists()
    assert (ROOT / "docs" / "assets" / "brand" / "koda-logo.png").exists()
    assert (ROOT / "docs" / "assets" / "brand" / "koda_hero.jpg").exists()
    assert (ROOT / "docs" / "assets" / "brand" / "koda-og.png").exists()
    assert (ROOT / "docs" / "assets" / "screenshots" / "setup.png").exists()

    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_index_text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    local_text = (ROOT / "docs" / "install" / "local.md").read_text(encoding="utf-8")
    vps_text = (ROOT / "docs" / "install" / "vps.md").read_text(encoding="utf-8")

    assert "control-plane-first" in readme_text
    assert "apps/web" in readme_text
    assert "127.0.0.1:3000" in readme_text
    assert "/control-plane/setup" in readme_text
    assert "/control-plane" in readme_text
    assert "?token=" not in readme_text
    assert "npm install -g @openkodaai/koda" in readme_text
    assert "npx @openkodaai/koda@latest install" in readme_text
    assert "seaweedfs" in readme_text.lower()
    assert "Use Koda" in docs_index_text
    assert "apps/web/" in docs_index_text
    assert "/control-plane/setup" in local_text
    assert "koda install" in local_text
    assert "@openkodaai/koda" in local_text
    assert "?token=" not in local_text
    assert "Product configuration stays inside the control-plane UI and API." in vps_text
    assert "The quickstart path does not require per-agent env configuration" in local_text
    assert "koda update" in vps_text
    assert "@openkodaai/koda@latest update" in vps_text


def test_openapi_document_contains_onboarding_paths() -> None:
    payload = json.loads((ROOT / "docs" / "openapi" / "control-plane.json").read_text(encoding="utf-8"))
    assert "/setup" in payload["paths"]
    assert "/api/control-plane/onboarding/status" in payload["paths"]
    assert "/api/control-plane/onboarding/bootstrap" in payload["paths"]
    assert "/api/control-plane/auth/status" in payload["paths"]
    assert "/api/control-plane/auth/bootstrap/exchange" in payload["paths"]
    assert "/api/control-plane/auth/register-owner" in payload["paths"]
    assert "/api/control-plane/auth/login" in payload["paths"]
    assert "/api/control-plane/auth/tokens" in payload["paths"]


def test_npm_cli_release_bundle_contains_product_only_artifacts(tmp_path) -> None:
    bundle_dir = tmp_path / "release"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_release_bundle.py"), "--output-dir", str(bundle_dir)],
        check=True,
        cwd=ROOT,
    )

    built_root = next(bundle_dir.iterdir())
    built_files = sorted(path.relative_to(built_root).as_posix() for path in built_root.rglob("*") if path.is_file())

    assert "manifest.json" in built_files
    assert "CHECKSUMS.txt" in built_files
    assert "bundle/docker-compose.release.yml" in built_files
    assert "bundle/.env.bootstrap" in built_files
    assert "bundle/MIGRATION.md" in built_files
    assert "bundle/sbom.spdx.json" in built_files
    assert "bundle/proxy/nginx.conf" in built_files
    assert not any(path.startswith("tests/") for path in built_files)
    assert not any(path.startswith("docs/ai/") for path in built_files)
    assert not any(".next" in path for path in built_files)
    assert not any("node_modules" in path for path in built_files)


def test_release_compose_carries_bootstrap_and_runtime_tokens_into_app_service() -> None:
    compose_text = (ROOT / "packages" / "cli" / "release" / "bundle" / "docker-compose.release.yml").read_text(
        encoding="utf-8"
    )

    assert 'CONTROL_PLANE_API_TOKEN: "${CONTROL_PLANE_API_TOKEN:?Set CONTROL_PLANE_API_TOKEN in .env}"' in compose_text
    assert 'RUNTIME_LOCAL_UI_TOKEN: "${RUNTIME_LOCAL_UI_TOKEN:?Set RUNTIME_LOCAL_UI_TOKEN in .env}"' in compose_text
    web_block = compose_text.split("  web:")[1].split("  security:")[0]
    assert "CONTROL_PLANE_API_TOKEN" not in web_block
    assert "RUNTIME_LOCAL_UI_TOKEN" not in web_block


def test_release_artifact_build_outputs_bundle_tarball_and_npm_tarball(tmp_path) -> None:
    output_dir = tmp_path / "release-artifacts"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_release_artifacts.py"), "--output-dir", str(output_dir)],
        check=True,
        cwd=ROOT,
    )

    payload = json.loads((output_dir / "release-artifacts.json").read_text(encoding="utf-8"))
    bundle_manifest = json.loads((output_dir / payload["manifest"]).read_text(encoding="utf-8"))
    bundle_checksums = (output_dir / payload["bundle_dir"] / "CHECKSUMS.txt").read_text(encoding="utf-8")

    assert (output_dir / payload["bundle_archive"]).exists()
    assert (output_dir / payload["npm_tarball"]).exists()
    assert (output_dir / payload["asset_checksums"]).exists()
    assert (output_dir / payload["manifest"]).exists()
    assert (output_dir / payload["sbom"]).exists()

    with tarfile.open(output_dir / payload["npm_tarball"], "r:gz") as tarball:
        manifest_from_npm = json.loads(tarball.extractfile("package/release/manifest.json").read().decode("utf-8"))
        checksums_from_npm = tarball.extractfile("package/release/CHECKSUMS.txt").read().decode("utf-8")
        readme_from_npm = tarball.extractfile("package/README.md").read().decode("utf-8")

    assert manifest_from_npm == bundle_manifest
    assert checksums_from_npm == bundle_checksums
    assert "npm install -g @openkodaai/koda" in readme_from_npm
    assert "control-plane/setup" in readme_from_npm


def test_workspace_npm_pack_includes_generated_readme() -> None:
    result = subprocess.run(
        ["npm", "pack", "./packages/cli", "--json", "--dry-run"],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)[0]
    file_paths = {entry["path"] for entry in payload["files"]}

    assert "README.md" in file_paths
    assert "bin/koda.mjs" in file_paths
    assert "release/manifest.json" in file_paths


def test_release_metadata_is_publication_ready() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "release_metadata.py")], check=True, cwd=ROOT)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_npm_readme.py")], check=True, cwd=ROOT)

    package_payload = json.loads((ROOT / "packages" / "cli" / "package.json").read_text(encoding="utf-8"))
    manifest_payload = json.loads((ROOT / "packages" / "cli" / "release" / "manifest.json").read_text(encoding="utf-8"))
    openapi_payload = json.loads((ROOT / "docs" / "openapi" / "control-plane.json").read_text(encoding="utf-8"))
    package_readme = (ROOT / "packages" / "cli" / "README.md").read_text(encoding="utf-8")

    assert package_payload["name"] == "@openkodaai/koda"
    assert package_payload["publishConfig"]["access"] == "public"
    assert package_payload["publishConfig"]["provenance"] is True
    assert package_payload["repository"]["directory"] == "packages/cli"
    assert "README.md" in package_payload["files"]
    assert manifest_payload["distribution"]["npm_package"] == "@openkodaai/koda"
    assert manifest_payload["distribution"]["npm_bin"] == "koda"
    assert manifest_payload["distribution"]["github_release_tag"] == f"v{package_payload['version']}"
    assert openapi_payload["info"]["version"] == package_payload["version"]
    assert package_readme.startswith("<!-- Generated from ../../README.md")
    assert (
        f"https://github.com/OpenKodaAI/koda/blob/v{package_payload['version']}/docs/install/local.md" in package_readme
    )
    assert "http://localhost:3000/control-plane/setup" in package_readme


def test_npm_cli_update_rolls_back_via_tempdir_outside_install_root() -> None:
    cli_text = (ROOT / "packages" / "cli" / "bin" / "koda.mjs").read_text(encoding="utf-8")

    assert 'mkdtemp(join(tmpdir(), "koda-rollback-"))' in cli_text
    assert 'join(installDir, ".rollback")' not in cli_text


def test_systemd_example_operates_docker_compose() -> None:
    unit_text = (ROOT / "koda.service.example").read_text(encoding="utf-8")

    assert "docker compose up -d" in unit_text
    assert "docker compose down" in unit_text


def test_release_workflow_enforces_validation_and_protected_publish_path() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "release.yml"
    assert workflow_path.exists()

    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    jobs = payload["jobs"]

    assert "codeql" in jobs
    assert "workflow-quality" in jobs
    assert "ensure-release-tag" in jobs
    assert "publish-ghcr" in jobs
    assert "publish-npm" in jobs
    assert "github-release" in jobs
    assert jobs["ensure-release-tag"]["permissions"]["contents"] == "write"
    assert jobs["publish-ghcr"]["environment"] == "release"
    assert jobs["publish-npm"]["environment"] == "release"
    assert jobs["github-release"]["environment"] == "release"
    publish_npm_steps = jobs["publish-npm"]["steps"]
    assert publish_npm_steps[0]["uses"] == "actions/checkout@v6.0.2"
    assert publish_npm_steps[0]["with"]["ref"] == "${{ needs.ensure-release-tag.outputs.publish_ref }}"
    assert jobs["publish-npm"]["permissions"]["id-token"] == "write"
    assert jobs["github-release"]["if"].startswith("always()")

    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "NPM_TOKEN" in workflow_text
    assert "trusted publishing" in workflow_text
    assert "npm publish" in workflow_text
    assert "Upgrade npm for trusted publishing support" not in workflow_text
    assert "npm install -g npm@^11.5.1" not in workflow_text
    assert "docker/setup-buildx-action@v3" in workflow_text
    assert "driver: docker-container" in workflow_text
    assert "npx --yes npm@11.5.1 publish" in workflow_text
    assert "Validate npm token fallback identity" in workflow_text
    assert "npm whoami --registry=https://registry.npmjs.org" in workflow_text
    assert "Abort release when trusted publishing fails without token fallback" in workflow_text
    assert "Abort token fallback when npm authentication is invalid" in workflow_text
    assert "uv export" in workflow_text
    assert "--all-extras" in workflow_text
    assert "--no-editable" in workflow_text
    assert "--no-emit-project" in workflow_text
    assert "--no-emit-workspace" in workflow_text
    assert "python-audit-requirements.txt" in workflow_text
    assert "--require-hashes" in workflow_text
    assert "--disable-pip" in workflow_text
    assert "Check whether npm package version already exists" in workflow_text
    assert "Skip npm publish when version already exists" in workflow_text
    assert "Repair npm dist-tag with token fallback when needed" in workflow_text
    assert "Verify npm package version and dist-tag" in workflow_text
    assert 'npm dist-tag add "${NPM_PACKAGE_NAME}@${VERSION}" "${DIST_TAG}"' in workflow_text
    assert "python3 scripts/npm_registry_metadata.py exists" in workflow_text
    assert "python3 scripts/npm_registry_metadata.py state" in workflow_text
    assert "python3 scripts/npm_registry_metadata.py dist-tags" in workflow_text
    assert (ROOT / "scripts" / "npm_registry_metadata.py").exists()
    assert 'gh release view "${RELEASE_TAG}"' in workflow_text
    assert "Create or update GitHub release" in workflow_text
    assert "draft: ${{ steps.release_mode.outputs.draft }}" in workflow_text
    assert "Publish status:" in workflow_text
    assert 'git push origin "refs/tags/${RELEASE_TAG}"' in workflow_text
    assert "scripts/sync_npm_readme.py" in workflow_text
    assert "docker/build-push-action" in workflow_text
    assert "bash scripts/docker_smoke.sh" in workflow_text
    assert "rhysd/actionlint@v1.7.12" in workflow_text
    assert "pnpm/action-setup@v5.0.0" in workflow_text
    assert "pnpm/action-setup@v4.2.0" not in workflow_text


def test_main_branch_uses_a_dedicated_release_tag_cut_workflow() -> None:
    workflow_path = ROOT / ".github" / "workflows" / "cut-release-tag.yml"
    assert workflow_path.exists()

    payload = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    trigger = payload.get("on", payload.get(True))

    assert trigger["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in trigger
    assert payload["permissions"]["actions"] == "write"
    assert payload["permissions"]["contents"] == "write"
    assert payload["permissions"]["id-token"] == "write"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    assert "--json isDraft,assets" in workflow_text
    assert "release_ready" in workflow_text
    assert "npm_ready" in workflow_text
    assert "dist-tags --json" in workflow_text
    assert "Fail when the version tag already exists on an older commit but publication is incomplete" in workflow_text
    assert "Do not retarget ${TAG}; ship a new patch version from this commit instead." in workflow_text


def test_shared_docker_smoke_script_hardens_release_endpoint_checks() -> None:
    script_path = ROOT / "scripts" / "docker_smoke.sh"
    script_text = script_path.read_text(encoding="utf-8")
    cut_release_workflow_text = (ROOT / ".github" / "workflows" / "cut-release-tag.yml").read_text(encoding="utf-8")

    assert script_path.exists()
    assert "curl -fsSL" in script_text
    assert "--retry-connrefused" in script_text
    assert "--retry-all-errors" in script_text
    assert "docker compose" in script_text
    assert "docker-inspect.json" in script_text
    assert "control-plane/setup" in script_text
    assert "openapi/control-plane.json" in script_text

    assert '["pr-quality", "security"]' in cut_release_workflow_text
    assert "actions/github-script@v8" in cut_release_workflow_text
    assert "gh release view" in cut_release_workflow_text
    assert (
        "Skip dispatch when the release and npm publication are complete for the current tag"
        in cut_release_workflow_text
    )
    assert "Recover publish when the tag exists but publication is incomplete" in cut_release_workflow_text
    assert (
        "Stop when the version tag already exists on an older commit and publication is complete"
        in cut_release_workflow_text
    )
    assert (
        "Fail when the version tag already exists on an older commit but publication is incomplete"
        in cut_release_workflow_text
    )
    assert "git tag -a" in cut_release_workflow_text
    assert 'git push origin "refs/tags/${TAG}"' in cut_release_workflow_text
    assert (
        "if: steps.version.outcome == 'success' && steps.existing.outputs.exists != 'true'" in cut_release_workflow_text
    )
    assert (
        "if: steps.version.outcome == 'success' && (steps.existing.outputs.exists != 'true' || "
        "(steps.existing.outputs.tag_sha == steps.target.outputs.sha && "
        "(steps.release_state.outputs.release_ready != 'true' || steps.npm_state.outputs.npm_ready != 'true')))"
        in cut_release_workflow_text
    )
    assert 'workflow_id: "release.yml"' in cut_release_workflow_text
    assert "createWorkflowDispatch" in cut_release_workflow_text


def test_release_docs_explain_main_release_automation() -> None:
    release_docs_text = (ROOT / "docs" / "reference" / "releases.md").read_text(encoding="utf-8")
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Automatic Release Tag Cut" in release_docs_text
    assert "cut-release-tag" in release_docs_text
    assert "pr-quality" in release_docs_text
    assert "security" in release_docs_text
    assert "v<version>" in release_docs_text
    assert "createWorkflowDispatch" not in release_docs_text
    assert "GitHub does not start a new `push` workflow when a workflow pushes a tag" in release_docs_text
    assert "GitHub release is draft, missing assets, or the npm dist-tag is still wrong" in release_docs_text
    assert "the workflow fails loudly and requires a new patch version" in release_docs_text
    assert "treat it as immutable" in release_docs_text
    assert "cut-release-tag.yml" in release_docs_text
    assert "release.yml" in release_docs_text
    assert "Configure npm trusted publishing against `OpenKodaAI/koda` and `release.yml`" in release_docs_text
    assert "Grant `id-token: write` to both `release.yml` and `cut-release-tag.yml`" in release_docs_text
    assert "optional `release` environment" in release_docs_text
    assert "draft recovery" in release_docs_text
    assert "npm whoami" in release_docs_text
    assert "dist-tag" in release_docs_text
    legacy_trusted_publishing_guidance = (
        "cut-release-tag.yml` is the workflow that dispatches "
        "`release.yml`, so npm trusted publishing should be configured"
    )
    assert legacy_trusted_publishing_guidance not in release_docs_text
    assert "Public releases are cut from `main` by version." in readme_text
    assert "GitHub release is still draft, missing assets, or the npm dist-tag is still wrong" in readme_text
    assert "fails loudly so the next merge must ship a new" in readme_text
    assert "patch version instead of trying to reuse an escaped semantic tag" in readme_text


def test_dependabot_blocks_unsupported_eslint_major_updates() -> None:
    dependabot_path = ROOT / ".github" / "dependabot.yml"
    payload = yaml.safe_load(dependabot_path.read_text(encoding="utf-8"))

    npm_update = next(update for update in payload["updates"] if update["package-ecosystem"] == "npm")
    ignores = npm_update["ignore"]

    assert {
        "dependency-name": "eslint",
        "update-types": ["version-update:semver-major"],
    } in ignores


def test_security_and_release_workflows_scan_all_runtime_images() -> None:
    release_workflow_text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    security_workflow_text = (ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    snyk_workflow_text = (ROOT / ".github" / "workflows" / "snyk.yml").read_text(encoding="utf-8")
    pr_quality_workflow_text = (ROOT / ".github" / "workflows" / "pr-quality.yml").read_text(encoding="utf-8")

    assert "python-audit-requirements.txt" in release_workflow_text
    assert "python-audit-requirements.txt" in security_workflow_text
    assert "--all-extras" in release_workflow_text
    assert "--all-extras" in security_workflow_text
    assert "--no-editable" in release_workflow_text
    assert "--no-editable" in security_workflow_text
    assert "--no-emit-project" in release_workflow_text
    assert "--no-emit-workspace" in release_workflow_text
    assert "--no-emit-project" in security_workflow_text
    assert "--no-emit-workspace" in security_workflow_text
    assert "--require-hashes" in release_workflow_text
    assert "--require-hashes" in security_workflow_text
    assert "--disable-pip" in release_workflow_text
    assert "--disable-pip" in security_workflow_text

    trivy_targets = (
        "koda.sarif --exit-code 1 koda:",
        "koda-web.sarif --exit-code 1 koda-web:",
        "koda-memory.sarif --exit-code 1 koda-memory:",
        "koda-security.sarif --exit-code 1 koda-security:",
    )

    for workflow_text in (release_workflow_text, security_workflow_text):
        assert "docker build -t koda:" in workflow_text
        assert "docker build -f apps/web/Dockerfile -t koda-web:" in workflow_text
        assert "docker build -f Dockerfile.memory -t koda-memory:" in workflow_text
        assert "docker build -f Dockerfile.security -t koda-security:" in workflow_text
        for trivy_target in trivy_targets:
            assert trivy_target in workflow_text

    for workflow_text in (pr_quality_workflow_text, security_workflow_text, release_workflow_text):
        assert "pnpm/action-setup@v5.0.0" in workflow_text
        assert "pnpm/action-setup@v4.2.0" not in workflow_text

    assert "snyk/actions/setup@v1.0.0" in snyk_workflow_text
    assert "uv sync --locked --all-groups --all-extras" in snyk_workflow_text
    assert "--all-projects" in snyk_workflow_text
    assert "--detection-depth=5" in snyk_workflow_text
    assert "python-requirements.txt" in snyk_workflow_text
    assert "--command=.venv/bin/python" in snyk_workflow_text
    assert "--skip-unresolved=true" in snyk_workflow_text
    assert "snyk monitor" in snyk_workflow_text
    assert "continue-on-error: true" in snyk_workflow_text
    assert "Summarize Snyk monitor snapshot status" in snyk_workflow_text
    assert "SNYK_TOKEN" in snyk_workflow_text

    assert "python3 scripts/review_dependency_changes.py" in security_workflow_text
    assert "github.event.pull_request.base.sha" in security_workflow_text
    assert "github.event.pull_request.head.sha" in security_workflow_text
    assert "fetch-depth: 0" in security_workflow_text

    for workflow_text in (pr_quality_workflow_text, release_workflow_text):
        assert "rhysd/actionlint@v1.7.12" in workflow_text
        assert "bash scripts/docker_smoke.sh" in workflow_text


def test_snyk_policy_excludes_generated_artifacts_only() -> None:
    policy_text = (ROOT / ".snyk").read_text(encoding="utf-8")

    assert "exclude:" in policy_text
    for excluded_path in (
        ".koda-release/**",
        ".pnpm-store/**",
        ".venv/**",
        ".next/**",
        "artifacts/**",
        "build/**",
        "coverage/**",
        "downloads/**",
        "dist/**",
        "output/**",
        "packages/cli/release/**",
        "target/**",
        "venv/**",
    ):
        assert excluded_path in policy_text
    assert "docker-compose.release.yml" not in policy_text


def test_snyk_workflow_excludes_non_source_manifests() -> None:
    workflow_text = (ROOT / ".github" / "workflows" / "snyk.yml").read_text(encoding="utf-8")

    assert (
        "--exclude=.git,.koda-release,.next,.mypy_cache,.pnpm-store,.pytest_cache,.ruff_cache,.venv,venv,artifacts,build,coverage,dist,downloads,node_modules,output,requirements.txt,target,release"
        in workflow_text
    )
    assert "uv sync --locked --all-groups --all-extras" in workflow_text
    assert "--command=.venv/bin/python" in workflow_text
    assert "--skip-unresolved=true" in workflow_text
    assert "Summarize Snyk monitor snapshot status" in workflow_text


def test_npm_tarball_network_strings_are_expected_and_localized(tmp_path) -> None:
    output_dir = tmp_path / "release-artifacts"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_release_artifacts.py"), "--output-dir", str(output_dir)],
        check=True,
        cwd=ROOT,
    )

    payload = json.loads((output_dir / "release-artifacts.json").read_text(encoding="utf-8"))
    tarball_path = output_dir / payload["npm_tarball"]
    host_re = re.compile(r"(?:git\\+)?https?://([A-Za-z0-9.-]+)")

    with tarfile.open(tarball_path, "r:gz") as tarball:
        texts = [
            tarball.extractfile(name).read().decode("utf-8")
            for name in (
                "package/package.json",
                "package/README.md",
                "package/bin/koda.mjs",
                "package/release/manifest.json",
                "package/release/bundle/docker-compose.release.yml",
                "package/release/bundle/proxy/nginx.conf",
                "package/release/bundle/sbom.spdx.json",
            )
        ]

    combined = "\n".join(texts)
    hosts = sorted(set(host_re.findall(combined)))
    allowed_hosts = {
        "app",
        "github.com",
        "img.shields.io",
        "localhost",
        "raw.githubusercontent.com",
        "seaweedfs",
    }

    assert "127.0.0.1" not in combined
    assert "https://openkoda.ai/spdx/" not in combined
    assert "urn:openkodaai:spdx:koda-release-bundle:" in combined
    assert "git+https://github.com/OpenKodaAI/koda.git" in combined
    assert "http://localhost:3000/control-plane/setup" in combined
    assert "http://localhost:8090/health" in combined
    assert "http://app:8090" in combined
    assert "http://seaweedfs:8333" in combined
    assert hosts
    assert set(hosts) <= allowed_hosts, hosts


def test_repo_hygiene_workflows_cover_public_docs_and_installation_assets() -> None:
    pr_quality_workflow_text = (ROOT / ".github" / "workflows" / "pr-quality.yml").read_text(encoding="utf-8")
    release_workflow_text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    for workflow_text in (pr_quality_workflow_text, release_workflow_text):
        assert "scripts/sync_npm_readme.py" in workflow_text
        assert "tests/test_public_docs.py" in workflow_text
        assert "tests/test_installation_assets.py" in workflow_text


def test_runtime_dockerfiles_strip_unused_node_package_managers() -> None:
    app_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    web_dockerfile = (ROOT / "apps" / "web" / "Dockerfile").read_text(encoding="utf-8")

    assert "rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack" in app_dockerfile
    assert "@googleworkspace/cli" in app_dockerfile
    assert "/usr/local/bin/gws" in app_dockerfile
    assert "rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack" in web_dockerfile
    assert 'CMD ["node", "server.mjs"]' in web_dockerfile
    assert 'CMD ["pnpm", "start"]' not in web_dockerfile


def test_runtime_dockerfile_exports_locked_python_dependencies() -> None:
    app_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ENV UV_VERSION=0.10.7" in app_dockerfile
    assert "pip==26.0 uv==${UV_VERSION}" in app_dockerfile
    assert "COPY pyproject.toml uv.lock ./" in app_dockerfile
    assert "uv export" in app_dockerfile
    assert "--locked" in app_dockerfile
    assert "--no-emit-project" in app_dockerfile
    assert "--no-emit-workspace" in app_dockerfile
    assert "/tmp/runtime-requirements.txt" in app_dockerfile
    assert "COPY requirements.txt ./" not in app_dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" not in app_dockerfile


def test_doctor_checks_dashboard_and_control_plane() -> None:
    doctor_text = (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")

    assert "web_dashboard" in doctor_text
    assert "WEB_PORT" in doctor_text
    assert "dashboard_url" in doctor_text
    assert "dashboard_setup_url" in doctor_text
    assert "legacy_setup_url" in doctor_text
    assert "/setup" in doctor_text
    assert "/setup?token=" not in doctor_text
    assert "CONTROL_PLANE_MASTER_KEY" not in doctor_text


def test_steady_state_assets_do_not_reference_legacy_object_storage_branding() -> None:
    legacy_backend_name = "".join(("mi", "nio"))
    migration_doc = ROOT / "docs" / "install" / "object-storage-migration.md"
    checked_files = [
        ROOT / "docker-compose.yml",
        ROOT / "docker-compose.prod.yml",
        ROOT / ".env.example",
        ROOT / "README.md",
        ROOT / "docs" / "install" / "local.md",
        ROOT / "docs" / "install" / "vps.md",
        ROOT / "docs" / "config" / "reference.md",
        ROOT / "scripts" / "install.sh",
        ROOT / "scripts" / "doctor.py",
        ROOT / "tests" / "test_installation_assets.py",
    ]
    for path in checked_files:
        text = path.read_text(encoding="utf-8").lower()
        assert legacy_backend_name not in text, path.as_posix()
    assert legacy_backend_name in migration_doc.read_text(encoding="utf-8").lower()
