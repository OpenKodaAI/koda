"""Tests for the first-boot bootstrap-file workflow."""

from __future__ import annotations

import errno
import os
import re
from datetime import UTC, datetime, timedelta
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
def test_a_seed_is_never_logged(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], seed: str
) -> None:
    """The operator chose the seed and knows it; the first-boot log says where the code came from.

    Setup codes match on their ASCII letters and digits, so neither the seed as configured nor
    those characters, upper-cased or regrouped in fours, may reach the log or the console.
    """
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) == seed

    kept = bootstrap_file_mod._seed_kept_characters(seed)
    grouped = "-".join(kept[index : index + 4] for index in range(0, len(kept), 4))
    logged = repr(_logged(log))
    console = capsys.readouterr()
    for form in {seed, seed.upper(), kept, grouped}:
        assert form not in logged, form
        assert form not in console.out + console.err, form
    (written,) = [call for call in log.info.call_args_list if call.args == ("bootstrap_file_written",)]
    assert written.kwargs["code_source"] == "CONTROL_PLANE_BOOTSTRAP_CODE"
    assert "code" not in written.kwargs


def test_a_generated_code_is_shown_once_in_a_banner_and_never_logged(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without a seed the operator learns the code from bootstrap.txt or from one banner on stderr."""
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code is not None
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False) is None

    (written,) = [call for call in log.info.call_args_list if call.args == ("bootstrap_file_written",)]
    assert "code" not in written.kwargs
    assert written.kwargs["code_source"] == "generated"
    assert code not in repr(_logged(log))
    console = capsys.readouterr()
    assert console.err.count(code) == 1
    assert f"Koda setup code: {code}" in console.err
    assert code not in console.out


def test_the_docs_say_where_the_setup_code_is_shown() -> None:
    """authentication.md and .env.example: a generated code is shown once on stderr, a seed never."""
    root = Path(__file__).resolve().parents[1]
    guide = " ".join((root / "docs" / "security" / "authentication.md").read_text(encoding="utf-8").split())
    env_example = " ".join(
        line.removeprefix("#").strip() for line in (root / ".env.example").read_text(encoding="utf-8").splitlines()
    )

    assert "logs, without the seed," not in guide
    assert "log line carries a generated code" not in guide
    assert (
        "prints a generated code once, in a banner on stderr, never a seed. The structured log never carries"
        " the code: its `bootstrap_file_written` event names `code_source=generated` or"
        " `code_source=CONTROL_PLANE_BOOTSTRAP_CODE` instead" in guide
    )
    assert "logs it once" not in env_example
    assert "prints it once, on stderr" in env_example
    assert "A seed set here replaces that code and is never logged or printed." in env_example


def test_the_docs_say_an_expired_setup_code_is_replaced() -> None:
    """authentication.md states the TTL rule ensure_bootstrap_file follows (D-195)."""
    root = Path(__file__).resolve().parents[1]
    guide = " ".join((root / "docs" / "security" / "authentication.md").read_text(encoding="utf-8").split())

    settings = (root / "koda" / "control_plane" / "settings.py").read_text(encoding="utf-8")
    assert 'os.environ.get("CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS", "900")' in settings
    assert (
        "The code expires `CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS` (default 900, so 15 minutes) after the file"
        " is written. The next status request after that, such as reloading `/setup`, replaces the expired file"
        " with a new code and a new banner (a seed is written again, with a fresh expiry). A file without both a"
        " code line and a readable `expires_at`, such as an empty one left by a crash or one that is not UTF-8,"
        " never matches and is replaced the same way, so an expired or damaged file does not lock setup. The code"
        " is the file's first line, whatever it holds (a seed may contain `=` or any other separator), and"
        " `expires_at` is read from the lines after it. The file is published whole: the content goes to a `0600`"
        " temp file in the same directory, is fsynced, then is hard-linked to `bootstrap.txt`, which fails when"
        " that file already exists. Another replica never reads a half-written file, a code is announced only"
        " when its file is the one on disk, and a write that fails leaves no file. An install with an owner never"
        " writes the file." in guide
    )
    assert "a write that fails removes the file it started" not in guide
    assert "so an expired code never locks setup" not in guide


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
    valid = "EXISTING-CODE-HERE\nexpires_at=2999-01-01T00:00:00+00:00\n"
    isolated_bootstrap.write_text(valid, encoding="utf-8")
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)
    assert code is None
    assert isolated_bootstrap.read_text(encoding="utf-8") == valid


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


# An injected clock for the TTL tests (D-195, M1-E1-T14).
_WRITTEN_AT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
_TTL = timedelta(seconds=bootstrap_file_mod.CONTROL_PLANE_BOOTSTRAP_CODE_TTL_SECONDS)


def _file_expires_at(path: Path) -> str:
    (line,) = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("expires_at=")]
    return line.removeprefix("expires_at=")


def test_the_ttl_counts_from_when_the_file_is_written(isolated_bootstrap: Path) -> None:
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)

    assert _file_expires_at(isolated_bootstrap) == (_WRITTEN_AT + _TTL).isoformat()
    just_before = _WRITTEN_AT + _TTL - timedelta(seconds=1)
    assert bootstrap_file_mod.read_bootstrap_file(now=just_before) == code
    assert bootstrap_file_mod.read_bootstrap_file(now=_WRITTEN_AT + _TTL) is None


def test_a_file_within_its_ttl_is_kept(isolated_bootstrap: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)
    capsys.readouterr()

    just_before = _WRITTEN_AT + _TTL - timedelta(seconds=1)
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=just_before) is None
    assert isolated_bootstrap.read_text(encoding="utf-8").splitlines()[0] == code
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("elapsed", [_TTL, _TTL + timedelta(seconds=1), timedelta(days=30)])
def test_an_expired_file_is_replaced_by_a_new_code_at_the_next_status_request(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], elapsed: timedelta
) -> None:
    """Setup is no longer locked once the TTL passes: the next status request writes a fresh code."""
    old = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)
    assert old is not None
    capsys.readouterr()
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)
    later = _WRITTEN_AT + elapsed
    assert bootstrap_file_mod.read_bootstrap_file(now=later) is None

    new = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=later)

    assert new is not None and new != old
    assert isolated_bootstrap.read_text(encoding="utf-8").splitlines()[0] == new
    assert _file_expires_at(isolated_bootstrap) == (later + _TTL).isoformat()
    assert os.stat(isolated_bootstrap).st_mode & 0o777 == 0o600
    assert bootstrap_file_mod.read_bootstrap_file(now=later) == new
    # The new code gets its own banner; the structured log names neither code.
    console = capsys.readouterr()
    assert console.err.count(new) == 1
    assert old not in console.err
    (replaced,) = [call for call in log.info.call_args_list if call.args == ("bootstrap_file_expired_replaced",)]
    assert replaced.kwargs["expired_at"] == (_WRITTEN_AT + _TTL).isoformat()
    logged = repr(_logged(log))
    assert old not in logged
    assert new not in logged
    # Only the expired file is replaced: a second call keeps the new one.
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=later) is None


def test_an_expired_file_left_by_an_earlier_start_is_replaced(
    isolated_bootstrap: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text(
        "EXPI-REDC-ODEX\nexpires_at=2000-01-01T00:00:00+00:00\nsetup_url=/setup\n",
        encoding="utf-8",
    )

    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False)

    assert code is not None and code != "EXPI-REDC-ODEX"
    assert bootstrap_file_mod.read_bootstrap_file() == code
    assert capsys.readouterr().err.count(code) == 1


@pytest.mark.parametrize(
    "content",
    [
        "",  # a write that never happened: the process died, or the disk was full
        "\n\n",
        "expires_at=2999-01-01T00:00:00+00:00\nsetup_url=/setup\n",  # no code line
        "LEGA-CYCO-DEXX\n",  # no expires_at, as written before v1.0.11
        "LEGA-CYCO-DEXX\nexpires_at=not-a-date\nsetup_url=/setup\n",
        "LEGA-CYCO-DEXX\nexpires_at=\n",
    ],
)
def test_a_file_without_a_code_and_a_readable_expiry_is_replaced(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    """D-195: no file left on disk may lock setup, whatever state a crash or an old version left it in."""
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_text(content, encoding="utf-8")
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)
    # Such a file never matches a setup code: it has no code or no expiry to check.
    assert bootstrap_file_mod.read_bootstrap_file(now=_WRITTEN_AT) is None

    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)

    assert code is not None and code != "LEGA-CYCO-DEXX"
    assert isolated_bootstrap.read_text(encoding="utf-8").splitlines()[0] == code
    assert _file_expires_at(isolated_bootstrap) == (_WRITTEN_AT + _TTL).isoformat()
    assert os.stat(isolated_bootstrap).st_mode & 0o777 == 0o600
    assert bootstrap_file_mod.read_bootstrap_file(now=_WRITTEN_AT) == code
    assert capsys.readouterr().err.count(code) == 1
    (replaced,) = [call for call in log.warning.call_args_list if call.args == ("bootstrap_file_invalid_replaced",)]
    assert replaced.kwargs["path"] == str(isolated_bootstrap)
    assert "LEGA-CYCO-DEXX" not in repr(_logged(log))
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT) is None


def _short_write(fd: int, data: bytes) -> int:
    """os.write on a nearly full disk: part of the data reaches the file, without an error."""
    return _REAL_WRITE(fd, data[: len(data) // 3])


def _failed_write(fd: int, data: bytes) -> int:
    raise OSError(errno.ENOSPC, "No space left on device")


_REAL_WRITE = os.write


@pytest.mark.parametrize("write", [_failed_write, _short_write], ids=["ENOSPC", "short write"])
def test_a_failed_write_leaves_no_file_behind(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], write: Any
) -> None:
    """A code that did not reach the disk whole is never announced, and its file is removed."""
    monkeypatch.setattr(bootstrap_file_mod.os, "write", write)

    with pytest.raises(OSError):
        bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)

    monkeypatch.setattr(bootstrap_file_mod.os, "write", _REAL_WRITE)
    assert not isolated_bootstrap.exists()
    assert list(isolated_bootstrap.parent.iterdir()) == []
    assert "Koda setup code" not in capsys.readouterr().err
    # Once the disk has room again, the next status request writes a usable code.
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)
    assert code is not None
    assert bootstrap_file_mod.read_bootstrap_file(now=_WRITTEN_AT) == code


@pytest.mark.parametrize("seed", ["V0I3S1FaM01OUDRY=", "WB7K=QZ3M=NP4X", "setup_url=WB7K-QZ3M-NP4X"])
def test_a_seed_with_an_equals_sign_is_read_back(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, seed: str
) -> None:
    """The code is the file's first line, whatever it holds; only the known key=value lines are fields."""
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", seed)
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT) == seed
    written = isolated_bootstrap.read_text(encoding="utf-8")

    assert bootstrap_file_mod.read_bootstrap_file(now=_WRITTEN_AT) == seed
    # A valid file is kept: the next status request neither rewrites it nor calls it invalid.
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT) is None
    assert isolated_bootstrap.read_text(encoding="utf-8") == written
    assert not [call for call in log.warning.call_args_list if call.args == ("bootstrap_file_invalid_replaced",)]


def test_a_file_that_is_not_utf8_is_replaced(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    isolated_bootstrap.parent.mkdir(parents=True, exist_ok=True)
    isolated_bootstrap.write_bytes(b"\xff\xfeWB7K-QZ3M-NP4X\nexpires_at=2999-01-01T00:00:00+00:00\n")
    log = MagicMock()
    monkeypatch.setattr(bootstrap_file_mod, "log", log)

    assert bootstrap_file_mod.read_bootstrap_file(now=_WRITTEN_AT) is None
    code = bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)

    assert code is not None
    assert bootstrap_file_mod.read_bootstrap_file(now=_WRITTEN_AT) == code
    assert capsys.readouterr().err.count(code) == 1
    assert [call for call in log.warning.call_args_list if call.args == ("bootstrap_file_invalid_replaced",)]


def _open_fds() -> int:
    return len(os.listdir("/proc/self/fd"))


def test_a_seed_that_cannot_be_encoded_opens_no_file(isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A seed from a non-UTF-8 environment (a lone surrogate) fails before any file is created."""
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "WB7K-QZ3M-NP4\udcff")
    before = _open_fds()

    with pytest.raises(UnicodeEncodeError):
        bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)

    assert _open_fds() == before
    assert not isolated_bootstrap.exists()
    assert list(isolated_bootstrap.parent.iterdir()) == []


def test_another_replica_never_sees_a_partly_written_file(
    isolated_bootstrap: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replica B's status request lands while replica A writes: every announced code is the file's code."""
    seen_during_write: list[bool] = []
    announced: list[str | None] = []

    def write_with_a_second_replica(fd: int, data: bytes) -> int:
        monkeypatch.setattr(bootstrap_file_mod.os, "write", _REAL_WRITE)
        seen_during_write.append(isolated_bootstrap.exists())
        announced.append(bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT))
        return _REAL_WRITE(fd, data)

    monkeypatch.setattr(bootstrap_file_mod.os, "write", write_with_a_second_replica)
    announced.append(bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT))

    # bootstrap.txt appears only once it holds the whole content.
    assert seen_during_write == [False]
    codes = [code for code in announced if code is not None]
    assert len(codes) == 1
    assert isolated_bootstrap.read_text(encoding="utf-8").splitlines()[0] == codes[0]
    assert bootstrap_file_mod.read_bootstrap_file(now=_WRITTEN_AT) == codes[0]
    assert capsys.readouterr().err.count("Koda setup code") == 1
    assert os.stat(isolated_bootstrap).st_mode & 0o777 == 0o600
    # No temp file is left beside it.
    assert list(isolated_bootstrap.parent.iterdir()) == [isolated_bootstrap]


def test_an_expired_seed_file_is_written_again_with_a_fresh_ttl(
    isolated_bootstrap: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap_file_mod, "CONTROL_PLANE_BOOTSTRAP_CODE_SEED", "WB7K-QZ3M-NP4X")
    bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)
    later = _WRITTEN_AT + _TTL + timedelta(minutes=5)

    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=later) == "WB7K-QZ3M-NP4X"
    assert _file_expires_at(isolated_bootstrap) == (later + _TTL).isoformat()
    assert bootstrap_file_mod.read_bootstrap_file(now=later) == "WB7K-QZ3M-NP4X"


@pytest.mark.parametrize("elapsed", [timedelta(0), _TTL + timedelta(seconds=1), timedelta(days=30)])
def test_an_install_with_an_owner_never_writes_a_file(
    isolated_bootstrap: Path, capsys: pytest.CaptureFixture[str], elapsed: timedelta
) -> None:
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=True, now=_WRITTEN_AT + elapsed) is None
    assert not isolated_bootstrap.exists()

    # A file left from before the owner registered is removed, expired or not, never replaced.
    bootstrap_file_mod.ensure_bootstrap_file(has_owner=False, now=_WRITTEN_AT)
    capsys.readouterr()
    assert bootstrap_file_mod.ensure_bootstrap_file(has_owner=True, now=_WRITTEN_AT + elapsed) is None
    assert not isolated_bootstrap.exists()
    assert capsys.readouterr().err == ""


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
