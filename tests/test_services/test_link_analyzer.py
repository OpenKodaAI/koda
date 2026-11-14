"""Tests for link analyzer service."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.link_analyzer import (
    LinkMetadata,
    _fetch_youtube_metadata,
    _parse_vtt,
    build_analysis_prompt,
    build_link_keyboard,
    dict_to_meta,
    fetch_link_metadata,
    fetch_youtube_transcript,
    meta_to_dict,
)
from koda.utils.url_detector import LinkType


class TestFetchOgMetadata:
    @pytest.mark.asyncio
    async def test_fetch_og_metadata(self):
        html = """
        <html>
        <head>
            <meta property="og:title" content="Test Article" />
            <meta property="og:description" content="A test description" />
            <meta property="og:site_name" content="TestSite" />
            <meta property="og:image" content="https://example.com/image.jpg" />
        </head>
        <body></body>
        </html>
        """
        with patch("koda.services.http_client.fetch_url", new_callable=AsyncMock, return_value=html):
            meta = await fetch_link_metadata("https://example.com/article")

        assert meta.title == "Test Article"
        assert meta.description == "A test description"
        assert meta.site_name == "TestSite"
        assert meta.thumbnail_url == "https://example.com/image.jpg"
        assert meta.link_type == LinkType.ARTICLE


class TestFetchYoutubeMetadata:
    @pytest.mark.asyncio
    async def test_fetch_youtube_metadata(self):
        ytdlp_data = {
            "title": "Test Video",
            "description": "A test video description",
            "thumbnail": "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
            "duration": 125,
            "subtitles": {"en": []},
        }

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(ytdlp_data).encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            meta = await fetch_link_metadata("https://www.youtube.com/watch?v=abc12345678")

        assert meta.title == "Test Video"
        assert meta.site_name == "YouTube"
        assert meta.youtube_id == "abc12345678"
        assert meta.duration == "2m05s"
        assert meta.has_transcript is True
        assert meta.link_type == LinkType.VIDEO

    @pytest.mark.asyncio
    async def test_fetch_youtube_metadata_fallback(self):
        """When yt-dlp is not found, should fallback to OG tags."""
        og_html = '<html><head><meta property="og:title" content="Fallback Title" /></head></html>'

        with (
            patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError),
            patch("koda.services.http_client.fetch_url", new_callable=AsyncMock, return_value=og_html),
        ):
            meta = await fetch_link_metadata("https://www.youtube.com/watch?v=abc12345678")

        assert meta.title == "Fallback Title"
        assert meta.youtube_id == "abc12345678"


def _finished_ytdlp(stdout: bytes = b"") -> AsyncMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    proc.returncode = 0
    return proc


class TestYtDlpOnlySeesCanonicalYoutubeUrls:
    """yt-dlp resolves DNS and follows redirects itself, outside the SSRF guard.

    It must therefore never be handed the user's URL, only a watch URL built
    from a validated video ID.
    """

    @pytest.mark.asyncio
    async def test_private_url_embedding_a_youtube_id_never_reaches_ytdlp(self):
        from koda.services import http_client

        url = "http://169.254.169.254/latest/meta-data/?youtu.be/AAAAAAAAAAA"
        with (
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as spawn,
            patch.object(http_client, "fetch_url", wraps=http_client.fetch_url) as fetch,
        ):
            meta = await fetch_link_metadata(url)

        spawn.assert_not_called()
        fetch.assert_awaited_once_with(url)  # the guarded fetch, which refuses the metadata address
        assert meta.youtube_id is None
        assert meta.link_type == LinkType.ARTICLE
        assert meta.title == ""

    @pytest.mark.asyncio
    async def test_metadata_lookup_passes_canonical_watch_url(self):
        meta = LinkMetadata(
            url="http://127.0.0.1:2375/containers/json",
            link_type=LinkType.VIDEO,
            youtube_id="abc12345678",
        )
        with patch(
            "asyncio.create_subprocess_exec", return_value=_finished_ytdlp(json.dumps({"title": "T"}).encode())
        ) as spawn:
            await _fetch_youtube_metadata(meta)

        args = spawn.call_args.args
        assert args[0] == "yt-dlp"
        assert args[-1] == "https://www.youtube.com/watch?v=abc12345678"
        assert meta.url not in args
        assert meta.title == "T"

    @pytest.mark.asyncio
    async def test_youtube_link_is_looked_up_by_id_not_by_the_raw_url(self):
        with patch("asyncio.create_subprocess_exec", return_value=_finished_ytdlp(b"{}")) as spawn:
            await fetch_link_metadata("https://www.youtube.com/watch?v=abc12345678&feature=share#t=1")

        assert spawn.call_args.args[-1] == "https://www.youtube.com/watch?v=abc12345678"

    @pytest.mark.asyncio
    async def test_transcript_lookup_passes_canonical_watch_url(self):
        with patch("asyncio.create_subprocess_exec", return_value=_finished_ytdlp()) as spawn:
            assert await fetch_youtube_transcript("abc12345678") is None  # no .vtt was written

        args = spawn.call_args.args
        assert args[0] == "yt-dlp"
        assert args[-1] == "https://www.youtube.com/watch?v=abc12345678"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_id", ["", "abc", "--exec=id x", "http://127.0.0.1:2375/xx"])
    async def test_transcript_lookup_rejects_malformed_ids(self, bad_id):
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as spawn:
            assert await fetch_youtube_transcript(bad_id) is None

        spawn.assert_not_called()


class TestParseVtt:
    def test_basic_vtt(self):
        vtt = (
            "WEBVTT\n"
            "Kind: captions\n"
            "Language: en\n\n"
            "00:00:01.000 --> 00:00:03.000\n"
            "Hello world\n\n"
            "00:00:04.000 --> 00:00:06.000\n"
            "This is a test\n"
        )
        result = _parse_vtt(vtt)
        assert "[00:00:01] Hello world" in result
        assert "[00:00:04] This is a test" in result

    def test_vtt_strips_html_tags(self):
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<b>Bold text</b> and <i>italic</i>\n"
        result = _parse_vtt(vtt)
        assert "Bold text and italic" in result
        assert "<b>" not in result

    def test_vtt_deduplicates(self):
        vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nRepeated line\n\n00:00:04.000 --> 00:00:06.000\nRepeated line\n"
        result = _parse_vtt(vtt)
        assert result.count("Repeated line") == 1


class TestBuildLinkKeyboard:
    def test_build_link_keyboard_video(self):
        meta = LinkMetadata(
            url="https://youtube.com/watch?v=abc",
            link_type=LinkType.VIDEO,
            youtube_id="abc",
        )
        keyboard = build_link_keyboard(meta)
        # Video should have 3 rows
        assert len(keyboard.inline_keyboard) == 3
        # First row: Transcript + Thumbnail
        assert len(keyboard.inline_keyboard[0]) == 2
        assert "Transcript" in keyboard.inline_keyboard[0][0].text
        assert "Thumbnail" in keyboard.inline_keyboard[0][1].text
        # All callback_data should start with "link:"
        for row in keyboard.inline_keyboard:
            for btn in row:
                assert btn.callback_data.startswith("link:")

    def test_build_link_keyboard_article(self):
        meta = LinkMetadata(
            url="https://example.com/article",
            link_type=LinkType.ARTICLE,
        )
        keyboard = build_link_keyboard(meta)
        # Article should have 2 rows
        assert len(keyboard.inline_keyboard) == 2
        # First row: Summary + Key Points
        assert "Summary" in keyboard.inline_keyboard[0][0].text
        assert "Key Points" in keyboard.inline_keyboard[0][1].text


class TestBuildAnalysisPrompt:
    def test_summary_prompt(self):
        meta = LinkMetadata(
            url="https://example.com",
            link_type=LinkType.ARTICLE,
            title="Test",
        )
        prompt = build_analysis_prompt("summary", meta)
        assert "https://example.com" in prompt
        assert "summary" in prompt.lower()
        assert "Test" in prompt

    def test_transcript_prompt(self):
        meta = LinkMetadata(
            url="https://youtube.com/watch?v=abc",
            link_type=LinkType.VIDEO,
            title="Video",
        )
        prompt = build_analysis_prompt("transcript", meta, transcript_text="[00:00:01] Hello world")
        assert "<transcript>" in prompt
        assert "Hello world" in prompt

    def test_unknown_action_fallback(self):
        meta = LinkMetadata(url="https://example.com", link_type=LinkType.ARTICLE)
        prompt = build_analysis_prompt("unknown_action", meta)
        assert "https://example.com" in prompt


class TestMetaSerialization:
    def test_roundtrip(self):
        meta = LinkMetadata(
            url="https://youtube.com/watch?v=abc",
            link_type=LinkType.VIDEO,
            title="Test Video",
            description="A description",
            site_name="YouTube",
            thumbnail_url="https://img.youtube.com/vi/abc/maxresdefault.jpg",
            youtube_id="abc",
            duration="5m30s",
            has_transcript=True,
        )
        d = meta_to_dict(meta)
        restored = dict_to_meta(d)

        assert restored.url == meta.url
        assert restored.link_type == meta.link_type
        assert restored.title == meta.title
        assert restored.description == meta.description
        assert restored.site_name == meta.site_name
        assert restored.thumbnail_url == meta.thumbnail_url
        assert restored.youtube_id == meta.youtube_id
        assert restored.duration == meta.duration
        assert restored.has_transcript == meta.has_transcript

    def test_dict_format(self):
        meta = LinkMetadata(url="https://example.com", link_type=LinkType.ARTICLE)
        d = meta_to_dict(meta)
        assert d["link_type"] == "article"
        assert d["url"] == "https://example.com"
