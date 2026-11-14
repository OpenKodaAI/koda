"""Provider CLI contract: pins, fail-closed probes and the argv vocabulary (ADR-002 AG-02)."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import itertools
import json
import os
import shutil
import sys
import time
from collections.abc import Iterator, Sequence
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
            # The flag has its own option entry, and each choice is documented inside it.
            entries = pcc.help_option_entries(help_text, flag.token)
            assert entries, flag.token
            for choice in flag.choices:
                assert any(pcc.help_lists_token(entry, choice) for entry in entries), (flag.token, choice)
        else:
            # Hidden options are accepted by the parser but missing from --help, which is
            # exactly why the runtime probe checks them with a parser probe instead.
            assert not pcc.help_lists_token(help_text, flag.token), flag.token
            assert pcc.help_option_entries(help_text, flag.token) == [], flag.token


def test_help_option_entries_end_at_the_next_option_or_section():
    help_text = (
        "Usage: cli [options]\n"
        "Options:\n"
        "  -o, --output-format <format>  Output format\n"
        '                                (choices: "text", "json")\n'
        "  --tools <tools...>            Use --output-format=json with this\n"
        "      a wrapped description line\n"
        "                                yolo\n"
        "      --sandbox\n"
        "          Sandbox policy\n"
        "\n"
        "          - read-only: no writes\n"
        "Commands:\n"
        "  run  default plan\n"
    )

    output_format = pcc.help_option_entries(help_text, "--output-format")
    assert len(output_format) == 1
    assert pcc.help_lists_token(output_format[0], "json")
    assert not pcc.help_lists_token(output_format[0], "yolo")
    # An option mentioned inside another option's description has no entry of its own.
    assert pcc.help_option_entries(help_text, "-o") == output_format
    assert len(pcc.help_option_entries(help_text, "--tools")) == 1
    assert pcc.help_lists_token(pcc.help_option_entries(help_text, "--tools")[0], "yolo")
    sandbox = pcc.help_option_entries(help_text, "--sandbox")
    assert len(sandbox) == 1 and pcc.help_lists_token(sandbox[0], "read-only")
    assert not pcc.help_lists_token(sandbox[0], "plan")
    assert pcc.help_option_entries(help_text, "--json") == []


def _real_claude_outputs() -> dict[str, str]:
    contract = pcc.get_contract("claude")
    return {
        "--version": (FIXTURES / f"claude-{contract.pinned_version}-version.txt").read_text(),
        "--help": (FIXTURES / f"claude-{contract.pinned_version}-help.txt").read_text(),
        "parser": (FIXTURES / f"claude-{contract.pinned_version}-parser-probe.txt").read_text(),
    }


def _recorded_claude(outputs: dict[str, str]):
    contract = pcc.get_contract("claude")

    async def recorded(argv: Sequence[str], env: Any, timeout: float) -> tuple[int, str, str]:
        args = tuple(argv[1:])
        if args == ("--version",):
            return 0, outputs["--version"], ""
        if args == ("--help",):
            return 0, outputs["--help"], ""
        assert args == pcc.parser_probe_args(contract)
        return 1, "", outputs["parser"]

    return recorded


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_a_choice_mentioned_only_outside_its_flag_entry_fails_closed(fake_bin):
    """Review AG-02 r1: ``json`` must not be satisfied by ``~/.claude.json`` elsewhere in --help."""
    outputs = _real_claude_outputs()
    pad = "\n" + " " * 40
    edited = outputs["--help"]
    for old, new in (
        (f'"json" (single{pad}result), or ', ""),
        (f'(choices: "text", "json",{pad}"stream-json")', f'(choices: "text",{pad}"stream-json")'),
    ):
        assert edited.count(old) == 1, old
        edited = edited.replace(old, new)
    entry = pcc.help_option_entries(edited, "--output-format")
    assert entry and not pcc.help_lists_token(entry[0], "json")
    assert pcc.help_lists_token(edited, "json")  # still present elsewhere: '~/.claude.json'

    with patch.object(pcc, "_run_probe_command", _recorded_claude({**outputs, "--help": edited})):
        check = await pcc.verify_provider_cli("claude", ("claude",), env=fake_bin("claude"))

    assert check.ok is False
    assert check.reason == pcc.REASON_UNVERIFIED_CLI_VERSION
    assert pcc.MissingToken("root", "--output-format=json") in check.missing


@pytest.mark.real_cli_contract_probe
@pytest.mark.asyncio
async def test_a_flag_mentioned_only_inside_another_description_fails_closed(fake_bin):
    """``--append-system-prompt`` also appears in ``--bare``'s description; that is not its entry."""
    outputs = _real_claude_outputs()
    help_text = outputs["--help"]
    entry = (
        "  --append-system-prompt <prompt>       Append a system prompt to the default\n"
        "                                        system prompt\n"
    )
    assert entry in help_text
    edited = help_text.replace(entry, "")
    assert pcc.help_lists_token(edited, "--append-system-prompt")  # '--append-system-prompt[-file]'

    with patch.object(pcc, "_run_probe_command", _recorded_claude({**outputs, "--help": edited})):
        check = await pcc.verify_provider_cli("claude", ("claude",), env=fake_bin("claude"))

    assert check.ok is False
    assert check.missing == (pcc.MissingToken("root", "--append-system-prompt"),)


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


@pytest.mark.parametrize(
    "override",
    [
        'mcp_servers={evil={command="sh",args=["-c","id"]}}',
        'mcp_servers={"evil":{"command":"sh","args":["-c","id"]}}',
        "tools.web_search=true",
        'tools.web_search="false"',
        "tools.web_search=0",
        "shell_environment_policy.exclude=[]",
        'shell_environment_policy.exclude=["*_API_KEY"]',
    ],
)
@pytest.mark.parametrize("scope", [["exec"], ["exec", "resume"]])
def test_codex_security_config_keys_only_take_the_value_the_adr_fixes(override, scope):
    """Review AG-02 r1: MCP servers, web search and the env passthrough cannot be re-enabled."""
    positionals = ["-"] if scope == ["exec"] else ["thread-1", "-"]
    with pytest.raises(pcc.ProviderCliContractError, match=override.partition("=")[0]):
        pcc.validate_args("codex", [*scope, "-c", override, *positionals])


def test_codex_pinned_config_keys_match_base_args_and_accept_equivalent_literals():
    contract = pcc.get_contract("codex")
    pinned = {spec.key: spec.value for spec in contract.config_keys if spec.value is not None}
    assert set(pinned) == {"mcp_servers", "tools.web_search", "shell_environment_policy.exclude"}
    overrides = {arg for flag, arg in itertools.pairwise(contract.base_args) if flag == "-c"}
    for key, value in pinned.items():
        assert f"{key}={value}" in overrides, key
    spaced = 'shell_environment_policy.exclude=["*_API_KEY", "*TOKEN*", "*SECRET*", "POSTGRES*", "KNOWLEDGE_V2_S3*"]'
    pcc.validate_args("codex", ["exec", "-c", spaced, "-c", "mcp_servers={ }", "-c", "tools.web_search=false", "-"])


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


def test_gemini_builder_validates_everything_after_the_executable():
    """Review AG-02 r1: tokens that come with the resolved command are argv too."""
    from koda.services import gemini_runner

    with (
        patch("koda.services.provider_auth.resolve_provider_command", return_value=("gemini", "--yolo")),
        pytest.raises(pcc.ProviderCliContractError, match="--yolo"),
    ):
        gemini_runner._build_cmd(
            model="gemini-2.5-pro",
            work_dir="/tmp/work",
            prompt="hi",
            permission_mode=None,
            dry_run=False,
            output_format="json",
        )


@pytest.mark.parametrize("configured", ["gemini --yolo --sandbox=false", "npx -y @google/gemini-cli"])
def test_gemini_bin_is_one_executable_path_never_a_command_line(fake_bin, configured):
    from koda.services import provider_auth

    env = fake_bin("gemini", "npx")
    with pytest.raises(FileNotFoundError):
        provider_auth.resolve_provider_command("gemini", base_env={**env, "GEMINI_BIN": configured})
    assert provider_auth.provider_command_present("gemini", base_env={**env, "GEMINI_BIN": configured}) is False


def test_gemini_bin_path_is_used_verbatim(tmp_path):
    from koda.services import provider_auth

    binary = tmp_path / "pinned clis" / "gemini"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)

    command = provider_auth.resolve_provider_command(
        "gemini", base_env={"PATH": str(tmp_path), "GEMINI_BIN": f"  {binary}  "}
    )
    assert command == (str(binary),)


@pytest.mark.real_cli_contract_probe
@pytest.mark.parametrize("command", [("npx", "-y", "@google/gemini-cli"), ("gemini", "--yolo")])
@pytest.mark.asyncio
async def test_probe_refuses_a_command_line_instead_of_one_executable(fake_bin, command):
    """The fingerprint identifies one file; ``npx`` resolving a newer package would keep it."""
    runner = AsyncMock(return_value=(0, "0.68.0\n", ""))
    with patch.object(pcc, "_run_probe_command", runner):
        check = await pcc.verify_provider_cli("gemini", command, env=fake_bin("gemini", "npx"))

    assert check.ok is False
    assert check.reason == pcc.REASON_UNVERIFIED_CLI_VERSION
    assert "one executable" in check.detail
    runner.assert_not_awaited()


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


def _codex_check(ok: bool, reason: str = "") -> pcc.CliContractCheck:
    contract = pcc.get_contract("codex")
    return pcc.CliContractCheck(
        provider="codex",
        contract_id=contract.contract_id,
        ok=ok,
        reason=reason,
        detail="probe detail",
        observed_version=contract.pinned_version if ok else "",
        version_matches=ok,
    )


@pytest.mark.parametrize(
    ("first", "then", "expect_ready"),
    [
        # An in-place upgrade is caught once the cached capability expires.
        (_codex_check(True), _codex_check(False, pcc.REASON_UNVERIFIED_CLI_VERSION), False),
        # One slow probe does not disable Codex until the worker restarts.
        (_codex_check(False, pcc.REASON_CLI_PROBE_FAILED), _codex_check(True), True),
    ],
)
@pytest.mark.asyncio
async def test_codex_capabilities_re_verify_the_cli_like_claude_and_gemini(monkeypatch, first, then, expect_ready):
    """Review AG-02 r1: the Codex capability cache expires; it was kept for the worker's life."""
    from koda.services import codex_runner

    verify = AsyncMock(side_effect=[first, then])
    codex_runner.clear_codex_capability_cache()
    try:
        with (
            patch.object(pcc, "verify_provider_cli", verify),
            patch.object(
                codex_runner, "_read_login_status", AsyncMock(return_value=(0, "Logged in using ChatGPT", ""))
            ),
        ):
            initial = await codex_runner.get_codex_capabilities("new_turn")
            cached = await codex_runner.get_codex_capabilities("new_turn")
            assert verify.await_count == 1  # inside the TTL the capability is reused
            monkeypatch.setattr(codex_runner, "_CAPABILITY_CACHE_TTL_SECONDS", 0.0, raising=False)
            refreshed = await codex_runner.get_codex_capabilities("new_turn")
    finally:
        codex_runner.clear_codex_capability_cache()

    assert initial.can_execute is cached.can_execute is first.ok
    assert verify.await_count == 2
    assert refreshed.can_execute is expect_ready
    assert refreshed.status == ("ready" if expect_ready else "unavailable")
    if not expect_ready:
        assert refreshed.errors[0].startswith(pcc.REASON_UNVERIFIED_CLI_VERSION)


def test_codex_capability_cache_uses_the_same_ttl_as_claude_and_gemini():
    from koda.services import claude_runner, codex_runner, gemini_runner

    assert codex_runner._CAPABILITY_CACHE_TTL_SECONDS == claude_runner._CAPABILITY_CACHE_TTL_SECONDS
    assert codex_runner._CAPABILITY_CACHE_TTL_SECONDS == gemini_runner._CAPABILITY_CACHE_TTL_SECONDS


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


@pytest.mark.asyncio
async def test_main_probes_with_the_runners_command_and_allowlisted_env(fake_bin, monkeypatch):
    """Review AG-02 r1: the CI and image check spawns the CLIs the way the runners do."""
    from koda.services import claude_runner, codex_runner, gemini_runner

    monkeypatch.setenv("PATH", fake_bin("claude", "codex", "gemini")["PATH"])
    secrets = {
        "POSTGRES_URL": "postgresql://koda:dsn-secret@db/koda",
        "KNOWLEDGE_V2_S3_SECRET_ACCESS_KEY": "s3-secret",
        "AGENT_TOKEN": "runtime-token-secret",
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)
    calls: list[tuple[str, tuple[str, ...], dict[str, str]]] = []

    async def record(provider: str, command: Sequence[str], *, env: Any = None) -> pcc.CliContractCheck:
        calls.append((provider, tuple(command), dict(env)))
        contract = pcc.get_contract(provider)
        return pcc.CliContractCheck(
            provider=provider, contract_id=contract.contract_id, ok=False, reason=pcc.REASON_CLI_PROBE_FAILED
        )

    codex_runner.clear_codex_capability_cache()
    try:
        with patch.object(pcc, "verify_provider_cli", record):
            await claude_runner._verify_claude_cli_contract()
            await codex_runner.get_codex_capabilities("new_turn")
            await gemini_runner._verify_gemini_cli_contract()
            runner_calls = {provider: (command, env) for provider, command, env in calls}
            calls.clear()
            assert await asyncio.to_thread(pcc.main, []) == 1
    finally:
        codex_runner.clear_codex_capability_cache()

    main_calls = {provider: (command, env) for provider, command, env in calls}
    assert set(runner_calls) == set(main_calls) == set(PROVIDERS)
    assert main_calls == runner_calls
    for provider, (_, env) in main_calls.items():
        leaked = {key for key, value in env.items() if value in secrets.values()}
        assert not leaked, (provider, leaked)
        assert env["PATH"] == os.environ["PATH"]


# --- The real spawn path, unpatched ---------------------------------------------------------


@contextlib.contextmanager
def _stdin_is_a_pipe() -> Iterator[None]:
    """Make fd 0 a pipe so a child that inherited stdin (instead of /dev/null) can tell."""
    saved = os.dup(0)
    read_end, write_end = os.pipe()
    os.dup2(read_end, 0)
    try:
        yield
    finally:
        os.dup2(saved, 0)
        for fd in (saved, read_end, write_end):
            os.close(fd)


def _process_alive(pid: int) -> bool:
    """Whether ``pid`` still runs; an unreaped zombie (no init reaping in a container) does not."""
    if Path("/proc/self/stat").exists():
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            return False
        return state not in {"Z", "X"}
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.real_cli_contract_probe
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executables")
@pytest.mark.asyncio
async def test_real_probe_runs_the_cli_detached_with_no_stdin(tmp_path):
    """Review AG-02 r1: exercise _run_probe_command itself with a fake gemini executable."""
    contract = pcc.get_contract("gemini")
    help_file = tmp_path / "help.txt"
    help_file.write_text(_conforming_help(contract, "root"))
    binary = tmp_path / "bin" / "gemini"
    binary.parent.mkdir()
    binary.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "devnull, stdin = os.stat(os.devnull), os.fstat(0)\n"
        "if (stdin.st_dev, stdin.st_ino) != (devnull.st_dev, devnull.st_ino):\n"
        "    print('stdin is not /dev/null'); sys.exit(3)\n"
        "if os.getsid(0) != os.getpid():\n"
        "    print('not detached into its own session'); sys.exit(3)\n"
        "if sys.argv[1:] == ['--version']:\n"
        f"    print({contract.pinned_version!r})\n"
        "elif sys.argv[1:] == ['--help']:\n"
        f"    sys.stdout.write(open({str(help_file)!r}).read())\n"
        "else:\n"
        "    sys.exit(2)\n"
    )
    binary.chmod(0o755)

    with _stdin_is_a_pipe():
        check = await pcc.verify_provider_cli("gemini", ("gemini",), env={"PATH": str(binary.parent)})

    assert check.ok, check.error
    assert check.observed_version == contract.pinned_version


@pytest.mark.real_cli_contract_probe
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executables")
@pytest.mark.asyncio
async def test_real_probe_timeout_kills_the_cli_process_tree(tmp_path, monkeypatch):
    sleep = shutil.which("sleep")
    assert sleep is not None
    pid_file = tmp_path / "child.pid"
    binary = tmp_path / "bin" / "gemini"
    binary.parent.mkdir()
    binary.write_text(f'#!/bin/sh\n"{sleep}" 30 &\necho $! > "{pid_file}"\nwait\n')
    binary.chmod(0o755)
    monkeypatch.setattr(pcc, "PROBE_TIMEOUT_SECONDS", 1.0)

    started = time.monotonic()
    try:
        check = await pcc.verify_provider_cli("gemini", ("gemini",), env={"PATH": str(binary.parent)})
        elapsed = time.monotonic() - started
        child = int(pid_file.read_text().strip())
        deadline = time.monotonic() + 5.0
        while _process_alive(child) and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        child_alive = _process_alive(child)
    finally:
        if pid_file.exists():
            with contextlib.suppress(ProcessLookupError, ValueError):
                os.kill(int(pid_file.read_text().strip()), 9)

    assert check.ok is False
    assert check.reason == pcc.REASON_CLI_PROBE_FAILED
    assert "did not answer within 1.0s" in check.detail
    assert elapsed < 10.0
    assert child_alive is False
    assert pcc._VERIFIED == {}
