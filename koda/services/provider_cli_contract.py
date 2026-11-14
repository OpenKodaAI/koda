"""Pinned provider CLI contract: exact versions, argv vocabulary and fail-closed probes.

ADR-002 §2.3 / AG-02. This module is the one table the CLI runners build argv from:

* ``pinned_version`` is the exact version installed into both images from
  ``packages/provider-clis/package-lock.json``.
* ``flags`` and ``config_keys`` are every token a runner may emit. ``validate_args`` refuses
  anything else, so a builder cannot emit a token that is not in the contract.
* ``verify_provider_cli`` probes the installed binary (one executable path, never a command
  line such as ``npx -y <package>``) for exactly those tokens: each flag must have its own
  option entry in ``--help`` and each choice must appear inside that entry. A different
  version, a missing token or a hidden option the parser rejects makes the provider
  unavailable (``unavailable:unverified_cli_version``). It never widens.
* ``levels`` records, per provider built-in tool level, the argv tokens, whether the level
  is self-confined, and the native-resume override. The compilers of AG-23..25 consume it.

Evidence (2026-11-14):

* Claude Code 2.1.325: every visible flag was checked against the real ``claude --help``
  output (``tests/fixtures/provider_cli``). ``--max-turns`` and
  ``--append-system-prompt-file`` are hidden from ``--help``; they are marked unverified and
  checked at runtime by a parser probe that never reaches the model.
* Codex 0.169.0 and Gemini CLI 0.68.0 could not be run in the authoring environment. Every
  token is marked unverified and is checked against the real ``--help`` at runtime; a
  mismatch fails closed. (Reading the published packages found each token in the Codex
  binary's strings and the Gemini bundle's option table; that is not proof.) The ``-c`` flag
  is probed, but Codex config keys and Gemini settings keys cannot be seen in ``--help`` at
  all: ``validate_args`` allows only the keys listed here (the ones that keep MCP servers, web
  search and the secret env passthrough off only at the value §2.3 fixes), and they stay
  unverified until the live provider checks (AG-24, AG-25).

Nothing here is proven self-confined or resume-safe yet: those values stay conservative
until the live checks of AG-23..25 record the evidence.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

ProviderCliId = Literal["claude", "codex", "gemini"]
BuiltinToolLevel = Literal["none", "read_only", "workspace_write", "workspace_exec"]
BUILTIN_TOOL_LEVELS: tuple[BuiltinToolLevel, ...] = ("none", "read_only", "workspace_write", "workspace_exec")
Arity = Literal[0, 1, "+"]

REASON_UNVERIFIED_CLI_VERSION = "unavailable:unverified_cli_version"
REASON_CLI_NOT_INSTALLED = "unavailable:cli_not_installed"
REASON_CLI_PROBE_FAILED = "unavailable:cli_probe_failed"

PROBE_TIMEOUT_SECONDS = 15.0
PARSER_PROBE_CONTROL_FLAG = "--koda-cli-contract-unknown-option"
_VERSION_PATTERN = re.compile(r"(?<![\w.-])v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)(?![\w.])")


class ProviderCliContractError(ValueError):
    """A command line would leave the pinned provider CLI contract."""


@dataclass(frozen=True, slots=True)
class FlagSpec:
    """One option a runner may pass, and how the probe proves the pinned CLI accepts it."""

    token: str
    scopes: tuple[str, ...]
    arity: Arity
    choices: tuple[str, ...] = ()
    # True only when the token was seen in the real ``--help`` output of the pinned version.
    verified: bool = False
    # Accepted by the parser but missing from ``--help``: checked with the parser probe.
    hidden: bool = False
    probe_value: str = ""
    # Still emitted by today's argv; removed by the AG-23..25 compilers. Never used by a level.
    legacy: bool = False
    legacy_choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConfigKeySpec:
    """One ``-c key=value`` override. ``--help`` cannot show these, so none is verified yet."""

    key: str
    scopes: tuple[str, ...]
    choices: tuple[str, ...] = ()
    # The only value the key may take (ADR-002 §2.3 fixes it), written as in ``base_args``.
    # Compared as a parsed literal, so ``{ }`` equals ``{}`` but ``"false"`` is not ``false``.
    value: str | None = None
    legacy: bool = False


@dataclass(frozen=True, slots=True)
class ScopeSpec:
    """A subcommand whose ``--help`` is probed and whose argv is validated on its own."""

    subcommand: tuple[str, ...]
    max_positionals: int


@dataclass(frozen=True, slots=True)
class ParserProbeSpec:
    """How to make the CLI parse options and stop before any model call."""

    args: tuple[str, ...]
    unknown_option_message: str


@dataclass(frozen=True, slots=True)
class LevelContract:
    """What one built-in tool level compiles to on the pinned CLI (ADR-002 §2.3)."""

    args: tuple[str, ...]
    # Class S only after live evidence (AG-23..25); ``workspace_exec`` never is.
    self_confined: bool = False
    # Extra tokens for a native resume; ``None`` means resume is not proven and the turn is replayed.
    resume_args: tuple[str, ...] | None = None
    settings: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class ProviderCliContract:
    provider: ProviderCliId
    package: str
    pinned_version: str
    verified_against_help: bool
    scopes: Mapping[str, ScopeSpec]
    flags: tuple[FlagSpec, ...]
    base_args: tuple[str, ...]
    levels: Mapping[BuiltinToolLevel, LevelContract | None]
    config_flag: str | None = None
    config_keys: tuple[ConfigKeySpec, ...] = ()
    parser_probe: ParserProbeSpec | None = None
    inner_sandbox_ok: bool = False
    # The CLI's parser (yargs, for Gemini) reads a separate value element that starts with "-"
    # as an option of its own, so every value must be attached as one ``--flag=value`` element.
    attached_values: bool = False

    @property
    def contract_id(self) -> str:
        return f"{self.provider}@{self.pinned_version}"

    @property
    def floor(self) -> BuiltinToolLevel:
        """Lowest level the pinned CLI can enforce; a lower effective level refuses the provider."""
        for level in BUILTIN_TOOL_LEVELS:
            if self.levels.get(level) is not None:
                return level
        raise ProviderCliContractError(f"{self.contract_id} supports no built-in tool level")

    def flag(self, token: str) -> FlagSpec | None:
        return next((spec for spec in self.flags if spec.token == token), None)


def _levels(**levels: LevelContract | None) -> Mapping[BuiltinToolLevel, LevelContract | None]:
    return MappingProxyType({level: levels[level] for level in BUILTIN_TOOL_LEVELS})


def _settings(value: dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(value)


_ROOT = ("root",)
_CLAUDE_READ = "Read,Grep,Glob"
_CLAUDE_WRITE = f"{_CLAUDE_READ},Edit,Write"
_CLAUDE_EXEC = f"{_CLAUDE_WRITE},Bash"
_CODEX_SCOPES = ("exec", "exec_resume")
_CODEX_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")
_CODEX_ENV_EXCLUDE = '["*_API_KEY","*TOKEN*","*SECRET*","POSTGRES*","KNOWLEDGE_V2_S3*"]'
_GEMINI_ALWAYS_EXCLUDED = ("web_fetch", "google_web_search", "save_memory")

CLAUDE_CONTRACT = ProviderCliContract(
    provider="claude",
    package="@anthropic-ai/claude-code",
    pinned_version="2.1.325",
    verified_against_help=True,
    scopes=MappingProxyType({"root": ScopeSpec(subcommand=(), max_positionals=0)}),
    flags=(
        FlagSpec("-p", _ROOT, 0, verified=True),
        FlagSpec("--verbose", _ROOT, 0, verified=True),
        FlagSpec("--output-format", _ROOT, 1, choices=("json", "stream-json"), verified=True),
        FlagSpec("--model", _ROOT, 1, verified=True),
        FlagSpec("--max-turns", _ROOT, 1, hidden=True, probe_value="1"),
        FlagSpec("--max-budget-usd", _ROOT, 1, verified=True),
        FlagSpec("--resume", _ROOT, 1, verified=True),
        FlagSpec("--effort", _ROOT, 1, choices=("low", "medium", "high", "xhigh", "max"), verified=True),
        FlagSpec(
            "--permission-mode",
            _ROOT,
            1,
            choices=("bypassPermissions", "plan", "dontAsk"),
            verified=True,
            legacy_choices=("bypassPermissions", "plan"),
        ),
        FlagSpec("--append-system-prompt", _ROOT, 1, verified=True, legacy=True),
        FlagSpec("--append-system-prompt-file", _ROOT, 1, hidden=True, probe_value=os.devnull),
        FlagSpec("--add-dir", _ROOT, 1, verified=True),
        FlagSpec("--restricted", _ROOT, 0, verified=True),
        FlagSpec("--strict-mcp-config", _ROOT, 0, verified=True),
        FlagSpec("--disable-slash-commands", _ROOT, 0, verified=True),
        FlagSpec("--permission-prompts", _ROOT, 1, choices=("none",), verified=True),
        FlagSpec("--tools", _ROOT, 1, verified=True),
        FlagSpec("--allowedTools", _ROOT, 1, verified=True),
    ),
    # Never: bypassPermissions or plan at a level, --dangerously-skip-permissions,
    # --mcp-config, --setting-sources, --bare (it reads only ANTHROPIC_API_KEY).
    base_args=(
        "--restricted",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--permission-prompts",
        "none",
        "--permission-mode",
        "dontAsk",
    ),
    levels=_levels(
        none=LevelContract(args=("--tools", ""), resume_args=()),
        read_only=LevelContract(args=("--tools", _CLAUDE_READ, "--allowedTools", _CLAUDE_READ), resume_args=()),
        workspace_write=LevelContract(args=("--tools", _CLAUDE_WRITE, "--allowedTools", _CLAUDE_WRITE), resume_args=()),
        workspace_exec=LevelContract(args=("--tools", _CLAUDE_EXEC, "--allowedTools", _CLAUDE_EXEC), resume_args=()),
    ),
    parser_probe=ParserProbeSpec(args=("-p",), unknown_option_message="unknown option '{flag}'"),
)

CODEX_CONTRACT = ProviderCliContract(
    provider="codex",
    package="@openai/codex",
    pinned_version="0.169.0",
    verified_against_help=False,
    scopes=MappingProxyType(
        {
            "exec": ScopeSpec(subcommand=("exec",), max_positionals=1),
            "exec_resume": ScopeSpec(subcommand=("exec", "resume"), max_positionals=2),
        }
    ),
    flags=(
        FlagSpec("--json", _CODEX_SCOPES, 0),
        FlagSpec("--cd", ("exec",), 1),
        FlagSpec("--model", _CODEX_SCOPES, 1),
        FlagSpec("--sandbox", ("exec",), 1, choices=("read-only", "workspace-write", "danger-full-access")),
        FlagSpec("--skip-git-repo-check", _CODEX_SCOPES, 0),
        FlagSpec("--dangerously-bypass-approvals-and-sandbox", ("exec_resume",), 0),
        FlagSpec("-c", _CODEX_SCOPES, 1),
        FlagSpec("--image", _CODEX_SCOPES, "+"),
    ),
    config_flag="-c",
    config_keys=(
        ConfigKeySpec("approval_policy", _CODEX_SCOPES, choices=("untrusted", "on-failure", "on-request", "never")),
        ConfigKeySpec("developer_instructions", _CODEX_SCOPES, legacy=True),
        ConfigKeySpec("model_reasoning_effort", _CODEX_SCOPES, choices=_CODEX_EFFORTS),
        ConfigKeySpec("shell_environment_policy.inherit", _CODEX_SCOPES, choices=("core",)),
        # These keep MCP servers, web search and the secret env passthrough off; no builder
        # may emit another value for them.
        ConfigKeySpec("shell_environment_policy.exclude", _CODEX_SCOPES, value=_CODEX_ENV_EXCLUDE),
        ConfigKeySpec("mcp_servers", _CODEX_SCOPES, value="{}"),
        ConfigKeySpec("tools.web_search", _CODEX_SCOPES, value="false"),
    ),
    base_args=(
        "-c",
        'approval_policy="never"',
        "-c",
        'shell_environment_policy.inherit="core"',
        "-c",
        f"shell_environment_policy.exclude={_CODEX_ENV_EXCLUDE}",
        "-c",
        "mcp_servers={}",
        "-c",
        "tools.web_search=false",
    ),
    # inner_sandbox_ok is unproven, so the ADR's "inner sandbox unavailable" column applies:
    # Koda's helper maps the workspace read-only at read_only, and workspace_write is not faithful.
    # ``none`` stays unsupported until a key that removes the shell tool is proven.
    levels=_levels(
        none=None,
        read_only=LevelContract(args=("--sandbox", "danger-full-access")),
        workspace_write=None,
        workspace_exec=LevelContract(args=("--sandbox", "danger-full-access")),
    ),
    inner_sandbox_ok=False,
)

GEMINI_CONTRACT = ProviderCliContract(
    provider="gemini",
    package="@google/gemini-cli",
    pinned_version="0.68.0",
    verified_against_help=False,
    scopes=MappingProxyType({"root": ScopeSpec(subcommand=(), max_positionals=0)}),
    flags=(
        FlagSpec("--model", _ROOT, 1),
        FlagSpec("--output-format", _ROOT, 1, choices=("text", "json", "stream-json")),
        FlagSpec(
            "--approval-mode",
            _ROOT,
            1,
            choices=("default", "auto_edit", "yolo", "plan"),
            legacy_choices=("plan",),
        ),
        FlagSpec("--include-directories", _ROOT, 1, legacy=True),
        FlagSpec("--prompt", _ROOT, 1, legacy=True),
        FlagSpec("--extensions", _ROOT, 1),
    ),
    base_args=("--extensions=none",),
    # Settings go to GEMINI_CLI_SYSTEM_SETTINGS_PATH; their keys are unverified until AG-25.
    # ``none`` (tools.core=[]) is unproven, so the floor is read_only.
    levels=_levels(
        none=None,
        read_only=LevelContract(
            args=("--approval-mode=default",),
            settings=_settings(
                {
                    "mcpServers": {},
                    "tools": {
                        "exclude": ["write_file", "replace", "run_shell_command", *_GEMINI_ALWAYS_EXCLUDED],
                    },
                }
            ),
        ),
        workspace_write=LevelContract(
            args=("--approval-mode=auto_edit",),
            settings=_settings(
                {"mcpServers": {}, "tools": {"exclude": ["run_shell_command", *_GEMINI_ALWAYS_EXCLUDED]}}
            ),
        ),
        workspace_exec=LevelContract(
            args=("--approval-mode=yolo",),
            settings=_settings({"mcpServers": {}, "tools": {"exclude": list(_GEMINI_ALWAYS_EXCLUDED)}}),
        ),
    ),
    attached_values=True,
)

CONTRACTS: dict[str, ProviderCliContract] = {
    "claude": CLAUDE_CONTRACT,
    "codex": CODEX_CONTRACT,
    "gemini": GEMINI_CONTRACT,
}


def get_contract(provider: str) -> ProviderCliContract:
    try:
        return CONTRACTS[provider.strip().lower()]
    except KeyError:
        raise ProviderCliContractError(f"no CLI contract for provider {provider!r}") from None


def pinned_versions() -> dict[str, str]:
    return {provider: contract.pinned_version for provider, contract in CONTRACTS.items()}


# --- Argv validation ------------------------------------------------------------------------


def _scope_for(contract: ProviderCliContract, args: Sequence[str]) -> tuple[str, ScopeSpec]:
    for name, scope in sorted(contract.scopes.items(), key=lambda item: -len(item[1].subcommand)):
        if tuple(args[: len(scope.subcommand)]) == scope.subcommand:
            return name, scope
    raise ProviderCliContractError(f"{contract.contract_id}: argv does not start with a contract subcommand")


def _config_literal(raw_value: str) -> str:
    """Canonical form of a ``-c`` value: the parsed JSON/TOML literal, else the raw string."""
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _check_config_override(contract: ProviderCliContract, scope: str, override: str) -> None:
    key, sep, raw_value = override.partition("=")
    if not sep or not key:
        raise ProviderCliContractError(f"{contract.contract_id}: {contract.config_flag} needs key=value")
    spec = next((item for item in contract.config_keys if item.key == key and scope in item.scopes), None)
    if spec is None:
        raise ProviderCliContractError(f"{contract.contract_id}: config key {key!r} is not in the contract")
    if spec.value is not None and _config_literal(raw_value) != _config_literal(spec.value):
        raise ProviderCliContractError(f"{contract.contract_id}: {key} must be {spec.value}, not {raw_value}")
    if spec.choices:
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = raw_value
        if value not in spec.choices:
            raise ProviderCliContractError(f"{contract.contract_id}: {key}={raw_value} is not in the contract")


def validate_args(provider: str, args: Sequence[str]) -> None:
    """Refuse a command line (without the executable) that leaves the provider's contract.

    Every option must be a contract flag of the subcommand's scope, enumerated values must be
    contract choices and config overrides contract keys. For contracts whose parser treats the
    next element as the value (commander, clap), that element is data, so a prompt starting with
    ``--`` is not a flag. For ``attached_values`` contracts (yargs), a separate value element is
    refused and values must be attached as ``--flag=value``, which the parser binds verbatim.
    """
    contract = get_contract(provider)
    scope_name, scope = _scope_for(contract, args)
    positionals: list[str] = []
    index = len(scope.subcommand)
    while index < len(args):
        token = args[index]
        index += 1
        if token == "-" or not token.startswith("-"):
            positionals.append(token)
            continue
        attached: str | None = None
        if contract.attached_values and token.startswith("--") and "=" in token:
            token, _, attached = token.partition("=")
        spec = contract.flag(token)
        if spec is None or scope_name not in spec.scopes:
            raise ProviderCliContractError(f"{contract.contract_id}: {token} is not in the contract for {scope_name}")
        if spec.arity == 0:
            if attached is not None:
                raise ProviderCliContractError(f"{contract.contract_id}: {token} takes no value")
            continue
        if contract.attached_values:
            if attached is None or spec.arity == "+":
                raise ProviderCliContractError(
                    f"{contract.contract_id}: {token} needs its value attached as {token}=VALUE"
                )
            if spec.choices and attached not in spec.choices:
                raise ProviderCliContractError(f"{contract.contract_id}: {token} {attached} is not in the contract")
            continue
        if spec.arity == "+":
            start = index
            while index < len(args) and not args[index].startswith("-"):
                index += 1
            if index == start:
                raise ProviderCliContractError(f"{contract.contract_id}: {token} needs at least one value")
            continue
        if index >= len(args):
            raise ProviderCliContractError(f"{contract.contract_id}: {token} needs a value")
        value = args[index]
        index += 1
        if spec.choices and value not in spec.choices:
            raise ProviderCliContractError(f"{contract.contract_id}: {token} {value} is not in the contract")
        if token == contract.config_flag:
            _check_config_override(contract, scope_name, value)
    if len(positionals) > scope.max_positionals:
        raise ProviderCliContractError(
            f"{contract.contract_id}: unexpected positional arguments for {scope_name}: {len(positionals)}"
        )


# --- Runtime probe --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MissingToken:
    scope: str
    token: str


@dataclass(frozen=True, slots=True)
class CliContractCheck:
    """Outcome of probing one installed CLI against its contract."""

    provider: str
    contract_id: str
    ok: bool
    reason: str = ""
    detail: str = ""
    observed_version: str = ""
    version_matches: bool = False
    missing: tuple[MissingToken, ...] = ()

    @property
    def error(self) -> str:
        return f"{self.reason}: {self.detail}" if self.reason else ""

    def scope_ok(self, scope: str) -> bool:
        """Whether argv of ``scope`` can run: the version matches and none of its tokens is missing."""
        return self.version_matches and not any(item.scope == scope for item in self.missing)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "contract": self.contract_id,
            "ok": self.ok,
            "reason": self.reason,
            "detail": self.detail,
            "observed_version": self.observed_version,
            "version_matches": self.version_matches,
            "missing": [f"{item.scope}:{item.token}" for item in self.missing],
        }


def not_installed_check(provider: str, executable: str) -> CliContractCheck:
    contract = get_contract(provider)
    return CliContractCheck(
        provider=contract.provider,
        contract_id=contract.contract_id,
        ok=False,
        reason=REASON_CLI_NOT_INSTALLED,
        detail=(
            f"{executable} not found on PATH. Install {contract.package}@{contract.pinned_version} "
            "(the version pinned in packages/provider-clis)."
        ),
    )


def help_lists_token(help_text: str, token: str) -> bool:
    """Whether ``token`` appears in help output as a whole word (``-c`` does not match ``--cd``)."""
    return re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", help_text) is not None


# An option line of ``--help``: indented a little, starting with ``-``; its names end at the
# first run of two spaces (commander, yargs and clap all lay options out this way). Description
# lines are indented further, so ``--plugin-dir A`` inside a description never starts an entry.
_HELP_OPTION_LINE = re.compile(r"^(?P<indent> {0,8})(?P<names>-\S.*?)(?= {2,}|$)")


def help_option_entries(help_text: str, token: str) -> list[str]:
    """The ``--help`` entries that document option ``token``: from the option line that names
    it up to the next option line or the next line that is not indented under it.

    A choice counts only when it appears inside its own flag's entry, and a flag only when an
    option line names it: a word elsewhere in the help (``~/.claude.json``, another option's
    description) proves nothing.
    """
    lines = help_text.expandtabs().splitlines()
    entries: list[str] = []
    index = 0
    while index < len(lines):
        match = _HELP_OPTION_LINE.match(lines[index])
        index += 1
        if match is None or not help_lists_token(match.group("names"), token):
            continue
        indent = len(match.group("indent"))
        entry = [lines[index - 1]]
        while index < len(lines):
            line = lines[index]
            if line.strip() and (_HELP_OPTION_LINE.match(line) or len(line) - len(line.lstrip()) <= indent):
                break
            entry.append(line)
            index += 1
        entries.append("\n".join(entry))
    return entries


def parser_probe_args(contract: ProviderCliContract) -> tuple[str, ...]:
    """Arguments of the parser probe: the hidden flags, then an option that cannot exist."""
    if contract.parser_probe is None:
        return ()
    args: list[str] = list(contract.parser_probe.args)
    for spec in contract.flags:
        if spec.hidden:
            args.append(spec.token)
            if spec.arity != 0:
                args.append(spec.probe_value)
    args.append(PARSER_PROBE_CONTROL_FLAG)
    return tuple(args)


async def _run_probe_command(
    argv: Sequence[str], env: Mapping[str, str] | None, timeout: float
) -> tuple[int, str, str]:
    """Run one probe with no stdin; return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=dict(env) if env is not None else None,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        from koda.utils.process_control import terminate_process_tree

        await terminate_process_tree(proc)
        await proc.wait()
        raise
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


_VERIFIED: dict[tuple[Any, ...], CliContractCheck] = {}


def clear_cli_contract_cache() -> None:
    _VERIFIED.clear()


def _fingerprint(contract: ProviderCliContract, command: Sequence[str], executable: str) -> tuple[Any, ...]:
    """Identify the installed binary so a replaced or upgraded CLI is probed again."""
    real = os.path.realpath(executable)
    stat = os.stat(real)
    return (contract.contract_id, tuple(command), real, stat.st_mtime_ns, stat.st_size)


def _fail(contract: ProviderCliContract, reason: str, detail: str, **extra: Any) -> CliContractCheck:
    return CliContractCheck(
        provider=contract.provider, contract_id=contract.contract_id, ok=False, reason=reason, detail=detail, **extra
    )


async def verify_provider_cli(
    provider: str,
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
) -> CliContractCheck:
    """Probe the installed CLI (``command`` is how the runner invokes it) against its contract.

    Runs ``--version``, each scope's ``--help`` and, for hidden options, a parser probe that
    stops before any model call. Only a fully verified result is cached, keyed by the binary.

    ``command`` must be one executable path. A command line such as ``npx -y <package>`` is
    refused: its extra tokens are argv outside the contract, and the binary fingerprint would
    keep vouching for whatever package version the runner resolves later.
    """
    contract = get_contract(provider)
    if not command:
        return not_installed_check(contract.provider, contract.provider)
    if len(command) != 1:
        return _fail(
            contract,
            REASON_UNVERIFIED_CLI_VERSION,
            f"Koda runs {contract.package} as one executable path, not the command line "
            f"{' '.join(command)!r}. Point it at the pinned binary (packages/provider-clis).",
        )
    search_path = (env if env is not None else os.environ).get("PATH")
    executable = shutil.which(command[0], path=search_path)
    if executable is None:
        return not_installed_check(contract.provider, command[0])
    try:
        fingerprint = _fingerprint(contract, command, executable)
        cached = _VERIFIED.get(fingerprint)
        if cached is not None:
            return cached
        check = await _probe(contract, command, env)
    except TimeoutError:
        return _fail(contract, REASON_CLI_PROBE_FAILED, f"{command[0]} did not answer within {PROBE_TIMEOUT_SECONDS}s")
    except Exception as exc:  # fail closed: whatever went wrong, nothing was verified
        return _fail(contract, REASON_CLI_PROBE_FAILED, f"could not probe {command[0]}: {exc}")
    if check.ok:
        _VERIFIED[fingerprint] = check
    return check


async def _probe(
    contract: ProviderCliContract, command: Sequence[str], env: Mapping[str, str] | None
) -> CliContractCheck:
    _, stdout, stderr = await _run_probe_command([*command, "--version"], env, PROBE_TIMEOUT_SECONDS)
    match = _VERSION_PATTERN.search(stdout) or _VERSION_PATTERN.search(stderr)
    observed = match.group(1) if match else ""
    if observed != contract.pinned_version:
        seen = f"reports {observed}" if observed else "reports no version"
        return _fail(
            contract,
            REASON_UNVERIFIED_CLI_VERSION,
            f"{command[0]} {seen}; Koda's contract is pinned to {contract.package}@{contract.pinned_version}. "
            "Install the pinned version (packages/provider-clis) or rebuild the image.",
            observed_version=observed,
        )

    missing: list[MissingToken] = []
    for scope_name, scope in contract.scopes.items():
        _, stdout, stderr = await _run_probe_command(
            [*command, *scope.subcommand, "--help"], env, PROBE_TIMEOUT_SECONDS
        )
        help_text = f"{stdout}\n{stderr}"
        for spec in contract.flags:
            if scope_name not in spec.scopes or spec.hidden:
                continue
            entries = help_option_entries(help_text, spec.token)
            if not entries:
                missing.append(MissingToken(scope_name, spec.token))
                continue
            missing.extend(
                MissingToken(scope_name, f"{spec.token}={choice}")
                for choice in spec.choices
                if not any(help_lists_token(entry, choice) for entry in entries)
            )

    hidden = [spec for spec in contract.flags if spec.hidden]
    if hidden:
        missing.extend(await _probe_hidden_flags(contract, command, env, hidden))

    if missing:
        listed = ", ".join(f"{item.token} ({item.scope})" for item in missing)
        return _fail(
            contract,
            REASON_UNVERIFIED_CLI_VERSION,
            f"{command[0]} {observed} does not accept contract tokens: {listed}",
            observed_version=observed,
            version_matches=True,
            missing=tuple(missing),
        )
    return CliContractCheck(
        provider=contract.provider,
        contract_id=contract.contract_id,
        ok=True,
        observed_version=observed,
        version_matches=True,
    )


async def _probe_hidden_flags(
    contract: ProviderCliContract,
    command: Sequence[str],
    env: Mapping[str, str] | None,
    hidden: Sequence[FlagSpec],
) -> list[MissingToken]:
    """Prove the parser accepts hidden flags: the only unknown option it reports is the control."""
    probe = contract.parser_probe
    rejected: Sequence[FlagSpec] = hidden
    if probe is not None:
        _, stdout, stderr = await _run_probe_command(
            [*command, *parser_probe_args(contract)], env, PROBE_TIMEOUT_SECONDS
        )
        output = f"{stdout}\n{stderr}"
        # A parser that does not reject an option that cannot exist proves nothing.
        if probe.unknown_option_message.format(flag=PARSER_PROBE_CONTROL_FLAG) in output:
            rejected = [spec for spec in hidden if probe.unknown_option_message.format(flag=spec.token) in output]
    return [MissingToken(scope, spec.token) for spec in rejected for scope in spec.scopes]


# --- Command-line check (CI contract job and the images) ------------------------------------


def _runner_command(provider: str) -> tuple[str, ...]:
    """The command each runner invokes its CLI with (``claude_runner``, ``codex_runner``,
    ``gemini_runner``), so this check probes the same binary the runners would run."""
    if provider == "codex":
        from koda.config import CODEX_BIN

        return (CODEX_BIN,)
    if provider == "gemini":
        from koda.services.provider_auth import resolve_provider_command

        return resolve_provider_command("gemini")
    return (provider,)


async def _check_as_runner(provider: str) -> CliContractCheck:
    """Probe one CLI with the runner's command and its allowlisted child env, never os.environ."""
    from koda.services.provider_env import build_llm_subprocess_env

    try:
        command = _runner_command(provider)
    except FileNotFoundError as exc:
        return not_installed_check(provider, str(exc) or provider)
    return await verify_provider_cli(provider, command, env=build_llm_subprocess_env(provider=provider))


def main(argv: Sequence[str] | None = None) -> int:
    """Probe the CLIs on PATH against the contract; print a JSON report; exit 1 unless all pass.

    No model is called and no credential is needed: only ``--version``, ``--help`` and the
    parser probe run, each with the same command and allowlisted env as the runner's probe.
    """
    del argv

    async def _run() -> list[CliContractCheck]:
        return [await _check_as_runner(provider) for provider in CONTRACTS]

    checks = asyncio.run(_run())
    print(json.dumps([check.as_dict() for check in checks], indent=2))
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    sys.exit(main(sys.argv[1:]))
