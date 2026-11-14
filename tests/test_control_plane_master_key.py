"""AG-05: the control-plane master key fails closed (ADR-002 §2.5).

Pinned guarantees:

  * Loading the key never creates one. A process without the key file (a
    worker, a CLI, a misconfigured app) gets ``MasterKeyUnavailable`` and
    leaves no file and no directory behind.
  * ``ensure_master_key()`` (control-plane bootstrap, app process only)
    generates a key only on a fresh install: no key file, no recorded
    fingerprint and no ciphertext.
  * An existing install with a key and secrets but no fingerprint upgrades
    cleanly: the fingerprint is recorded from the present key and the key is
    not touched, provided that key (or the previous key) decrypts at least
    one of the newest stored values. A key that decrypts none of them, such
    as one a pre-AG-05 loader created after the real key was lost, is
    refused and not recorded, unless the operator's acknowledgement file
    names that key's fingerprint (the documented lost-key procedure).
  * A mismatch, or a missing key while a fingerprint or ciphertext exists,
    refuses startup with guidance.
  * Rotation keeps working: a previous key that matches the recorded
    fingerprint re-records the fingerprint for the new current key.

The SQL behind the fingerprint helpers runs against real Postgres in
``tests/integration/test_master_key_fingerprint_postgres.py``.
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from koda.control_plane import crypto

ROOT = Path(__file__).resolve().parents[1]


class _FakeFingerprintStore:
    """In-memory stand-in for the ``cp_master_key_fingerprint`` row."""

    def __init__(self) -> None:
        self.fingerprint: str | None = None
        self.reason: str | None = None
        self.ciphertext = False
        # Fernet tokens the newest rows of the ciphertext stores hold.
        self.samples: list[str] = []
        self.writes: list[tuple[str, str]] = []
        self.audit: list[dict[str, Any]] = []

    def recorded(self) -> str | None:
        return self.fingerprint

    def insert(self, fingerprint: str, *, reason: str) -> None:
        self.writes.append(("insert", reason))
        if self.fingerprint is None:
            self.fingerprint = fingerprint
            self.reason = reason

    def replace(self, *, expected: str, fingerprint: str, reason: str) -> bool:
        self.writes.append(("replace", reason))
        if self.fingerprint != expected:
            return False
        self.fingerprint = fingerprint
        self.reason = reason
        return True

    def ciphertext_exists(self) -> bool:
        return self.ciphertext

    def ciphertext_samples(self) -> list[str]:
        return list(self.samples)

    def record_audit_event(self, agent_id: str, *, event_type: str, details: dict[str, Any] | None = None) -> None:
        self.audit.append({"agent_id": agent_id, "event_type": event_type, "details": dict(details or {})})


@pytest.fixture
def key_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Point the key and previous-key files at an empty state root."""
    state_root = tmp_path / "state"
    key_file = state_root / "control_plane" / ".master.key"
    previous_file = state_root / "control_plane" / ".master-previous.key"
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY", "")
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY_FILE", key_file)
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY_PREVIOUS", "")
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE", previous_file)
    crypto.clear_fernet_cache()
    yield SimpleNamespace(state_root=state_root, key_file=key_file, previous_file=previous_file)
    crypto.clear_fernet_cache()


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _FakeFingerprintStore:
    fake = _FakeFingerprintStore()
    monkeypatch.setattr(crypto, "_recorded_fingerprint", fake.recorded)
    monkeypatch.setattr(crypto, "_insert_fingerprint", fake.insert)
    monkeypatch.setattr(crypto, "_replace_fingerprint", fake.replace)
    monkeypatch.setattr(crypto, "_ciphertext_exists", fake.ciphertext_exists)
    monkeypatch.setattr(crypto, "_ciphertext_samples", fake.ciphertext_samples)
    monkeypatch.setattr(crypto, "record_audit_event", fake.record_audit_event)
    return fake


def _write_key(path: Path, key: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    path.chmod(mode)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# Loading never creates a key


def test_worker_decrypt_path_leaves_no_key_file(key_paths: SimpleNamespace) -> None:
    """The worker-side MCP env decrypt must not create a key as a side effect."""
    from koda.services.mcp_connection_broker import decrypt_env_values

    ciphertext = Fernet(Fernet.generate_key()).encrypt(b"value").decode()

    assert decrypt_env_values(f'{{"API_TOKEN": "{ciphertext}"}}') == {}
    assert not key_paths.key_file.exists()
    assert not key_paths.state_root.exists()


@pytest.mark.parametrize(
    "operation",
    [
        lambda: crypto.get_fernet(),
        lambda: crypto.encrypt_secret("value"),
        lambda: crypto.decrypt_secret("gAAAAA-not-reached"),
        lambda: crypto.get_signing_key(),
    ],
    ids=["get_fernet", "encrypt_secret", "decrypt_secret", "get_signing_key"],
)
def test_worker_gets_master_key_unavailable_and_leaves_no_file(key_paths: SimpleNamespace, operation: Any) -> None:
    with pytest.raises(crypto.MasterKeyUnavailable) as excinfo:
        operation()

    assert str(key_paths.key_file) in str(excinfo.value)
    assert not key_paths.key_file.exists()
    assert not key_paths.state_root.exists()


def test_master_key_unavailable_is_a_runtime_error() -> None:
    """Existing ``except Exception`` / ``except RuntimeError`` callers keep working."""
    assert issubclass(crypto.MasterKeyUnavailable, crypto.MasterKeyError)
    assert issubclass(crypto.MasterKeyMismatch, crypto.MasterKeyError)
    assert issubclass(crypto.MasterKeyError, RuntimeError)


def test_present_key_loads_and_loose_permissions_are_tightened(key_paths: SimpleNamespace) -> None:
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key + b"\n", mode=0o644)

    assert crypto.decrypt_secret(crypto.encrypt_secret("round-trip")) == "round-trip"
    assert crypto.get_signing_key() == key
    assert _mode(key_paths.key_file) == 0o600


@pytest.mark.parametrize("loose_mode", [0o444, 0o440, 0o404, 0o640, 0o604, 0o660])
def test_key_readable_by_group_or_others_is_tightened(key_paths: SimpleNamespace, loose_mode: int) -> None:
    # Modes numerically below 0o600 (e.g. 0o444) still expose the key to other users.
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key, mode=loose_mode)

    assert crypto.get_signing_key() == key
    assert _mode(key_paths.key_file) & 0o077 == 0


def test_key_on_unchangeable_mount_is_used_and_exposure_logged(
    key_paths: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key, mode=0o444)
    warnings: list[tuple[str, dict]] = []
    monkeypatch.setattr(crypto.log, "warning", lambda event, **kw: warnings.append((event, kw)))

    def _read_only(self: Path, mode: int) -> None:
        raise PermissionError(30, "Read-only file system")

    monkeypatch.setattr(Path, "chmod", _read_only)

    assert crypto.get_signing_key() == key
    assert [event for event, _ in warnings] == ["control_plane_master_key_permissions_too_open"]
    assert warnings[0][1]["mode"] == "0o444"


def test_unreadable_key_file_is_unavailable(key_paths: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_key(key_paths.key_file, Fernet.generate_key())

    def _deny(self: Path) -> bytes:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_bytes", _deny)

    with pytest.raises(crypto.MasterKeyUnavailable, match="Permission denied"):
        crypto.get_fernet()


def test_empty_key_file_is_unavailable(key_paths: SimpleNamespace) -> None:
    _write_key(key_paths.key_file, b"  \n")

    with pytest.raises(crypto.MasterKeyUnavailable, match="empty"):
        crypto.get_fernet()


def test_fingerprint_is_an_hmac_of_a_fixed_label_never_the_key() -> None:
    key = Fernet.generate_key()
    expected = hmac.new(key, crypto.MASTER_KEY_FINGERPRINT_LABEL, hashlib.sha256).hexdigest()

    fingerprint = crypto.master_key_fingerprint(key)

    assert fingerprint == expected
    assert fingerprint == crypto.master_key_fingerprint(key)
    assert key.decode() not in fingerprint
    assert fingerprint != crypto.master_key_fingerprint(Fernet.generate_key())


# ensure_master_key: the bootstrap matrix


def test_fresh_install_generates_key_and_records_fingerprint(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    assert crypto.ensure_master_key() == "fresh_install"

    key = key_paths.key_file.read_bytes().strip()
    Fernet(key)  # a valid Fernet key
    assert _mode(key_paths.key_file) == 0o600
    assert _mode(key_paths.key_file.parent) == 0o700
    assert store.fingerprint == crypto.master_key_fingerprint(key)
    assert store.reason == "fresh_install"
    assert [event["event_type"] for event in store.audit] == ["security.master_key_fingerprint_recorded"]
    assert store.audit[0]["details"]["reason"] == "fresh_install"
    assert key.decode() not in repr(store.audit)
    # No temporary key material is left next to the key.
    assert sorted(path.name for path in key_paths.key_file.parent.iterdir()) == [".master.key"]


def test_restart_verifies_without_touching_key_or_fingerprint(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    crypto.ensure_master_key()
    key_before = key_paths.key_file.read_bytes()
    writes_before = list(store.writes)

    assert crypto.ensure_master_key() == "verified"

    assert key_paths.key_file.read_bytes() == key_before
    assert store.writes == writes_before


def test_existing_install_without_fingerprint_upgrades_from_present_key(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key)
    store.ciphertext = True
    store.samples = [Fernet(key).encrypt(b"pre-upgrade").decode()]

    assert crypto.ensure_master_key() == "upgrade"

    assert key_paths.key_file.read_bytes() == key
    assert store.fingerprint == crypto.master_key_fingerprint(key)
    assert store.reason == "upgrade"
    assert store.ciphertext is True
    assert store.audit[0]["details"]["reason"] == "upgrade"


def test_present_key_without_fingerprint_or_secrets_records_fingerprint(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key)

    assert crypto.ensure_master_key() == "upgrade"
    assert key_paths.key_file.read_bytes() == key
    assert store.fingerprint == crypto.master_key_fingerprint(key)


def _acknowledgement(key_paths: SimpleNamespace) -> Path:
    return key_paths.key_file.parent / ".master.key.accept-undecryptable"


def test_upgrade_with_a_key_that_decrypts_no_stored_secret_refuses_and_records_nothing(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    """A pre-AG-05 loader replaced a lost key K1 with K2: K2 must not become the recorded key.

    Otherwise restoring K1 from backup would later be refused as a mismatch.
    """
    original = Fernet.generate_key()
    regenerated = Fernet.generate_key()
    _write_key(key_paths.key_file, regenerated)
    store.ciphertext = True
    store.samples = [Fernet(original).encrypt(f"secret-{n}".encode()).decode() for n in range(3)]

    with pytest.raises(crypto.MasterKeyMismatch) as excinfo:
        crypto.ensure_master_key()

    message = str(excinfo.value)
    assert "decrypts none of the 3" in message
    assert crypto.master_key_fingerprint(regenerated)[:12] in message
    assert "backup" in message
    assert str(_acknowledgement(key_paths)) in message
    assert regenerated.decode() not in message
    assert store.fingerprint is None
    assert store.writes == []
    assert store.audit == []
    assert key_paths.key_file.read_bytes() == regenerated

    # The operator restores the original key: it is accepted and recorded.
    key_paths.key_file.write_bytes(original)
    crypto.clear_fernet_cache()
    assert crypto.ensure_master_key() == "upgrade"
    assert store.fingerprint == crypto.master_key_fingerprint(original)
    assert crypto.ensure_master_key() == "verified"


def test_upgrade_accepts_a_key_that_decrypts_any_newest_sample(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    """Rows a still older key left behind do not block the key the install was last using."""
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key)
    store.samples = [
        Fernet(Fernet.generate_key()).encrypt(b"stale").decode(),
        Fernet(key).encrypt(b"current").decode(),
    ]

    assert crypto.ensure_master_key() == "upgrade"
    assert store.fingerprint == crypto.master_key_fingerprint(key)


def test_upgrade_accepts_a_key_when_the_previous_key_decrypts(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    """An install from before AG-05 in the middle of a rotation: the new key is recorded."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    _write_key(key_paths.key_file, new_key)
    _write_key(key_paths.previous_file, old_key)
    store.samples = [Fernet(old_key).encrypt(b"pre-rotation").decode()]

    assert crypto.ensure_master_key() == "upgrade"
    assert store.fingerprint == crypto.master_key_fingerprint(new_key)


def test_upgrade_ignores_an_invalid_previous_key(key_paths: SimpleNamespace, store: _FakeFingerprintStore) -> None:
    _write_key(key_paths.key_file, Fernet.generate_key())
    _write_key(key_paths.previous_file, bytes(range(32)))
    store.samples = [Fernet(Fernet.generate_key()).encrypt(b"value").decode()]

    with pytest.raises(crypto.MasterKeyMismatch, match="decrypts none"):
        crypto.ensure_master_key()
    assert store.writes == []


def test_lost_key_acknowledgement_records_the_named_key_and_is_removed(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    new_key = Fernet.generate_key()
    _write_key(key_paths.key_file, new_key)
    store.samples = [Fernet(Fernet.generate_key()).encrypt(b"lost").decode()]
    _acknowledgement(key_paths).write_text(crypto.master_key_fingerprint(new_key)[:12].upper() + "\n")

    assert crypto.ensure_master_key() == "lost_key_reset"

    assert store.fingerprint == crypto.master_key_fingerprint(new_key)
    assert store.reason == "lost_key_reset"
    assert [event["details"]["reason"] for event in store.audit] == ["lost_key_reset"]
    assert new_key.decode() not in repr(store.audit)
    assert not _acknowledgement(key_paths).exists()
    assert key_paths.key_file.read_bytes() == new_key


@pytest.mark.parametrize(
    "content",
    ["another-key", "short", ""],
    ids=["other_key", "too_short", "empty"],
)
def test_lost_key_acknowledgement_for_another_key_does_not_apply(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore, content: str
) -> None:
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key)
    store.samples = [Fernet(Fernet.generate_key()).encrypt(b"lost").decode()]
    prefix = crypto.master_key_fingerprint(key)[:12]
    if content == "another-key":
        content = crypto.master_key_fingerprint(Fernet.generate_key())[:12]
    elif content == "short":
        content = prefix[:6]
    _acknowledgement(key_paths).write_text(content)

    with pytest.raises(crypto.MasterKeyMismatch) as excinfo:
        crypto.ensure_master_key()

    assert "does not name this key" in str(excinfo.value)
    assert store.writes == []
    assert _acknowledgement(key_paths).read_text() == content


def test_lost_key_acknowledgement_does_not_override_a_recorded_fingerprint(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    recorded = crypto.master_key_fingerprint(Fernet.generate_key())
    store.fingerprint = recorded
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key)
    _acknowledgement(key_paths).write_text(crypto.master_key_fingerprint(key)[:12])

    with pytest.raises(crypto.MasterKeyMismatch, match="is not the key this database recorded"):
        crypto.ensure_master_key()

    assert store.fingerprint == recorded
    assert store.writes == []
    assert _acknowledgement(key_paths).exists()


def test_fernet_tokens_are_found_in_every_store_format() -> None:
    fernet = Fernet(Fernet.generate_key())
    token = fernet.encrypt(b"value").decode()
    other = fernet.encrypt(b"other").decode()

    assert crypto._fernet_tokens(token) == [token]
    assert crypto._fernet_tokens(f"  {token}\n") == [token]
    assert crypto._fernet_tokens(f'{{"API_TOKEN": "{token}", "EMPTY": ""}}') == [token]
    assert crypto._fernet_tokens(f'{{"status": "pending", "encrypted_details": "{token}"}}') == [token]
    snapshot = f'{{"secrets": {{"A": {{"encrypted_value": "{token}"}}, "B": {{"encrypted_value": "{other}"}}}}}}'
    assert sorted(crypto._fernet_tokens(snapshot)) == sorted([token, other])
    # Values that are not Fernet tokens are not evidence of a wrong key.
    for value in (None, "", "gAAAA-ciphertext", "plain text", "{not json", "[1, 2]", token[:-8], token + "!"):
        assert crypto._fernet_tokens(value) == [], value


def test_missing_key_while_secrets_exist_refuses_and_creates_nothing(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    store.ciphertext = True

    with pytest.raises(crypto.MasterKeyUnavailable) as excinfo:
        crypto.ensure_master_key()

    message = str(excinfo.value)
    assert "encrypted secrets" in message
    assert "backup" in message
    assert not key_paths.key_file.exists()
    assert not key_paths.state_root.exists()
    assert store.fingerprint is None
    assert store.writes == []


def test_missing_key_with_recorded_fingerprint_refuses_and_creates_nothing(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    store.fingerprint = crypto.master_key_fingerprint(Fernet.generate_key())

    with pytest.raises(crypto.MasterKeyUnavailable) as excinfo:
        crypto.ensure_master_key()

    assert store.fingerprint[:12] in str(excinfo.value)
    assert "backup" in str(excinfo.value)
    assert not key_paths.key_file.exists()
    assert not key_paths.state_root.exists()
    assert store.writes == []


def test_mismatched_key_refuses_with_guidance(key_paths: SimpleNamespace, store: _FakeFingerprintStore) -> None:
    recorded = crypto.master_key_fingerprint(Fernet.generate_key())
    store.fingerprint = recorded
    key = Fernet.generate_key()
    _write_key(key_paths.key_file, key)

    with pytest.raises(crypto.MasterKeyMismatch) as excinfo:
        crypto.ensure_master_key()

    message = str(excinfo.value)
    assert recorded[:12] in message
    assert crypto.master_key_fingerprint(key)[:12] in message
    assert "CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE" in message
    assert key.decode() not in message
    assert key_paths.key_file.read_bytes() == key
    assert store.fingerprint == recorded
    assert store.writes == []


def test_mismatched_previous_key_still_refuses(key_paths: SimpleNamespace, store: _FakeFingerprintStore) -> None:
    store.fingerprint = crypto.master_key_fingerprint(Fernet.generate_key())
    _write_key(key_paths.key_file, Fernet.generate_key())
    _write_key(key_paths.previous_file, Fernet.generate_key())

    with pytest.raises(crypto.MasterKeyMismatch):
        crypto.ensure_master_key()


def test_rotation_with_matching_previous_key_rerecords_fingerprint(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore
) -> None:
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    store.fingerprint = crypto.master_key_fingerprint(old_key)
    _write_key(key_paths.key_file, new_key)
    _write_key(key_paths.previous_file, old_key)

    assert crypto.ensure_master_key() == "rotation"

    assert store.fingerprint == crypto.master_key_fingerprint(new_key)
    assert store.reason == "rotation"
    assert key_paths.key_file.read_bytes() == new_key
    assert key_paths.previous_file.read_bytes() == old_key
    assert store.audit[0]["details"]["reason"] == "rotation"
    # Ciphertext written under the old key still decrypts through the fallback.
    old_ciphertext = Fernet(old_key).encrypt(b"pre-rotation").decode()
    assert crypto.decrypt_secret(old_ciphertext) == "pre-rotation"


def test_invalid_key_file_refuses(key_paths: SimpleNamespace, store: _FakeFingerprintStore) -> None:
    # `openssl rand 32` output, which an earlier rotation runbook suggested.
    _write_key(key_paths.key_file, bytes(range(32)))

    with pytest.raises(crypto.MasterKeyUnavailable, match="not a valid Fernet key"):
        crypto.ensure_master_key()

    assert store.writes == []


def test_concurrent_bootstrap_that_recorded_another_key_refuses(
    key_paths: SimpleNamespace, store: _FakeFingerprintStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two app processes racing a fresh install: the loser must not run with its own key."""
    other = crypto.master_key_fingerprint(Fernet.generate_key())

    def _lost_race(fingerprint: str, *, reason: str) -> None:
        store.writes.append(("insert", reason))
        store.fingerprint = store.fingerprint or other

    monkeypatch.setattr(crypto, "_insert_fingerprint", _lost_race)

    with pytest.raises(crypto.MasterKeyMismatch):
        crypto.ensure_master_key()

    assert store.fingerprint == other


def test_create_key_file_never_overwrites_an_existing_key(key_paths: SimpleNamespace) -> None:
    existing = Fernet.generate_key()
    _write_key(key_paths.key_file, existing)

    crypto._create_key_file(key_paths.key_file)

    assert key_paths.key_file.read_bytes() == existing
    assert sorted(path.name for path in key_paths.key_file.parent.iterdir()) == [".master.key"]


# Only the control-plane bootstrap can create a key


def _calls_in(tree: ast.AST) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        found.append((name, node.lineno))
    return found


def test_only_the_bootstrap_creates_keys_and_only_the_supervisor_calls_it() -> None:
    generate_sites: list[str] = []
    ensure_sites: list[str] = []
    create_sites: list[str] = []
    for path in sorted((ROOT / "koda").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for name, lineno in _calls_in(tree):
            if name == "generate_key":
                generate_sites.append(f"{relative}:{lineno}")
            elif name == "ensure_master_key":
                ensure_sites.append(relative)
            elif name == "_create_key_file":
                create_sites.append(relative)

    crypto_tree = ast.parse((ROOT / "koda/control_plane/crypto.py").read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(crypto_tree) if isinstance(node, ast.FunctionDef)}
    create_key_names = [name for name, _ in _calls_in(functions["_create_key_file"])]

    assert len(generate_sites) == 1, generate_sites
    assert generate_sites[0].startswith("koda/control_plane/crypto.py:")
    assert "generate_key" in create_key_names
    assert create_sites == ["koda/control_plane/crypto.py"]
    assert ensure_sites == ["koda/control_plane/supervisor.py"]
    load_names = [name for name, _ in _calls_in(functions["_load_master_key"])]
    assert "_create_key_file" not in load_names
    assert "generate_key" not in load_names


def _supervisor_with(manager: Any, link: Any) -> Any:
    from koda.control_plane.supervisor import ControlPlaneSupervisor

    with patch("koda.control_plane.supervisor.get_control_plane_manager", return_value=manager):
        return ControlPlaneSupervisor(link=link)


async def test_supervisor_start_refuses_before_seeding_or_kernel_link(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.control_plane import supervisor as supervisor_mod

    manager = MagicMock()
    link = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), ensure_agent_workers=AsyncMock(), target="fake")
    sup = _supervisor_with(manager, link)

    def _refuse() -> str:
        raise crypto.MasterKeyMismatch("wrong key")

    monkeypatch.setattr(supervisor_mod, "ensure_master_key", _refuse)

    with pytest.raises(crypto.MasterKeyMismatch):
        await sup.start()

    manager.ensure_seeded.assert_not_called()
    link.start.assert_not_called()


async def test_supervisor_start_ensures_key_before_seeding(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.control_plane import supervisor as supervisor_mod

    order: list[str] = []
    manager = MagicMock()
    manager.ensure_seeded.side_effect = lambda: order.append("ensure_seeded")
    link = SimpleNamespace(start=AsyncMock(side_effect=RuntimeError("stop here")), target="fake")
    sup = _supervisor_with(manager, link)
    monkeypatch.setattr(supervisor_mod, "ensure_master_key", lambda: order.append("ensure_master_key") or "verified")

    with pytest.raises(RuntimeError, match="stop here"):
        await sup.start()

    assert order == ["ensure_master_key", "ensure_seeded"]


def test_control_plane_main_exits_with_the_refusal_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.control_plane import __main__ as main_mod

    async def _refuse() -> None:
        raise crypto.MasterKeyUnavailable("restore the key from backup")

    monkeypatch.setattr(main_mod, "ensure_browser_installed_in_background", lambda: None)
    monkeypatch.setattr(main_mod, "run_supervisor", _refuse)

    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()

    assert "refused to start" in str(excinfo.value.code)
    assert "restore the key from backup" in str(excinfo.value.code)
