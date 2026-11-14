"""Every Compose file publishes host ports on loopback by default.

The control-plane API is never published beyond 127.0.0.1 (the dashboard and a
host reverse proxy reach it locally). The dashboard defaults to 127.0.0.1 and
can only be opened to other interfaces through an explicit
``WEB_PUBLISH_ADDRESS`` override. See docs/install/vps.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = sorted(
    [*ROOT.glob("docker-compose*.yml"), *(ROOT / "packages" / "cli" / "release" / "bundle").glob("docker-compose*.yml")]
)
LOOPBACK = "127.0.0.1"
# Only ${VAR:-default}: with ${VAR-default}, an empty VAR yields no host IP,
# which publishes on every interface.
_VAR_WITH_DEFAULT = re.compile(r"^\$\{(?P<name>[A-Z0-9_]+):-(?P<default>[^}]*)\}$")


def _published_ports(path: Path) -> list[tuple[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ports: list[tuple[str, str]] = []
    for service, spec in (data.get("services") or {}).items():
        for entry in (spec or {}).get("ports") or []:
            ports.append((service, str(entry)))
    return ports


def _host_ip(entry: str) -> str | None:
    """Return the host-IP part of a short-syntax port mapping, or None if absent."""
    # Split on ':' outside ${...} expressions.
    parts = re.findall(r"\$\{[^}]*\}|[^:]+", entry)
    return parts[0] if len(parts) == 3 else None


def test_compose_files_are_discovered() -> None:
    names = {path.name for path in COMPOSE_FILES}
    assert {"docker-compose.yml", "docker-compose.prod.yml", "docker-compose.release.yml"} <= names


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda path: path.name)
def test_every_published_port_defaults_to_loopback(path: Path) -> None:
    for service, entry in _published_ports(path):
        host_ip = _host_ip(entry)
        assert host_ip is not None, f"{path.name}:{service} publishes {entry!r} on all interfaces"
        match = _VAR_WITH_DEFAULT.match(host_ip)
        if match:
            assert match.group("name") == "WEB_PUBLISH_ADDRESS" and service == "web", (
                f"{path.name}:{service}: only the dashboard may take its publish address from a variable"
            )
            assert match.group("default") == LOOPBACK, f"{path.name}:{service} must default to {LOOPBACK}"
        else:
            assert host_ip == LOOPBACK, f"{path.name}:{service} publishes {entry!r} beyond loopback"


@pytest.mark.parametrize("name", ["docker-compose.yml", "docker-compose.release.yml"])
def test_control_plane_api_is_published_on_loopback_only(name: str) -> None:
    path = next(path for path in COMPOSE_FILES if path.name == name)
    app_ports = [entry for service, entry in _published_ports(path) if service == "app"]
    assert app_ports == ["127.0.0.1:${CONTROL_PLANE_PORT:-8090}:8090"]


OVERLAYS = [path for path in COMPOSE_FILES if path.parent == ROOT and path.name != "docker-compose.yml"]


@pytest.mark.parametrize("path", OVERLAYS, ids=lambda path: path.name)
def test_overlays_do_not_repeat_base_port_mappings(path: Path) -> None:
    # Compose concatenates `ports` across files, so redefining app/web ports in
    # an overlay would add mappings instead of replacing the base ones.
    services = {service for service, _ in _published_ports(path)}
    assert not services & {"app", "web"}


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda path: path.name)
def test_no_service_uses_host_networking(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for service, spec in (data.get("services") or {}).items():
        assert (spec or {}).get("network_mode") != "host", f"{path.name}:{service} bypasses port publishing"


@pytest.mark.parametrize("name", ["docker-compose.yml", "docker-compose.release.yml"])
def test_control_plane_listens_on_fixed_internal_port(name: str) -> None:
    # CONTROL_PLANE_PORT selects the host port only; inside the stack the API is
    # always app:8090, and the published port is passed for host-facing URLs.
    path = next(path for path in COMPOSE_FILES if path.name == name)
    services = (yaml.safe_load(path.read_text(encoding="utf-8")) or {})["services"]
    app_env = services["app"]["environment"]
    assert app_env["CONTROL_PLANE_PORT"] == "8090"
    assert app_env["CONTROL_PLANE_PUBLIC_PORT"] == "${CONTROL_PLANE_PORT:-8090}"
    assert services["web"]["environment"]["CONTROL_PLANE_BASE_URL"] == "http://app:8090"


def test_oauth_relay_url_uses_the_published_host_port(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.services import provider_auth

    # The relay is only used inside Docker, where the published port differs.
    monkeypatch.setattr(provider_auth, "_is_running_in_docker", lambda: True)
    monkeypatch.setattr("koda.config.CONTROL_PLANE_PUBLIC_PORT", "18090")
    auth_url = "https://provider.example/authorize?redirect_uri=http%3A%2F%2Flocalhost%3A54545%2Fcallback&state=x"

    rewritten, internal = provider_auth._rewrite_auth_callback_for_relay(auth_url, "session-1")

    assert internal == "http://localhost:54545/callback"
    assert "http%3A%2F%2Flocalhost%3A18090%2Fapi%2Fcontrol-plane%2Foauth-relay%2Fsession-1" in rewritten
