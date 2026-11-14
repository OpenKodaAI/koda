"""Tests for structured git tool handlers."""

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from koda.services import tool_dispatcher
from koda.services.tool_dispatcher import ToolContext, _validate_git_args


@dataclass
class FakeCliResult:
    binary: str = "git"
    args: str = ""
    text: str = ""
    exit_code: int | None = 0
    timed_out: bool = False
    blocked: bool = False
    error: bool = False
    truncated: bool = False


def _make_ctx(work_dir: str = "/tmp", **overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir=work_dir,
        user_data={
            "work_dir": work_dir,
            "model": "claude-sonnet-4-6",
            "session_id": "s",
            "total_cost": 0.0,
            "query_count": 0,
        },
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


class TestGitStatus:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_git_status

        with patch("koda.services.tool_dispatcher.GIT_ENABLED", False):
            result = await _handle_git_status({}, _make_ctx())
        assert not result.success
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_git_status

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="On branch main\nnothing to commit")
            result = await _handle_git_status({}, _make_ctx())
        assert result.success
        assert "main" in result.output


class TestGitDiff:
    @pytest.mark.asyncio
    async def test_staged(self):
        from koda.services.tool_dispatcher import _handle_git_diff

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="diff --cached output")
            result = await _handle_git_diff({"staged": True}, _make_ctx())
        assert result.success
        # Verify --cached was passed in the args string
        call_args = mock_run.call_args
        assert "--cached" in call_args[0][1]


class TestGitLog:
    @pytest.mark.asyncio
    async def test_default(self):
        from koda.services.tool_dispatcher import _handle_git_log

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="abc1234 Initial commit\ndef5678 Add feature")
            result = await _handle_git_log({}, _make_ctx())
        assert result.success


class TestGitCommit:
    @pytest.mark.asyncio
    async def test_missing_message(self):
        from koda.services.tool_dispatcher import _handle_git_commit

        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await _handle_git_commit({}, _make_ctx())
        assert not result.success
        assert "message" in result.output.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_git_commit

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="[main abc1234] fix: login bug\n 1 file changed")
            result = await _handle_git_commit({"message": "fix: login bug"}, _make_ctx())
        assert result.success


class TestGitBranch:
    @pytest.mark.asyncio
    async def test_list(self):
        from koda.services.tool_dispatcher import _handle_git_branch

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="* main\n  feature/x")
            result = await _handle_git_branch({}, _make_ctx())
        assert result.success

    @pytest.mark.asyncio
    async def test_create(self):
        from koda.services.tool_dispatcher import _handle_git_branch

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="")
            result = await _handle_git_branch({"name": "feature/new"}, _make_ctx())
        assert result.success


class TestGitCheckout:
    @pytest.mark.asyncio
    async def test_missing_target(self):
        from koda.services.tool_dispatcher import _handle_git_checkout

        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await _handle_git_checkout({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_git_checkout

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="Switched to branch 'main'")
            result = await _handle_git_checkout({"target": "main"}, _make_ctx())
        assert result.success


class TestGitPush:
    @pytest.mark.asyncio
    async def test_default(self):
        from koda.services.tool_dispatcher import _handle_git_push

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="Everything up-to-date")
            result = await _handle_git_push({}, _make_ctx())
        assert result.success


class TestGitPull:
    @pytest.mark.asyncio
    async def test_with_rebase(self):
        from koda.services.tool_dispatcher import _handle_git_pull

        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch(
                "koda.services.cli_runner.run_cli_command_detailed",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="Already up to date.")
            result = await _handle_git_pull({"rebase": True}, _make_ctx())
        assert result.success
        call_args = mock_run.call_args
        assert "--rebase" in call_args[0][1]


class TestGitPrompt:
    def test_git_section_when_enabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.GIT_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "### Git Operations" in prompt
        assert "git_status" not in prompt
        assert "git_commit" not in prompt

    def test_no_git_section_when_disabled(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.GIT_ENABLED", False):
            prompt = build_agent_tools_prompt()
        assert "### Git Operations" not in prompt


# D-026: git option injection. A model-supplied ref, branch, remote, target or
# start point that starts with "-" must never reach git, where it would be parsed
# as an option (``--output=<path>`` writes files, ``--receive-pack=<cmd>`` and
# ``--upload-pack=<cmd>`` run commands).


class TestValidateGitArgs:
    @pytest.mark.parametrize(
        "args",
        [
            ["--output=/tmp/pwned"],
            ["--output", "/tmp/pwned"],
            ["--outp=/tmp/pwned"],  # git accepts unambiguous abbreviations of long options
            ["--output-directory=/tmp/pwned"],
            ["origin", "--receive-pack=touch /tmp/pwned"],
            ["--receive=touch /tmp/pwned"],
            ["--upload-pack=touch /tmp/pwned"],
            ["--upl=touch /tmp/pwned"],
            ["--exec=touch /tmp/pwned"],
            ["--exe=touch /tmp/pwned"],
            # git pull hands its operands to git fetch without the marker.
            ["--end-of-options", "--upload-pack=touch /tmp/pwned"],
        ],
    )
    def test_denies_options_that_write_files_or_run_commands(self, args):
        error = _validate_git_args(args)
        assert error is not None
        assert error.startswith("Blocked: git option")

    @pytest.mark.parametrize(
        "args",
        [
            ["--short"],
            ["--cached", "--stat", "--end-of-options", "HEAD^", "--", "src/"],
            ["-10", "--oneline", "--all", "--graph", "--", "src/"],
            ["-a", "--message=--exec is only text in a commit message"],
            ["--end-of-options", "feature/x", "main"],
            ["-a", "-v"],
            ["-b", "feature/x", "main"],
            ["-u", "--end-of-options", "origin", "main"],
            ["--rebase", "--end-of-options", "origin", "main"],
        ],
    )
    def test_allows_arguments_built_by_the_git_handlers(self, args):
        assert _validate_git_args(args) is None

    def test_still_blocks_shell_metacharacters(self):
        assert _validate_git_args(["HEAD;id"]) == "Blocked: argument contains disallowed characters."


_OPTION_INJECTION_PROBES = [
    ("_handle_git_diff", {"ref": "--output=/tmp/pwned"}, "ref"),
    ("_handle_git_diff", {"ref": "-R"}, "ref"),
    ("_handle_git_branch", {"name": "--delete", "start_point": "main"}, "name"),
    ("_handle_git_branch", {"name": "feature/x", "start_point": "--track"}, "start_point"),
    ("_handle_git_checkout", {"target": "--force"}, "target"),
    ("_handle_git_checkout", {"target": "--orphan=evil", "create": True}, "target"),
    ("_handle_git_checkout", {"target": "feature/x", "create": True, "start_point": "--detach"}, "start_point"),
    ("_handle_git_push", {"remote": "--receive-pack=touch /tmp/pwned"}, "remote"),
    ("_handle_git_push", {"remote": "--force"}, "remote"),
    ("_handle_git_push", {"remote": "origin", "branch": "--exec=touch /tmp/pwned"}, "branch"),
    ("_handle_git_pull", {"remote": "--upload-pack=touch /tmp/pwned"}, "remote"),
    ("_handle_git_pull", {"remote": "origin", "branch": "--upload-pack=touch /tmp/pwned"}, "branch"),
]


class TestGitOptionInjectionProbes:
    @pytest.mark.security
    @pytest.mark.guardrail
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("handler_name", "params", "param"), _OPTION_INJECTION_PROBES)
    async def test_leading_dash_value_is_rejected_before_git_runs(self, handler_name, params, param):
        handler = getattr(tool_dispatcher, handler_name)
        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch("koda.services.cli_runner.run_cli_command_detailed", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="ran")
            result = await handler(params, _make_ctx())
        assert not result.success
        assert result.output == f"Blocked: '{param}' must not start with '-'."
        mock_run.assert_not_called()


class TestGitArgvLayout:
    """Normal calls keep working, with options before ``--end-of-options`` and operands after it."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("handler_name", "params", "argv"),
        [
            ("_handle_git_status", {"short": True}, ["status", "--short"]),
            (
                "_handle_git_diff",
                {"staged": True, "ref": "HEAD^", "path": "src/", "stat": True},
                ["diff", "--cached", "--stat", "--end-of-options", "HEAD^", "--", "src/"],
            ),
            ("_handle_git_diff", {"path": "src/", "stat": True}, ["diff", "--stat", "--", "src/"]),
            (
                "_handle_git_log",
                {"limit": 5, "all": True, "path": "src/"},
                ["log", "-5", "--oneline", "--all", "--", "src/"],
            ),
            ("_handle_git_commit", {"message": "- fix typo", "all": True}, ["commit", "-a", "--message=- fix typo"]),
            (
                "_handle_git_branch",
                {"name": "feature/x", "start_point": "main"},
                ["branch", "--end-of-options", "feature/x", "main"],
            ),
            ("_handle_git_branch", {"all": True}, ["branch", "-a", "-v"]),
            # git checkout treats --end-of-options as a pathspec, so its values are only dash-checked.
            ("_handle_git_checkout", {"target": "main"}, ["checkout", "main"]),
            (
                "_handle_git_checkout",
                {"target": "feature/x", "create": True, "start_point": "main"},
                ["checkout", "-b", "feature/x", "main"],
            ),
            ("_handle_git_push", {}, ["push", "--end-of-options", "origin"]),
            (
                "_handle_git_push",
                {"branch": "main", "set_upstream": True},
                ["push", "-u", "--end-of-options", "origin", "main"],
            ),
            (
                "_handle_git_pull",
                {"remote": "origin", "branch": "main", "rebase": True},
                ["pull", "--rebase", "--end-of-options", "origin", "main"],
            ),
            ("_handle_git_pull", {}, ["pull"]),
        ],
    )
    async def test_argv(self, handler_name, params, argv):
        handler = getattr(tool_dispatcher, handler_name)
        with (
            patch("koda.services.tool_dispatcher.GIT_ENABLED", True),
            patch("koda.services.cli_runner.run_cli_command_detailed", new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = FakeCliResult(text="ok")
            result = await handler(params, _make_ctx())
        assert result.success, result.output
        assert mock_run.call_args[0][0] == "git"
        assert shlex.split(mock_run.call_args[0][1]) == argv


def _git_supports_end_of_options() -> bool:
    if shutil.which("git") is None:
        return False
    version = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False).stdout
    parts = version.split()[-1].split(".") if version else []
    try:
        return (int(parts[0]), int(parts[1])) >= (2, 24)
    except (IndexError, ValueError):
        return False


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repository with two commits, a ``keep`` branch and ``main`` tracking a local bare ``origin``."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(cwd: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)

    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    origin.mkdir()
    repo.mkdir()
    git(origin, "init", "-q", "--bare")
    git(repo, "init", "-q")
    git(repo, "checkout", "-q", "-b", "main")
    git(repo, "config", "user.name", "Koda Test")
    git(repo, "config", "user.email", "koda-test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "first")
    (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    git(repo, "commit", "-q", "-a", "-m", "second")
    git(repo, "branch", "keep")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _branches(repo: Path) -> set[str]:
    out = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(out.split())


@pytest.mark.skipif(not _git_supports_end_of_options(), reason="needs git >= 2.24 for --end-of-options")
class TestGitToolsAgainstRealGit:
    """Run the handlers against a real repository: probes leave no effect, normal calls work."""

    @pytest.mark.security
    @pytest.mark.guardrail
    @pytest.mark.asyncio
    async def test_diff_ref_cannot_write_a_file(self, git_repo: Path):
        canary = git_repo.parent / "pwned-diff.txt"
        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await tool_dispatcher._handle_git_diff(
                {"ref": f"--output={canary}"}, _make_ctx(work_dir=str(git_repo))
            )
        assert not canary.exists()
        assert not result.success

    @pytest.mark.security
    @pytest.mark.guardrail
    @pytest.mark.asyncio
    async def test_push_remote_cannot_run_a_command(self, git_repo: Path):
        canary = git_repo.parent / "pwned-push"
        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await tool_dispatcher._handle_git_push(
                {"remote": f"--receive-pack=touch {canary}"}, _make_ctx(work_dir=str(git_repo))
            )
        assert not canary.exists()
        assert not result.success

    @pytest.mark.security
    @pytest.mark.guardrail
    @pytest.mark.asyncio
    async def test_pull_remote_cannot_run_a_command(self, git_repo: Path):
        canary = git_repo.parent / "pwned-pull"
        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await tool_dispatcher._handle_git_pull(
                {"remote": f"--upload-pack=touch {canary}"}, _make_ctx(work_dir=str(git_repo))
            )
        assert not canary.exists()
        assert not result.success

    @pytest.mark.security
    @pytest.mark.guardrail
    @pytest.mark.asyncio
    async def test_branch_name_cannot_delete_a_branch(self, git_repo: Path):
        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await tool_dispatcher._handle_git_branch(
                {"name": "--delete", "start_point": "keep"}, _make_ctx(work_dir=str(git_repo))
            )
        assert not result.success
        assert "keep" in _branches(git_repo)

    @pytest.mark.security
    @pytest.mark.guardrail
    @pytest.mark.asyncio
    async def test_checkout_target_cannot_discard_local_changes(self, git_repo: Path):
        (git_repo / "a.txt").write_text("uncommitted work\n", encoding="utf-8")
        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            result = await tool_dispatcher._handle_git_checkout(
                {"target": "--force"}, _make_ctx(work_dir=str(git_repo))
            )
        assert not result.success
        assert (git_repo / "a.txt").read_text(encoding="utf-8") == "uncommitted work\n"

    @pytest.mark.asyncio
    async def test_normal_calls_succeed(self, git_repo: Path):
        ctx = _make_ctx(work_dir=str(git_repo))
        with patch("koda.services.tool_dispatcher.GIT_ENABLED", True):
            status = await tool_dispatcher._handle_git_status({"short": True}, ctx)
            diff = await tool_dispatcher._handle_git_diff({"ref": "HEAD^", "path": "a.txt", "stat": True}, ctx)
            log = await tool_dispatcher._handle_git_log({"limit": 1, "path": "a.txt"}, ctx)
            branch = await tool_dispatcher._handle_git_branch({"name": "feature/x", "start_point": "main"}, ctx)
            listed = await tool_dispatcher._handle_git_branch({}, ctx)
            checkout = await tool_dispatcher._handle_git_checkout({"target": "feature/x"}, ctx)
            create = await tool_dispatcher._handle_git_checkout(
                {"target": "feature/y", "create": True, "start_point": "main"}, ctx
            )
            (git_repo / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
            commit = await tool_dispatcher._handle_git_commit(
                {"message": "--exec is only text in a commit message", "all": True}, ctx
            )
            push = await tool_dispatcher._handle_git_push({"branch": "feature/y", "set_upstream": True}, ctx)
            pull = await tool_dispatcher._handle_git_pull(
                {"remote": "origin", "branch": "feature/y", "rebase": True}, ctx
            )

        for result in (status, diff, log, branch, listed, checkout, create, commit, push, pull):
            assert result.success, f"{result.tool}: {result.output}"
        # --stat used to follow "-- <path>", where git read it as a pathspec.
        assert "1 file changed" in diff.output
        assert "second" in log.output
        assert "feature/x" in listed.output
        assert {"feature/x", "feature/y", "keep", "main"} <= _branches(git_repo)
        subject = subprocess.run(
            ["git", "log", "-1", "--format=%s"], cwd=git_repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert subject == "--exec is only text in a commit message"
