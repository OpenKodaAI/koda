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
async def test_http_makes_request(mock_update, mock_context):
    mock_context.args = ["POST", "https://api.example.com", '{"key":"val"}']
    with (
        patch("koda.handlers.automation.make_http_request", new_callable=AsyncMock) as mock_req,
        patch("koda.handlers.automation.send_long_message", new_callable=AsyncMock),
    ):
        mock_req.return_value = "HTTP 200 OK"
        await cmd_http(mock_update, mock_context)
        mock_req.assert_called_once_with("POST", "https://api.example.com", body='{"key":"val"}')


@pytest.mark.asyncio
async def test_curl_no_args(mock_update, mock_context):
    mock_context.args = []
    await cmd_curl(mock_update, mock_context)
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


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
