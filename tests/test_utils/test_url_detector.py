"""Tests for URL detection and classification utilities."""

from koda.utils.url_detector import (
    LinkType,
    classify_url,
    extract_urls,
    extract_youtube_id,
    is_link_message,
    url_hash,
)


class TestExtractUrls:
    def test_extract_urls(self):
        text = "veja isso https://example.com e https://youtube.com/watch?v=abc123"
        urls = extract_urls(text)
        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "https://youtube.com/watch?v=abc123" in urls

    def test_extract_urls_no_urls(self):
        assert extract_urls("no links here") == []

    def test_extract_urls_http(self):
        urls = extract_urls("check http://example.com")
        assert len(urls) == 1
        assert "http://example.com" in urls

    def test_extract_urls_with_path(self):
        urls = extract_urls("https://example.com/path/to/page?q=1&b=2")
        assert len(urls) == 1


class TestIsLinkMessage:
    def test_url_only(self):
        assert is_link_message("https://youtube.com/watch?v=abc") is True

    def test_url_with_short_text(self):
        assert is_link_message("veja isso https://example.com") is True

    def test_url_with_long_text(self):
        long_text = (
            "preciso que você analise o conteúdo desse artigo e me diga se as conclusões são válidas "
            "https://example.com"
        )
        assert is_link_message(long_text) is False

    def test_no_url(self):
        assert is_link_message("just plain text") is False

    def test_empty(self):
        assert is_link_message("") is False

    def test_none_like(self):
        assert is_link_message("") is False


class TestClassifyUrl:
    def test_youtube(self):
        assert classify_url("https://www.youtube.com/watch?v=abc") == LinkType.VIDEO

    def test_youtu_be(self):
        assert classify_url("https://youtu.be/abc123") == LinkType.VIDEO

    def test_vimeo(self):
        assert classify_url("https://vimeo.com/123456") == LinkType.VIDEO

    def test_article(self):
        assert classify_url("https://example.com/article") == LinkType.ARTICLE

    def test_github(self):
        assert classify_url("https://github.com/user/repo") == LinkType.ARTICLE


class TestExtractYoutubeId:
    def test_watch_format(self):
        assert extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_format(self):
        assert extract_youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_format(self):
        assert extract_youtube_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_format(self):
        assert extract_youtube_id("https://youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_no_youtube(self):
        assert extract_youtube_id("https://example.com/page") is None

    def test_watch_with_params(self):
        assert extract_youtube_id("https://youtube.com/watch?v=abc12345678&list=PLxyz") == "abc12345678"


class TestUrlHash:
    def test_deterministic(self):
        url = "https://example.com/test"
        assert url_hash(url) == url_hash(url)

    def test_length(self):
        h = url_hash("https://example.com")
        assert len(h) == 10

    def test_different_urls(self):
        assert url_hash("https://a.com") != url_hash("https://b.com")
