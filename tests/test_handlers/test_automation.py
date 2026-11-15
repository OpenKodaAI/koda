"""Tests for automation command handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.handlers.automation import cmd_cron, cmd_curl, cmd_fetch, cmd_http, cmd_search


@pytest.mark.asyncio
async def test_search_no_args(mock_update, mock_context):
    mock_context.args = []
    await cmd_search(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_search_runs(mock_update, mock_context):
    mock_context.args = ["python", "asyncio"]
    with (
        patch("koda.handlers.automation.search_web", new_callable=AsyncMock) as mock_search,
        patch("koda.handlers.automation.send_long_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_search.return_value = "Result 1\nResult 2"
        await cmd_search(mock_update, mock_context)
        mock_search.assert_called_once_with("python asyncio")
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_no_args(mock_update, mock_context):
    mock_context.args = []
    await cmd_fetch(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_fetch_adds_https(mock_update, mock_context):
    mock_context.args = ["example.com"]
    with (
        patch("koda.handlers.automation.fetch_url", new_callable=AsyncMock) as mock_fetch,
        patch("koda.handlers.automation.send_long_message", new_callable=AsyncMock),
    ):
        mock_fetch.return_value = "content"
        await cmd_fetch(mock_update, mock_context)
        mock_fetch.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
async def test_http_no_args(mock_update, mock_context):
    mock_context.args = []
    await cmd_http(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_http_post_requests_approval_before_request(mock_update, mock_context):
    mock_context.args = ["POST", "https://api.example.com", '{"key":"val"}']
    with (
        patch("koda.handlers.automation.make_http_request", new_callable=AsyncMock) as mock_req,
        patch("koda.handlers.automation.send_long_message", new_callable=AsyncMock),
    ):
        await cmd_http(mock_update, mock_context)
        mock_req.assert_not_called()
    assert "Confirmacao necessaria" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_curl_no_args(mock_update, mock_context):
    mock_context.args = []
    await cmd_curl(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


async def _command_output(command, mock_update, mock_context, args):
    """What a fetch command sends for ``args``: the URL fetched, the replies and the long message."""
    mock_update.message.reply_text.reset_mock()
    mock_context.args = list(args)
    with (
        patch("koda.handlers.automation.fetch_url", new_callable=AsyncMock) as mock_fetch,
        patch("koda.handlers.automation.send_long_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_fetch.return_value = "<h1>Example Domain</h1>"
        await command(mock_update, mock_context)
    return (
        [call.args for call in mock_fetch.call_args_list],
        [call.args[0] for call in mock_update.message.reply_text.call_args_list],
        [call.args[1] for call in mock_send.call_args_list],
    )


@pytest.mark.asyncio
async def test_fetch_output_characterisation(mock_update, mock_context):
    # M6-E3-T4: what /fetch answers. /curl is routed to this handler, so this is also /curl's output.
    assert await _command_output(cmd_fetch, mock_update, mock_context, ["example.com"]) == (
        [("https://example.com",)],
        ["Fetching..."],
        ["<h1>Example Domain</h1>"],
    )
    assert await _command_output(cmd_fetch, mock_update, mock_context, []) == ([], ["Usage: /fetch <url>"], [])


@pytest.mark.asyncio
@pytest.mark.parametrize("args", [["example.com"], ["https://example.com/a", "b"], []])
async def test_curl_gives_the_fetch_result_for_the_same_url(mock_update, mock_context, args):
    # M6-E3-T4: /curl is an alias of /fetch. Before, /curl sent no "Fetching..." notice, wrapped the
    # page in a code block and answered "Usage: /curl <url>" without a URL.
    fetch_output = await _command_output(cmd_fetch, mock_update, mock_context, args)
    assert await _command_output(cmd_curl, mock_update, mock_context, args) == fetch_output


def test_curl_is_routed_to_the_fetch_handler():
    assert cmd_curl is cmd_fetch


@pytest.mark.asyncio
async def test_tool_catalog_lists_curl_as_an_alias_of_fetch():
    import json
    from unittest.mock import MagicMock

    from koda.control_plane.api import list_agent_tools_catalog_route

    response = await list_agent_tools_catalog_route(MagicMock())
    items = {item["id"]: item["description"] for item in json.loads(response.text)["items"]}
    assert items["fetch"] == "Fetch a URL"
    assert items["curl"] == "Alias of /fetch: fetch a URL"


# --- cmd_cron tests ---


@pytest.mark.asyncio
async def test_cron_no_args(mock_update, mock_context):
    mock_context.args = []
    await cmd_cron(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cron_list_empty(mock_update, mock_context):
    mock_context.args = ["list"]
    with patch("koda.services.cron_store.list_cron_jobs", return_value=[]):
        await cmd_cron(mock_update, mock_context)
    assert "No cron jobs" in mock_update.message.reply_text.call_args[0][0]


_CRON_ROWS = [
    {
        "id": 5,
        "job_type": "shell_command",
        "status": "active",
        "schedule_expr": "*/5 * * * *",
        "payload": {"command": "uptime", "description": "load"},
        "work_dir": "/tmp",
    },
    {
        "id": 6,
        "job_type": "shell_command",
        "status": "paused",
        "schedule_expr": "0 * * * *",
        "payload": {"command": "df -h"},
        "work_dir": "/tmp",
    },
]


@pytest.mark.asyncio
async def test_cron_list_lines(mock_update, mock_context):
    mock_context.args = ["list"]
    with (
        patch("koda.services.cron_store.list_jobs", return_value=_CRON_ROWS),
        patch("koda.handlers.automation.send_long_message", new_callable=AsyncMock) as mock_send,
    ):
        await cmd_cron(mock_update, mock_context)
    assert mock_send.call_args[0][1] == (
        "Your legacy cron jobs:\n\n#5 [ON] `*/5 * * * *` → uptime (load)\n#6 [OFF] `0 * * * *` → df -h"
    )


@pytest.mark.asyncio
async def test_cron_add_missing_args(mock_update, mock_context):
    mock_context.args = ["add"]
    await cmd_cron(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cron_add_blocks_metachar(mock_update, mock_context):
    mock_context.args = ["add", '"*/5 * * * *"', "echo", "hello;", "rm", "-rf"]
    await cmd_cron(mock_update, mock_context)
    assert "meta-characters" in mock_update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
async def test_cron_add_blocks_dangerous(mock_update, mock_context):
    mock_context.args = ["add", '"*/5 * * * *"', "rm", "-rf", "/"]
    await cmd_cron(mock_update, mock_context)
    assert "Blocked" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cron_del_no_args(mock_update, mock_context):
    mock_context.args = ["del"]
    await cmd_cron(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_cron_unknown_action(mock_update, mock_context):
    mock_context.args = ["foo"]
    await cmd_cron(mock_update, mock_context)
    assert "Unknown action" in mock_update.message.reply_text.call_args[0][0]
