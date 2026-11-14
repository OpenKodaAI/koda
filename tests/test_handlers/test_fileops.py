"""Tests for file operation command handlers."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from koda.handlers.fileops import cmd_cat, cmd_edit, cmd_mkdir, cmd_rm, cmd_write
from koda.utils.files import safe_resolve


@pytest.mark.asyncio
async def test_write_no_args(mock_update, mock_context):
    mock_context.args = []
    await cmd_write(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_write_requests_approval_before_creating_file(mock_update, mock_context, tmp_path):
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["test.txt", "hello", "world"]
    await cmd_write(mock_update, mock_context)
    assert not (tmp_path / "test.txt").exists()
    assert "Confirmacao necessaria" in mock_update.message.reply_text.call_args.args[0]
    assert mock_update.message.reply_text.call_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_write_blocked_traversal(mock_update, mock_context, tmp_path):
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["../../etc/passwd", "pwned"]
    await cmd_write(mock_update, mock_context)
    assert "denied" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_write_respects_allowed_paths_grant(mock_update, mock_context, tmp_path):
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["test.txt", "hello"]

    policy = {
        "integration_grants": {
            "fileops": {
                "enabled": True,
                "allowed_paths": [str(tmp_path / "allowed")],
            }
        }
    }

    with patch("koda.utils.approval.AGENT_RESOURCE_ACCESS_POLICY", policy):
        await cmd_write(mock_update, mock_context)

    assert "outside the granted scope" in mock_update.message.reply_text.call_args[0][0].lower()
    assert not (tmp_path / "test.txt").exists()


@pytest.mark.asyncio
async def test_edit_requests_approval_before_appending(mock_update, mock_context, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\n")
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["test.txt", "line2"]
    await cmd_edit(mock_update, mock_context)
    assert "line2\n" not in f.read_text()
    assert "Confirmacao necessaria" in mock_update.message.reply_text.call_args.args[0]
    assert mock_update.message.reply_text.call_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_rm_requests_approval_before_delete(mock_update, mock_context, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("content")
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["test.txt"]
    await cmd_rm(mock_update, mock_context)
    assert f.exists()
    assert "Confirmacao necessaria" in mock_update.message.reply_text.call_args.args[0]
    assert mock_update.message.reply_text.call_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_rm_blocked_traversal(mock_update, mock_context, tmp_path):
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["../../etc/passwd"]
    await cmd_rm(mock_update, mock_context)
    assert "denied" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_mkdir_requests_approval_before_create(mock_update, mock_context, tmp_path):
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["subdir"]
    await cmd_mkdir(mock_update, mock_context)
    assert not (tmp_path / "subdir").exists()
    assert "Confirmacao necessaria" in mock_update.message.reply_text.call_args.args[0]
    assert mock_update.message.reply_text.call_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_cat_reads_file(mock_update, mock_context, tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("file content")
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["test.txt"]
    with patch("koda.handlers.fileops.send_long_message", new_callable=AsyncMock) as mock_send:
        await cmd_cat(mock_update, mock_context)
        call_text = mock_send.call_args[0][1]
        assert "file content" in call_text


@pytest.mark.asyncio
async def test_cat_no_args(mock_update, mock_context):
    mock_context.args = []
    await cmd_cat(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cat_reads_a_path_with_a_quote(mock_update, mock_context, tmp_path):
    """The policy gate reads the path as the handler does, not as a shell would tokenize it."""
    (tmp_path / "it's.txt").write_text("quoted content")
    mock_context.user_data["work_dir"] = str(tmp_path)
    mock_context.args = ["it's.txt"]
    with patch("koda.handlers.fileops.send_long_message", new_callable=AsyncMock) as mock_send:
        await cmd_cat(mock_update, mock_context)
    assert "quoted content" in mock_send.call_args[0][1]


def _tree(root: Path) -> dict[str, str | None]:
    return {
        str(path.relative_to(root)): path.read_text() if path.is_file() else None for path in sorted(root.rglob("*"))
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command", "handler", "args", "acted_on"),
    [
        # /rm, /mkdir and /cat act on the whole argument string, spaces included.
        ("rm", cmd_rm, ["x", "/../secrets/key"], "secrets/key"),
        ("mkdir", cmd_mkdir, ["x", "/../secrets/new"], "secrets/new"),
        ("cat", cmd_cat, ["x", "/../secrets/key"], "secrets/key"),
        # /write and /edit act on their first argument, whatever a shell would make of the quote in it.
        ("write", cmd_write, ['x/../secrets/key"', '/../../elsewhere"', "content"], 'secrets/key"'),
        ("edit", cmd_edit, ['x/../secrets/key"', '/../../elsewhere"', "line"], 'secrets/key"'),
    ],
)
async def test_path_rules_decide_the_path_the_file_command_acts_on(
    command, handler, args, acted_on, mock_update, mock_context, tmp_path, monkeypatch
):
    work_dir = tmp_path.resolve()
    (work_dir / "secrets").mkdir()
    (work_dir / "secrets" / "key").write_text("SECRET")
    (work_dir / "secrets" / 'key"').write_text("SECRET\n")
    handler_path = args[0] if command in {"write", "edit"} else " ".join(args)
    assert safe_resolve(handler_path, str(work_dir)) == work_dir / acted_on
    policy = {
        "version": 1,
        "rules": [
            {"name": f"allow-{command}", "match": {"tool_id": command}, "decision": "allow"},
            {"name": "deny-secrets", "match": {"path": str(work_dir / "secrets")}, "decision": "deny"},
        ],
    }
    monkeypatch.setattr("koda.services.execution_policy.AGENT_EXECUTION_POLICY", policy)
    before = _tree(work_dir)
    mock_context.user_data["work_dir"] = str(work_dir)
    mock_context.args = args

    with patch("koda.handlers.fileops.send_long_message", new_callable=AsyncMock) as mock_send:
        await handler(mock_update, mock_context)

    mock_send.assert_not_called()
    assert mock_update.message.reply_text.call_args.args[0] == "Matched execution-policy rule."
    assert "reply_markup" not in mock_update.message.reply_text.call_args.kwargs
    assert _tree(work_dir) == before
