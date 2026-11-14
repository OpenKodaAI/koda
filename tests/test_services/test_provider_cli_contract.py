"""Provider CLI contract: pins, fail-closed probes and the argv vocabulary (ADR-002 AG-02)."""

from __future__ import annotations

import dataclasses
import itertools
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services import provider_cli_contract as pcc
from koda.services.provider_runtime import ProviderCapabilities

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "provider_cli"
PROVIDERS = ("claude", "codex", "gemini")
_VERSION_OUTPUT = {
    # Claude's format is real (tests/fixtures/provider_cli); Codex and Gemini are assumed.
    "claude": "{version} (Claude Code)\n",
    "codex": "codex-cli {version}\n",
    "gemini": "{version}\n",
}


def _conforming_help(contract: pcc.ProviderCliContract, scope: str, *, drop: Sequence[str] = ()) -> str:
    """Help text that lists every visible contract token of one scope, minus ``drop``."""
    lines = [f"Usage: {contract.provider} [OPTIONS]"]
    for flag in contract.flags:
        if scope not in flag.scopes or flag.hidden or flag.token in drop:
            continue
        choices = [choice for choice in flag.choices if choice not in drop]
        suffix = f" [possible values: {', '.join(choices)}]" if choices else ""
        lines.append(f"  {flag.token} <VALUE>  Some description.{suffix}")
    return "\n".join(lines) + "\n"


class FakeCli:
    """Answers the probe commands the way a CLI binary would, without spawning anything."""

    def __init__(
        self,
        provider: str,
        *,
        version: str | None = None,
        drop: Sequence[str] = (),
        drop_in_scope: str | None = None,
        parser_output: str | None = None,
        help_overrides: dict[str, str] | None = None,
        raise_on: tuple[str, BaseException] | None = None,
    ) -> None:
        self.contract = pcc.get_contract(provider)
        self.version = version if version is not None else self.contract.pinned_version
        self.drop = tuple(drop)
        self.drop_in_scope = drop_in_scope
        self.parser_output = parser_output
        self.help_overrides = dict(help_overrides or {})
        self.raise_on = raise_on
        self.calls: list[tuple[str, ...]] = []

    async def __call__(self, argv: Sequence[str], env: Any, timeout: float) -> tuple[int, str, str]:
        args = tuple(argv[1:])
        self.calls.append(args)
        if self.raise_on is not None and self.raise_on[0] in args:
            raise self.raise_on[1]
        if args == ("--version",):
            return 0, _VERSION_OUTPUT[self.contract.provider].format(version=self.version), ""
        if args and args[-1] == "--help":
            scope = next(name for name, spec in self.contract.scopes.items() if spec.subcommand == args[:-1])
            if scope in self.help_overrides:
                return 0, self.help_overrides[scope], ""
            drop = self.drop if self.drop_in_scope in (None, scope) else ()
            return 0, _conforming_help(self.contract, scope, drop=drop), ""
        if pcc.PARSER_PROBE_CONTROL_FLAG in args:
            if self.parser_output is not None:
                return 1, "", self.parser_output
            return 1, "", f"error: unknown option '{pcc.PARSER_PROBE_CONTROL_FLAG}'\n"
        raise AssertionError(f"unexpected probe command: {argv!r}")


@pytest.fixture(autouse=True)
def _fresh_contract_cache():
    pcc.clear_cli_contract_cache()
    yield
    pcc.clear_cli_contract_cache()


@pytest.fixture
def fake_bin(tmp_path: Path):
    """Create fake executables on a private PATH and return that PATH's env."""

    def make(*names: str) -> dict[str, str]:
        for name in names:
            path = tmp_path / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        return {"PATH": str(tmp_path)}

    return make


# --- Pins -----------------------------------------------------------------------------------


def test_contract_pins_match_the_provider_cli_lockfile():
    manifest = json.loads((ROOT / "packages/provider-clis/package.json").read_text())
    lock = json.loads((ROOT / "packages/provider-clis/package-lock.json").read_text())

    for provider in PROVIDERS:
        contract = pcc.get_contract(provider)
        assert manifest["dependencies"][contract.package] == contract.pinned_version
        assert lock["packages"][""]["dependencies"][contract.package] == contract.pinned_version
        assert lock["packages"][f"node_modules/{contract.package}"]["version"] == contract.pinned_version
        assert contract.contract_id == f"{provider}@{contract.pinned_version}"
    assert pcc.pinned_versions() == {provider: pcc.get_contract(provider).pinned_version for provider in PROVIDERS}


def test_only_claude_is_marked_verified_against_real_help_output():
    assert pcc.get_contract("claude").verified_against_help is True
    for provider in ("codex", "gemini"):
        contract = pcc.get_contract(provider)
        assert contract.verified_against_help is False
        assert all(flag.verified is False for flag in contract.flags), provider


def test_verified_claude_tokens_appear_in_the_real_pinned_help_output():
    contract = pcc.get_contract("claude")
    help_text = (FIXTURES / f"claude-{contract.pinned_version}-help.txt").read_text()

    for flag in contract.flags:
        assert flag.verified is not flag.hidden, flag.token
        if flag.verified:
            assert pcc.help_lists_token(help_text, flag.token), flag.token
            for choice in flag.choices:
                assert pcc.help_lists_token(help_text, choice), (flag.token, choice)
        else:
            # Hidden options are accepted by the parser but missing from --help, which is
            # exactly why the runtime probe checks them with a parser probe instead.
            assert not pcc.help_lists_token(help_text, flag.token), flag.token


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_real_claude_outputs_satisfy_the_contract(fake_bin):
    contract = pcc.get_contract("claude")
    outputs = {
        "--version": (FIXTURES / f"claude-{contract.pinned_version}-version.txt").read_text(),
        "--help": (FIXTURES / f"claude-{contract.pinned_version}-help.txt").read_text(),
        "parser": (FIXTURES / f"claude-{contract.pinned_version}-parser-probe.txt").read_text(),
    }

    async def recorded(argv: Sequence[str], env: Any, timeout: float) -> tuple[int, str, str]:
        args = tuple(argv[1:])
        if args == ("--version",):
            return 0, outputs["--version"], ""
        if args == ("--help",):
            return 0, outputs["--help"], ""
        assert args == pcc.parser_probe_args(contract)
        return 1, "", outputs["parser"]

    with patch.object(pcc, "_run_probe_command", recorded):
        check = await pcc.verify_provider_cli("claude", ("claude",), env=fake_bin("claude"))

    assert check.ok, check.error
    assert check.observed_version == contract.pinned_version


# --- Fail-closed probe ----------------------------------------------------------------------


@pytest.mark.real_cli_contract_probe
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.asyncio
async def test_pinned_version_with_conforming_help_is_verified(provider, fake_bin):
    fake = FakeCli(provider)
    with patch.object(pcc, "_run_probe_command", fake):
        check = await pcc.verify_provider_cli(provider, (provider,), env=fake_bin(provider))

    assert check.ok, check.error
    assert check.reason == ""
    assert ("--version",) in fake.calls


@pytest.mark.real_cli_contract_probe
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.asyncio
async def test_version_mismatch_reports_unverified_cli_version(provider, fake_bin):
    fake = FakeCli(provider, version="9.9.9")
    with patch.object(pcc, "_run_probe_command", fake):
        check = await pcc.verify_provider_cli(provider, (provider,), env=fake_bin(provider))

    assert check.ok is False
    assert check.reason == pcc.REASON_UNVERIFIED_CLI_VERSION == "unavailable:unverified_cli_version"
    assert check.observed_version == "9.9.9"
    assert check.error.startswith("unavailable:unverified_cli_version: ")
    assert "9.9.9" in check.error and pcc.get_contract(provider).pinned_version in check.error
    # Nothing else is run against a binary whose version is not the pinned one.
    assert fake.calls == [("--version",)]
    assert check.scope_ok(next(iter(pcc.get_contract(provider).scopes))) is False


@pytest.mark.real_cli_contract_probe
@pytest.mark.parametrize("version_output", ["", "Claude Code\n", "2.1.325-beta.1 (Claude Code)\n"])
@pytest.mark.asyncio
async def test_unparseable_or_prerelease_version_is_unverified(version_output, fake_bin):
    async def run(argv: Sequence[str], env: Any, timeout: float) -> tuple[int, str, str]:
        return 0, version_output, ""

    with patch.object(pcc, "_run_probe_command", run):
        check = await pcc.verify_provider_cli("claude", ("claude",), env=fake_bin("claude"))

    assert check.ok is False
    assert check.reason == pcc.REASON_UNVERIFIED_CLI_VERSION


@pytest.mark.real_cli_contract_probe
@pytest.mark.parametrize(
    ("provider", "token"),
    [
        ("claude", "--permission-mode"),
        ("claude", "--output-format"),
        ("codex", "--sandbox"),
        ("codex", "-c"),
        ("gemini", "--approval-mode"),
        ("gemini", "--output-format"),
    ],
)
@pytest.mark.asyncio
async def test_help_without_a_contract_token_fails_closed(provider, token, fake_bin):
    fake = FakeCli(provider, drop=[token])
    with patch.object(pcc, "_run_probe_command", fake):
        check = await pcc.verify_provider_cli(provider, (provider,), env=fake_bin(provider))

    assert check.ok is False
    assert check.reason == pcc.REASON_UNVERIFIED_CLI_VERSION
    assert token in check.error
    assert any(missing.token == token for missing in check.missing)


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_help_without_a_contract_choice_fails_closed(fake_bin):
    fake = FakeCli("claude", drop=["dontAsk"])
    with patch.object(pcc, "_run_probe_command", fake):
        check = await pcc.verify_provider_cli("claude", ("claude",), env=fake_bin("claude"))

    assert check.ok is False
    assert any(missing.token == "--permission-mode=dontAsk" for missing in check.missing)


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_a_missing_resume_token_only_fails_the_resume_scope(fake_bin):
    fake = FakeCli("codex", drop=["--dangerously-bypass-approvals-and-sandbox"], drop_in_scope="exec_resume")
    with patch.object(pcc, "_run_probe_command", fake):
        check = await pcc.verify_provider_cli("codex", ("codex",), env=fake_bin("codex"))

    assert check.ok is False
    assert check.scope_ok("exec") is True
    assert check.scope_ok("exec_resume") is False


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_hidden_flag_rejected_by_the_parser_fails_closed(fake_bin):
    fake = FakeCli("claude", parser_output="error: unknown option '--max-turns'\n")
    with patch.object(pcc, "_run_probe_command", fake):
        check = await pcc.verify_provider_cli("claude", ("claude",), env=fake_bin("claude"))

    assert check.ok is False
    assert check.reason == pcc.REASON_UNVERIFIED_CLI_VERSION
    assert any(missing.token == "--max-turns" for missing in check.missing)


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_parser_that_does_not_reject_unknown_options_cannot_verify_hidden_flags(fake_bin):
    fake = FakeCli("claude", parser_output="Error: Input must be provided\n")
    with patch.object(pcc, "_run_probe_command", fake):
        check = await pcc.verify_provider_cli("claude", ("claude",), env=fake_bin("claude"))

    assert check.ok is False
    hidden = {flag.token for flag in pcc.get_contract("claude").flags if flag.hidden}
    assert hidden and hidden <= {missing.token for missing in check.missing}


@pytest.mark.real_cli_contract_probe
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.asyncio
async def test_missing_binary_reports_not_installed(provider, tmp_path):
    runner = AsyncMock()
    with patch.object(pcc, "_run_probe_command", runner):
        check = await pcc.verify_provider_cli(provider, (provider,), env={"PATH": str(tmp_path)})

    assert check.ok is False
    assert check.reason == pcc.REASON_CLI_NOT_INSTALLED
    runner.assert_not_awaited()


@pytest.mark.real_cli_contract_probe
@pytest.mark.parametrize("error", [TimeoutError(), OSError("exec format error"), RuntimeError("unexpected")])
@pytest.mark.asyncio
async def test_probe_errors_fail_closed_and_are_not_cached(error, fake_bin):
    env = fake_bin("gemini")
    failing = FakeCli("gemini", raise_on=("--help", error))
    with patch.object(pcc, "_run_probe_command", failing):
        check = await pcc.verify_provider_cli("gemini", ("gemini",), env=env)
    assert check.ok is False
    assert check.reason == pcc.REASON_CLI_PROBE_FAILED

    healthy = FakeCli("gemini")
    with patch.object(pcc, "_run_probe_command", healthy):
        check = await pcc.verify_provider_cli("gemini", ("gemini",), env=env)
    assert check.ok is True
    assert healthy.calls


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_successful_check_is_cached_until_the_binary_changes(fake_bin, tmp_path):
    env = fake_bin("claude")
    first = FakeCli("claude")
    with patch.object(pcc, "_run_probe_command", first):
        assert (await pcc.verify_provider_cli("claude", ("claude",), env=env)).ok
        assert (await pcc.verify_provider_cli("claude", ("claude",), env=env)).ok
    assert first.calls.count(("--version",)) == 1

    binary = tmp_path / "claude"
    binary.write_text("#!/bin/sh\necho replaced\n")
    stat = binary.stat()
    os.utime(binary, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    replaced = FakeCli("claude", version="2.0.0")
    with patch.object(pcc, "_run_probe_command", replaced):
        check = await pcc.verify_provider_cli("claude", ("claude",), env=env)
    assert check.ok is False
    assert check.reason == pcc.REASON_UNVERIFIED_CLI_VERSION


# --- Argv vocabulary ------------------------------------------------------------------------


def test_validate_args_rejects_a_flag_outside_the_contract():
    with pytest.raises(pcc.ProviderCliContractError, match="--dangerously-skip-permissions"):
        pcc.validate_args("claude", ["-p", "--model", "m", "--dangerously-skip-permissions"])


def test_validate_args_rejects_a_choice_outside_the_contract():
    with pytest.raises(pcc.ProviderCliContractError, match="acceptEdits"):
        pcc.validate_args("claude", ["-p", "--permission-mode", "acceptEdits"])
    with pytest.raises(pcc.ProviderCliContractError, match="yolo-plus"):
        pcc.validate_args("gemini", ["--approval-mode", "yolo-plus"])


def test_validate_args_rejects_equals_forms_and_missing_values():
    with pytest.raises(pcc.ProviderCliContractError):
        pcc.validate_args("claude", ["-p", "--model=opus"])
    with pytest.raises(pcc.ProviderCliContractError):
        pcc.validate_args("claude", ["-p", "--model"])
    with pytest.raises(pcc.ProviderCliContractError):
        pcc.validate_args("codex", ["exec", "--json", "--image", "-"])


def test_validate_args_checks_codex_config_keys_and_values():
    pcc.validate_args("codex", ["exec", "-c", 'approval_policy="never"', "-"])
    with pytest.raises(pcc.ProviderCliContractError, match="sandbox_permissions"):
        pcc.validate_args("codex", ["exec", "-c", 'sandbox_permissions=["disk-full-read-access"]', "-"])
    with pytest.raises(pcc.ProviderCliContractError, match="approval_policy"):
        pcc.validate_args("codex", ["exec", "-c", 'approval_policy="yolo"', "-"])
    with pytest.raises(pcc.ProviderCliContractError):
        pcc.validate_args("codex", ["exec", "-c", "no-equals-sign", "-"])


def test_validate_args_rejects_unknown_subcommands_and_extra_positionals():
    with pytest.raises(pcc.ProviderCliContractError):
        pcc.validate_args("codex", ["login", "--json"])
    with pytest.raises(pcc.ProviderCliContractError):
        pcc.validate_args("codex", ["exec", "--json", "extra", "-"])
    with pytest.raises(pcc.ProviderCliContractError):
        pcc.validate_args("claude", ["-p", "do something"])
    with pytest.raises(pcc.ProviderCliContractError, match="--sandbox"):
        pcc.validate_args("codex", ["exec", "resume", "--sandbox", "read-only", "thread", "-"])


def test_validate_args_treats_flag_values_as_data():
    pcc.validate_args("gemini", ["--model", "gemini-2.5-pro", "--prompt", "--yolo please"])
    pcc.validate_args("claude", ["-p", "--append-system-prompt", "--restricted is not a flag here"])


def test_level_profiles_only_use_current_contract_tokens():
    expected_floors = {"claude": "none", "codex": "read_only", "gemini": "read_only"}
    for provider in PROVIDERS:
        contract = pcc.get_contract(provider)
        assert set(contract.levels) == set(pcc.BUILTIN_TOOL_LEVELS), provider
        assert contract.floor == expected_floors[provider]
        legacy = {flag.token for flag in contract.flags if flag.legacy}
        legacy_choices = {(flag.token, choice) for flag in contract.flags for choice in flag.legacy_choices}
        scope = next(iter(contract.scopes))
        subcommand = list(contract.scopes[scope].subcommand)
        positionals = ["-"] if provider == "codex" else []
        for level, profile in contract.levels.items():
            if profile is None:
                continue
            args = [*contract.base_args, *profile.args]
            pcc.validate_args(provider, [*subcommand, *args, *positionals])
            tokens = set(args)
            assert not tokens & legacy, (provider, level)
            assert not {(a, b) for a, b in itertools.pairwise(args)} & legacy_choices, (provider, level)
            # Nothing is proven self-confined or resume-safe until the live checks of AG-23..25.
            assert profile.self_confined is False, (provider, level)
        if provider == "codex":
            assert contract.inner_sandbox_ok is False
            assert all(p is None or p.resume_args is None for p in contract.levels.values())
            assert contract.levels["none"] is None
            assert contract.levels["workspace_write"] is None


def test_no_contract_token_enables_bypass_flags_outside_the_legacy_set():
    claude = pcc.get_contract("claude")
    tokens = {flag.token for flag in claude.flags}
    assert "--dangerously-skip-permissions" not in tokens
    assert "--mcp-config" not in tokens
    assert "--setting-sources" not in tokens
    assert "--bare" not in tokens
    permission_mode = next(flag for flag in claude.flags if flag.token == "--permission-mode")
    assert set(permission_mode.legacy_choices) == {"bypassPermissions", "plan"}


def test_effort_values_known_to_koda_are_inside_the_contract():
    from koda import provider_models

    contract_values = {
        "claude": set(next(f for f in pcc.get_contract("claude").flags if f.token == "--effort").choices),
        "codex": set(
            next(k for k in pcc.get_contract("codex").config_keys if k.key == "model_reasoning_effort").choices
        ),
    }
    for provider, allowed in contract_values.items():
        keys = {key for key in provider_models._GENERAL_MODEL_METADATA if key[0] == provider}
        keys |= {key for key in provider_models._EFFORT_CAPABILITY_OVERRIDES if key[0] == provider}
        for _, model in keys:
            capability = provider_models.get_model_effort_capability(provider, model)
            if capability and capability["kind"] == "enum":
                assert set(capability["values"]) <= allowed, (provider, model)


# --- Builders cannot emit a token that is not in the contract -------------------------------


def test_every_claude_builder_variant_is_inside_the_contract():
    from koda.services import claude_runner

    for permission_mode, dry_run, session, system, images, effort, budget in itertools.product(
        (None, "bypassPermissions", "plan"),
        (False, True),
        (None, "sess-1"),
        (None, "be brief"),
        (None, ["/tmp/a.png"]),
        (None, "high"),
        (0.0, 1.5),
    ):
        cmd = claude_runner._build_cmd(
            "claude-opus-4-7",
            budget,
            session,
            system,
            images,
            permission_mode=permission_mode,
            max_turns=7,
            dry_run=dry_run,
            effort=effort,
        )
        assert cmd[0] == "claude"
        pcc.validate_args("claude", cmd[1:])


def test_claude_streaming_argv_is_unchanged():
    from koda.services import claude_runner

    cmd = claude_runner._build_cmd("claude-opus-4-7", 0.0, None, "sys", None, permission_mode="bypassPermissions")
    assert cmd == [
        "claude",
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--model",
        "claude-opus-4-7",
        "--max-turns",
        "25",
        "--permission-mode",
        "bypassPermissions",
        "--append-system-prompt",
        "sys",
    ]


@pytest.mark.parametrize("sandbox", ["danger-full-access", "workspace-write", "read-only"])
@pytest.mark.parametrize("skip_git", [True, False])
def test_every_codex_builder_variant_is_inside_the_contract(sandbox, skip_git):
    from koda.services import codex_runner

    with (
        patch.object(codex_runner, "CODEX_SANDBOX", sandbox),
        patch.object(codex_runner, "CODEX_SKIP_GIT_REPO_CHECK", skip_git),
    ):
        for system, images, effort, dry_run in itertools.product(
            (None, "be brief"), (None, ["/tmp/a.png", "/tmp/b.png"]), (None, "high", "minimal"), (False, True)
        ):
            new_turn = codex_runner._build_cmd(
                "new_turn", "gpt-5.5", "/tmp/work", None, system, images, dry_run=dry_run, effort=effort
            )
            pcc.validate_args("codex", new_turn[1:])
            assert new_turn[-1] == "-"
            if not dry_run:
                resume = codex_runner._build_cmd(
                    "resume_turn", "gpt-5.5", "/tmp/work", "thread-1", system, images, effort=effort
                )
                pcc.validate_args("codex", resume[1:])
                assert resume[-2:] == ["thread-1", "-"]


def test_every_gemini_builder_variant_is_inside_the_contract():
    from koda.services import gemini_runner

    with patch("koda.services.provider_auth.resolve_provider_command", return_value=("gemini",)):
        for permission_mode, dry_run, output_format in itertools.product(
            (None, "plan", "read_only", "acceptEdits", "auto_edit", "bypassPermissions", "yolo", "other"),
            (False, True),
            ("json", "text"),
        ):
            cmd = gemini_runner._build_cmd(
                model="gemini-2.5-pro",
                work_dir="/tmp/work",
                prompt="-- looks like a flag",
                permission_mode=permission_mode,
                dry_run=dry_run,
                output_format=output_format,
            )
            assert cmd[0] == "gemini"
            pcc.validate_args("gemini", cmd[1:])


def _without_flag(provider: str, token: str) -> pcc.ProviderCliContract:
    contract = pcc.get_contract(provider)
    return dataclasses.replace(contract, flags=tuple(flag for flag in contract.flags if flag.token != token))


def test_claude_builder_refuses_a_token_missing_from_the_contract(monkeypatch):
    from koda.services import claude_runner

    monkeypatch.setitem(pcc.CONTRACTS, "claude", _without_flag("claude", "--verbose"))
    with pytest.raises(pcc.ProviderCliContractError, match="--verbose"):
        claude_runner._build_cmd("claude-opus-4-7", 0.0, None, None, None)


def test_codex_builders_refuse_a_token_missing_from_the_contract(monkeypatch):
    from koda.services import codex_runner

    monkeypatch.setitem(pcc.CONTRACTS, "codex", _without_flag("codex", "--json"))
    with pytest.raises(pcc.ProviderCliContractError, match="--json"):
        codex_runner._build_new_turn_cmd("gpt-5.5", "/tmp/work", None, None)
    with pytest.raises(pcc.ProviderCliContractError, match="--json"):
        codex_runner._build_resume_turn_cmd("gpt-5.5", "thread-1", None, None)


def test_gemini_builder_refuses_a_token_missing_from_the_contract(monkeypatch):
    from koda.services import gemini_runner

    monkeypatch.setitem(pcc.CONTRACTS, "gemini", _without_flag("gemini", "--include-directories"))
    with (
        patch("koda.services.provider_auth.resolve_provider_command", return_value=("gemini",)),
        pytest.raises(pcc.ProviderCliContractError, match="--include-directories"),
    ):
        gemini_runner._build_cmd(
            model="gemini-2.5-pro",
            work_dir="/tmp/work",
            prompt="hi",
            permission_mode=None,
            dry_run=False,
            output_format="json",
        )


def _ready(provider: str) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider=provider, turn_mode="new_turn", status="ready", can_execute=True, supports_native_resume=False
    )


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.asyncio
async def test_runs_fail_closed_without_spawning_when_argv_leaves_the_contract(monkeypatch, streaming):
    from koda.services import claude_runner, codex_runner, gemini_runner

    monkeypatch.setitem(pcc.CONTRACTS, "claude", _without_flag("claude", "--model"))
    monkeypatch.setitem(pcc.CONTRACTS, "codex", _without_flag("codex", "--model"))
    monkeypatch.setitem(pcc.CONTRACTS, "gemini", _without_flag("gemini", "--model"))
    spawn = MagicMock(side_effect=AssertionError("a process was spawned"))
    runners = {
        "claude": (claude_runner.run_claude, claude_runner.run_claude_streaming),
        "codex": (codex_runner.run_codex, codex_runner.run_codex_streaming),
        "gemini": (gemini_runner.run_gemini, gemini_runner.run_gemini_streaming),
    }
    with (
        patch("asyncio.create_subprocess_exec", spawn),
        patch("koda.services.provider_auth.resolve_provider_command", return_value=("gemini",)),
        patch("koda.services.resilience.check_breaker", return_value=None),
    ):
        for provider, (run, run_streaming) in runners.items():
            kwargs: dict[str, Any] = {
                "query": "hi",
                "work_dir": "/tmp",
                "model": "m",
                "capabilities": _ready(provider),
            }
            if streaming:
                metadata: dict[str, Any] = {}
                chunks = [chunk async for chunk in run_streaming(metadata_collector=metadata, **kwargs)]
                assert chunks == [], provider
                assert metadata["error"] is True, provider
                assert metadata["error_kind"] == "adapter_contract", provider
                assert metadata["retryable"] is False, provider
                assert "--model" in metadata["error_message"], provider
            else:
                result = await run(**kwargs)
                assert result["error"] is True, provider
                assert result["_error_kind"] == "adapter_contract", provider
                assert result["_retryable"] is False, provider
                assert "--model" in result["result"], provider
    spawn.assert_not_called()


# --- Runner capabilities --------------------------------------------------------------------


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_claude_capabilities_are_unavailable_on_a_version_mismatch(fake_bin, monkeypatch):
    from koda.services import claude_runner

    monkeypatch.setenv("PATH", fake_bin("claude")["PATH"])
    auth_probe = AsyncMock()
    claude_runner.clear_claude_capability_cache()
    with (
        patch.object(pcc, "_run_probe_command", FakeCli("claude", version="2.1.300")),
        patch.object(claude_runner, "_probe_claude_auth_status", auth_probe),
    ):
        capabilities = await claude_runner.get_claude_capabilities("new_turn")
    claude_runner.clear_claude_capability_cache()

    assert capabilities.can_execute is False
    assert capabilities.status == "unavailable"
    assert capabilities.errors[0].startswith("unavailable:unverified_cli_version")
    assert capabilities.checked_via == "cli_contract"
    auth_probe.assert_not_awaited()


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_claude_capabilities_run_the_auth_probe_after_a_verified_contract(fake_bin, monkeypatch):
    from koda.services import claude_runner

    monkeypatch.setenv("PATH", fake_bin("claude")["PATH"])
    ready = ProviderCapabilities(
        provider="claude", turn_mode="new_turn", status="ready", can_execute=True, supports_native_resume=True
    )
    claude_runner.clear_claude_capability_cache()
    with (
        patch.object(pcc, "_run_probe_command", FakeCli("claude")),
        patch.object(claude_runner, "_probe_claude_auth_status", AsyncMock(return_value=ready)) as auth_probe,
    ):
        capabilities = await claude_runner.get_claude_capabilities("new_turn")
    claude_runner.clear_claude_capability_cache()

    assert capabilities.can_execute is True
    auth_probe.assert_awaited_once()


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_codex_capabilities_are_unavailable_on_a_version_mismatch(fake_bin, monkeypatch):
    from koda.services import codex_runner

    monkeypatch.setenv("PATH", fake_bin("codex")["PATH"])
    login = AsyncMock(return_value=(0, "Logged in using ChatGPT", ""))
    codex_runner.clear_codex_capability_cache()
    with (
        patch.object(pcc, "_run_probe_command", FakeCli("codex", version="0.168.0")),
        patch.object(codex_runner, "_read_login_status", login),
    ):
        new_turn = await codex_runner.get_codex_capabilities("new_turn")
        resume = await codex_runner.get_codex_capabilities("resume_turn")
    codex_runner.clear_codex_capability_cache()

    for capabilities in (new_turn, resume):
        assert capabilities.can_execute is False
        assert capabilities.errors[0].startswith("unavailable:unverified_cli_version")
    assert new_turn.status == "unavailable"
    login.assert_not_awaited()


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_codex_resume_degrades_alone_when_only_its_help_lacks_a_token(fake_bin, monkeypatch):
    from koda.services import codex_runner

    monkeypatch.setenv("PATH", fake_bin("codex")["PATH"])
    codex_runner.clear_codex_capability_cache()
    fake = FakeCli("codex", drop=["--image"], drop_in_scope="exec_resume")
    with (
        patch.object(pcc, "_run_probe_command", fake),
        patch.object(codex_runner, "CODEX_SANDBOX", "danger-full-access"),
        patch.object(codex_runner, "_read_login_status", AsyncMock(return_value=(0, "Logged in using ChatGPT", ""))),
    ):
        new_turn = await codex_runner.get_codex_capabilities("new_turn")
        resume = await codex_runner.get_codex_capabilities("resume_turn")
    codex_runner.clear_codex_capability_cache()

    assert new_turn.can_execute is True
    assert resume.can_execute is False
    assert resume.status == "degraded"
    assert any("--image" in error for error in resume.errors)


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_gemini_capabilities_are_unavailable_on_a_version_mismatch(fake_bin, monkeypatch):
    from koda.services import gemini_runner

    monkeypatch.setenv("PATH", fake_bin("gemini")["PATH"])
    monkeypatch.setenv("GEMINI_AUTH_MODE", "api_key")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    gemini_runner.clear_gemini_capability_cache()
    with patch.object(pcc, "_run_probe_command", FakeCli("gemini", version="0.67.0")):
        capabilities = await gemini_runner.get_gemini_capabilities("new_turn")
    gemini_runner.clear_gemini_capability_cache()

    assert capabilities.can_execute is False
    assert capabilities.errors[0].startswith("unavailable:unverified_cli_version")


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_missing_gemini_binary_is_unavailable_even_when_npx_exists(fake_bin, monkeypatch):
    from koda.services import gemini_runner

    monkeypatch.setenv("PATH", fake_bin("npx")["PATH"])
    monkeypatch.setenv("GEMINI_AUTH_MODE", "api_key")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    runner = AsyncMock()
    gemini_runner.clear_gemini_capability_cache()
    with patch.object(pcc, "_run_probe_command", runner):
        capabilities = await gemini_runner.get_gemini_capabilities("new_turn")
    gemini_runner.clear_gemini_capability_cache()

    assert capabilities.can_execute is False
    assert capabilities.errors[0].startswith("unavailable:cli_not_installed")
    runner.assert_not_awaited()


# --- Command-line check used by CI and inside the images ------------------------------------


@pytest.mark.real_cli_contract_probe
def test_main_reports_every_provider_and_fails_when_one_is_unverified(fake_bin, monkeypatch, capsys):
    monkeypatch.setenv("PATH", fake_bin("claude", "codex", "gemini")["PATH"])
    fakes = {provider: FakeCli(provider) for provider in PROVIDERS}
    fakes["codex"] = FakeCli("codex", version="0.1.0")

    async def run(argv: Sequence[str], env: Any, timeout: float) -> tuple[int, str, str]:
        return await fakes[Path(argv[0]).name](argv, env, timeout)

    with patch.object(pcc, "_run_probe_command", run):
        exit_code = pcc.main([])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert {entry["provider"] for entry in report} == set(PROVIDERS)
    by_provider = {entry["provider"]: entry for entry in report}
    assert by_provider["claude"]["ok"] is True
    assert by_provider["codex"]["ok"] is False
    assert by_provider["codex"]["reason"] == pcc.REASON_UNVERIFIED_CLI_VERSION
