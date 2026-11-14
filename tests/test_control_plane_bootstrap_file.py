"""Tests for the first-boot bootstrap-file workflow."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from koda.control_plane import bootstrap_file as bootstrap_file_mod


@pytest.fixture()
def isolated_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the bootstrap-file path into a per-test directory."""
    file_path = tmp_path / "control_plane" / "bootstrap.txt"
    monkeypatch.setattr(bootstrap_file_mod, "_BOOTSTRAP_FILE_PATH", file_path)
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "")
    return file_path


def test_ensure_writes_file_with_restricted_perms(isolated_bootstrap: Path) -> None:
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code is not None
    assert isolated_bootstrap.exists()
    mode = os.stat(isolated_bootstrap).st_mode & 0o777
    assert mode == 0o600
    content = isolated_bootstrap.read_text(encoding="utf-8")
    assert content.splitlines()[0] == code
    assert "expires_at=" in content
    assert "setup_url=/setup" in content


def test_ensure_is_noop_when_owner_exists(isolated_bootstrap: Path) -> None:
    # Pre-create the file to ensure ensure() cleans it up when has_owner=True.
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text("OLD-CODE\n", encoding="utf-8")
    bootstrap_file_mod.ensure_bootstrap_file(has_owner=True)
    assert not isolated_bootstrap.exists()


def test_ensure_respects_env_seed(isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "CUST-OMSE-EDCD")
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code == "CUST-OMSE-EDCD"
    assert isolated_bootstrap.read_text(encoding="utf-8").splitlines()[0] == "CUST-OMSE-EDCD"


def _weak_seed_warnings(log: MagicMock) -> list[Any]:
    return [call for call in log.warning.call_args_list if call.args == ("bootstrap_code_seed_weak",)]


@pytest.mark.parametrize(
    ("seed", "significant"),
    [("!@#$%^&*()_+1", 1), ("!!!!a!!!!", 1), ("Tr0ub4dor&3!", 10), ("ÄÖÜ-ÄÖÜ", 0)],
)
def test_ensure_warns_about_a_seed_with_few_ascii_letters_or_digits(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, seed: str, significant: int
) -> None:
    """Setup codes match on ASCII letters and digits only, so a symbol-heavy seed is a short secret."""
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) == seed
    assert isolated_bootstrap.read_text(encoding="utf-8").splitlines()[0] == seed
    # The file already exists now, so a later call writes nothing and warns no more.
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) is None

    warnings = _weak_seed_warnings(log)
    assert len(warnings) == 1
    kwargs = warnings[0].kwargs
    assert kwargs["significant_characters"] == significant
    assert kwargs["minimum"] == 12
    assert seed not in repr(warnings[0])


@pytest.mark.parametrize("seed", ["", "CUST-OMSE-EDCD", "cust omse edcd", "Tr0ub4dor&3!xy"])
def test_ensure_does_not_warn_about_a_generated_code_or_a_full_seed(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, seed: str
) -> None:
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert _weak_seed_warnings(log) == []


_SETUP_CODE_INPUT = (
    Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "components" / "setup" / "bootstrap-code-input.tsx"
)


def _setup_field_rule() -> tuple[str, int]:
    """The alphabet and length of the /setup screen's code field, read from its component."""
    source = _SETUP_CODE_INPUT.read_text(encoding="utf-8")
    alphabet = re.search(r'^const BOOTSTRAP_ALPHABET = "([^"]+)";$', source, re.MULTILINE)
    groups = re.search(r"^const GROUPS = \[([\d, ]+)\] as const;$", source, re.MULTILINE)
    assert alphabet and groups, "the /setup code field no longer declares BOOTSTRAP_ALPHABET and GROUPS"
    # parseIncoming keeps only BOOTSTRAP_ALPHABET characters, up to TOTAL = sum(GROUPS).
    assert '.map((ch) => (BOOTSTRAP_ALPHABET.includes(ch) ? ch : ""))' in source
    assert "return filtered.slice(0, TOTAL);" in source
    return alphabet.group(1), sum(int(size) for size in groups.group(1).split(","))


def test_the_seed_check_uses_the_setup_code_field_rule() -> None:
    """The warning about seeds /setup cannot take follows what the dashboard's field accepts."""
    alphabet, length = _setup_field_rule()

    assert alphabet == bootstrap_file_mod._BOOTSTRAP_ALPHABET
    assert length == bootstrap_file_mod._SETUP_FIELD_CHARACTERS


def _not_typeable_warnings(log: MagicMock) -> list[Any]:
    return [call for call in log.warning.call_args_list if call.args == ("bootstrap_code_seed_not_typeable",)]


@pytest.mark.parametrize(
    "seed",
    [
        "WB7K-QZ3M-NP4X-HJ5R",  # 16 characters: the field submits only the first 12
        "Tr0ub4dor&3!",  # 0 and O: the field drops them
        "CUST-OMSE-EDCD",  # O
        "CUST-WMSE-EDCI",  # I
        "cust-wmse-edc1",  # 1
        "!!!!",  # nothing to type
    ],
)
def test_ensure_warns_about_a_seed_the_setup_screen_cannot_take(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, seed: str
) -> None:
    """The /setup field keeps at most 12 characters from the setup alphabet and drops the rest."""
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) == seed

    warnings = _not_typeable_warnings(log)
    assert len(warnings) == 1
    hint = warnings[0].kwargs["hint"]
    assert "/setup" in hint
    assert f"exactly 12 characters from {bootstrap_file_mod._BOOTSTRAP_ALPHABET}" in hint
    assert seed not in repr(warnings[0])


@pytest.mark.parametrize("seed", ["", "WB7K-QZ3M-NP4X", "wb7k qz3m np4x", "Wb7k-Qz3m!Np4x", "ABCD"])
def test_ensure_does_not_flag_a_seed_the_setup_screen_takes(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, seed: str
) -> None:
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert _not_typeable_warnings(log) == []


def test_the_weak_seed_hint_asks_for_a_seed_the_setup_screen_takes(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Following the hint must give a seed the /setup field can take, not just a long one."""
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "ABCD")
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)

    (warning,) = _weak_seed_warnings(log)
    assert f"exactly 12 characters from {bootstrap_file_mod._BOOTSTRAP_ALPHABET}" in warning.kwargs["hint"]
    assert "at least" not in warning.kwargs["hint"]


def _logged(log: MagicMock) -> list[Any]:
    """Every call made on the module's logger, whatever its level."""
    return [*log.debug.call_args_list, *log.info.call_args_list, *log.warning.call_args_list, *log.error.call_args_list]


@pytest.mark.parametrize("seed", ["Tr0ub4dor&3!", "WB7K-QZ3M-NP4X", "wb7k qz3m np4x", "Qz3m"])
def test_a_seed_is_never_logged(isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, seed: str) -> None:
    """The operator chose the seed and knows it; the first-boot log says where the code came from.

    Setup codes match on their ASCII letters and digits, so neither the seed as configured nor
    those characters, upper-cased or regrouped in fours, may reach the log.
    """
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) == seed

    kept = bootstrap_file_mod._seed_kept_characters(seed)
    grouped = "-".join(kept[index : index + 4] for index in range(0, len(kept), 4))
    logged = repr(_logged(log))
    for form in {seed, seed.upper(), kept, grouped}:
        assert form not in logged, form
    (written,) = [call for call in log.info.call_args_list if call.args == ("bootstrap_file_written",)]
    assert written.kwargs["code_source"] == "CONTROL_PLANE_BOOTSTRAP_CODE"
    assert "code" not in written.kwargs


def test_a_generated_code_is_logged_once(isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a seed the operator learns the code from bootstrap.txt or from this one log line."""
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) is None

    (written,) = [call for call in log.info.call_args_list if call.args == ("bootstrap_file_written",)]
    assert written.kwargs["code"] == code
    assert written.kwargs["code_source"] == "generated"
    assert repr(_logged(log)).count(str(code)) == 1


def test_the_docs_say_which_setup_code_is_logged() -> None:
    """authentication.md and .env.example: a generated code is logged once, a seed never."""
    root = Path(__file__).resolve().parents[1]
    guide = " ".join((root / "docs" / "security" / "authentication.md").read_text(encoding="utf-8").split())
    env_example = " ".join(
        line.removeprefix("#").strip() for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
    )

    assert "logs, without the seed," not in guide
    assert (
        "`bootstrap_file_written` log line carries a generated code, once, but never a seed: for a seed it"
        " names `code_source=CONTROL_PLANE_BOOTSTRAP_CODE` instead" in guide
    )
    assert "A seed set here replaces that code and is never logged." in env_example


def test_the_seed_setting_is_documented_where_operators_look() -> None:
    """CONTROL_PLANE_BOOTSTRAP_CODE, and the /setup rule for it, in .env.example and the config reference."""
    root = Path(__file__).resolve().parents[1]
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    reference = " ".join((root / "docs" / "config" / "reference.md").read_text(encoding="utf-8").split())
    release_compose = (root / "packages" / "cli" / "release" / "bundle" / "docker-compose.release.yml").read_text(
        encoding="utf-8"
    )

    assert "# CONTROL_PLANE_BOOTSTRAP_CODE=" in env_example.splitlines()
    assert bootstrap_file_mod._BOOTSTRAP_ALPHABET in env_example
    assert "- `CONTROL_PLANE_BOOTSTRAP_CODE` — " in reference
    assert f"takes at most 12 characters from `{bootstrap_file_mod._BOOTSTRAP_ALPHABET}`" in reference
    # The reference says the release bundle does not pass it; passing it means updating that sentence.
    assert "the release bundle's Compose file does not pass it" in reference
    assert "CONTROL_PLANE_BOOTSTRAP_CODE" not in release_compose


def test_ensure_does_not_overwrite_existing(isolated_bootstrap: Path) -> None:
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text("EXISTING-CODE-HERE\n", encoding="utf-8")
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code is None
    assert isolated_bootstrap.read_text(encoding="utf-8").strip() == "EXISTING-CODE-HERE"


def test_read_bootstrap_file_returns_content(isolated_bootstrap: Path) -> None:
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert bootstrap_file_mod.read_bootstrap_file() == code


def test_read_bootstrap_file_rejects_expired_content(isolated_bootstrap: Path) -> None:
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text(
        "EXPI-REDC-ODEX\nexpires_at=2000-01-01T00:00:00+00:00\nsetup_url=/setup\n",
        encoding="utf-8",
    )
    assert bootstrap_file_mod.read_bootstrap_file() is None


def test_consume_removes_file(isolated_bootstrap: Path) -> None:
    bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert isolated_bootstrap.exists()
    bootstrap_file_mod.consume_bootstrap_file()
    assert not isolated_bootstrap.exists()


def test_is_loopback_request_rejects_forwarded() -> None:
    assert bootstrap_file_mod.is_loopback_request("127.0.0.1", None) is True
    assert bootstrap_file_mod.is_loopback_request("::1", None) is True
    assert bootstrap_file_mod.is_loopback_request("127.0.0.1", "203.0.113.10") is False
    assert bootstrap_file_mod.is_loopback_request("10.0.0.5", None) is False
    assert bootstrap_file_mod.is_loopback_request(None, None) is False
