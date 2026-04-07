"""Tests for enhanced browser tool handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.tool_dispatcher import (
    ToolContext,
)


def _make_ctx(**overrides) -> ToolContext:
    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir="/tmp",
        user_data={
            "work_dir": "/tmp",
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


def _patch_browser_available():
    """Patch _check_browser_available to return None (no error)."""
    return patch(
        "koda.services.tool_dispatcher._check_browser_available",
        new_callable=AsyncMock,
        return_value=None,
    )


class TestBrowserExecuteJs:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_browser_execute_js

        with patch("koda.services.tool_dispatcher.BROWSER_FEATURES_ENABLED", False):
            result = await _handle_browser_execute_js({"script": "1+1"}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_missing_script(self):
        from koda.services.tool_dispatcher import _handle_browser_execute_js

        with _patch_browser_available():
            result = await _handle_browser_execute_js({}, _make_ctx())
        assert not result.success
        assert "script" in result.output.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_execute_js

        with (
            _patch_browser_available(),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.execute_js = AsyncMock(return_value="42")
            result = await _handle_browser_execute_js({"script": "1+1"}, _make_ctx())
        assert result.success
        assert "42" in result.output


class TestBrowserDownload:
    @pytest.mark.asyncio
    async def test_missing_url(self):
        from koda.services.tool_dispatcher import _handle_browser_download

        with _patch_browser_available():
            result = await _handle_browser_download({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_download

        with (
            _patch_browser_available(),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.download_file = AsyncMock(return_value="Downloaded: /tmp/file.pdf (1024 bytes)")
            result = await _handle_browser_download({"url": "https://example.com/file.pdf"}, _make_ctx())
        assert result.success


class TestBrowserUpload:
    @pytest.mark.asyncio
    async def test_missing_file_path(self):
        from koda.services.tool_dispatcher import _handle_browser_upload

        with _patch_browser_available():
            result = await _handle_browser_upload({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_upload

        with (
            _patch_browser_available(),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.upload_file = AsyncMock(return_value="Uploaded: doc.pdf to input")
            result = await _handle_browser_upload({"file_path": "/tmp/doc.pdf"}, _make_ctx())
        assert result.success


class TestBrowserSetViewport:
    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_set_viewport

        with (
            _patch_browser_available(),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.set_viewport = AsyncMock(return_value="Viewport set to 1920x1080")
            result = await _handle_browser_set_viewport({"width": 1920, "height": 1080}, _make_ctx())
        assert result.success


class TestBrowserPdf:
    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_browser_pdf

        with (
            _patch_browser_available(),
            patch("koda.services.browser_manager.browser_manager") as mock_bm,
        ):
            mock_bm.page_to_pdf = AsyncMock(return_value="PDF saved: /tmp/page.pdf (5000 bytes)")
            result = await _handle_browser_pdf({}, _make_ctx())
        assert result.success


class TestBrowserPromptEnhancements:
    def test_new_tools_in_prompt(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        with patch("koda.services.tool_prompt.BROWSER_FEATURES_ENABLED", True):
            prompt = build_agent_tools_prompt()
        assert "browser_execute_js" not in prompt
        assert "browser_download" not in prompt
        assert "browser_upload" not in prompt
        assert "browser_set_viewport" not in prompt
