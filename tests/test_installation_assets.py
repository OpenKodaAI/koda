"""Tests for Docker-first installation assets and public quickstart docs."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_env_example_is_bootstrap_only() -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    web_env_text = (ROOT / "apps" / "web" / ".env.example").read_text(encoding="utf-8")

    assert "CONTROL_PLANE_API_TOKEN=" in env_text
    assert "RUNTIME_LOCAL_UI_TOKEN=" in env_text
    assert "WEB_PORT=" in env_text
    assert "KNOWLEDGE_V2_POSTGRES_DSN=" in env_text
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
    assert "${WEB_PORT:-3000}:3000" in compose_text
    assert "http://seaweedfs:8333" in compose_text
    assert 'CONTROL_PLANE_API_TOKEN: "${CONTROL_PLANE_API_TOKEN:-}"' not in compose_text
    assert "env_file: .env" not in compose_text.split("web:")[1].split("postgres:")[0]


def test_install_script_bootstraps_compose_and_doctor() -> None:
    script_text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert "compose up -d --build" in script_text
    assert "python3 scripts/doctor.py" in script_text
    assert "--dashboard-url" in script_text
    assert "Dashboard URL:" in script_text
    assert "/setup?token=" not in script_text
    assert "http://${host}:${port:-8090}/setup" in script_text


def test_public_docs_cover_quickstart_and_vps() -> None:
    assert (ROOT / "docs" / "README.md").exists()
    assert (ROOT / "docs" / "install" / "local.md").exists()
    assert (ROOT / "docs" / "install" / "vps.md").exists()
    assert (ROOT / "docs" / "install" / "object-storage-migration.md").exists()
    assert (ROOT / "docs" / "config" / "reference.md").exists()
    assert (ROOT / "docs" / "architecture" / "overview.md").exists()
    assert (ROOT / "docs" / "architecture" / "runtime.md").exists()
    assert (ROOT / "docs" / "reference" / "api.md").exists()
    assert (ROOT / "CONTRIBUTING.md").exists()
    assert (ROOT / "SECURITY.md").exists()
    assert (ROOT / "CODE_OF_CONDUCT.md").exists()
    assert (ROOT / "LICENSE").exists()
    assert (ROOT / "apps" / "web" / "package.json").exists()
    assert (ROOT / "apps" / "web" / ".env.example").exists()
    assert (ROOT / "apps" / "web" / "Dockerfile").exists()
    assert (ROOT / "docs" / "assets" / "brand" / "koda-logo.svg").exists()
    assert (ROOT / "docs" / "assets" / "brand" / "koda-logo.png").exists()
    assert (ROOT / "docs" / "assets" / "brand" / "koda-hero.png").exists()
    assert (ROOT / "docs" / "assets" / "brand" / "koda-og.png").exists()
    assert (ROOT / "docs" / "assets" / "screenshots" / "setup.png").exists()

    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_index_text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    local_text = (ROOT / "docs" / "install" / "local.md").read_text(encoding="utf-8")
    vps_text = (ROOT / "docs" / "install" / "vps.md").read_text(encoding="utf-8")

    assert "control-plane-first" in readme_text
    assert "apps/web" in readme_text
    assert "127.0.0.1:3000" in readme_text
    assert "/setup" in readme_text
    assert "?token=" not in readme_text
    assert "seaweedfs" in readme_text.lower()
    assert "Use Koda" in docs_index_text
    assert "apps/web/" in docs_index_text
    assert "/setup" in local_text
    assert "?token=" not in local_text
    assert "Product configuration stays inside the control-plane UI and API." in vps_text
    assert "The quickstart path does not require per-agent env configuration" in local_text


def test_openapi_document_contains_onboarding_paths() -> None:
    payload = json.loads((ROOT / "docs" / "openapi" / "control-plane.json").read_text(encoding="utf-8"))
    assert "/setup" in payload["paths"]
    assert "/api/control-plane/onboarding/status" in payload["paths"]
    assert "/api/control-plane/onboarding/bootstrap" in payload["paths"]


def test_systemd_example_operates_docker_compose() -> None:
    unit_text = (ROOT / "koda.service.example").read_text(encoding="utf-8")

    assert "docker compose up -d" in unit_text
    assert "docker compose down" in unit_text


def test_doctor_checks_dashboard_and_control_plane() -> None:
    doctor_text = (ROOT / "scripts" / "doctor.py").read_text(encoding="utf-8")

    assert "web_dashboard" in doctor_text
    assert "WEB_PORT" in doctor_text
    assert "dashboard_url" in doctor_text
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
