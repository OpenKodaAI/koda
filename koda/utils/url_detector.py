"""URL detection, classification, and utility functions for link analysis."""

import hashlib
import re
from enum import Enum

URL_PATTERN = re.compile(
    r"https?://[^\s<>\"')\]]+",
    re.IGNORECASE,
)

_YOUTUBE_DOMAINS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "youtube-nocookie.com"}
_VIDEO_DOMAINS = _YOUTUBE_DOMAINS | {"vimeo.com", "www.vimeo.com", "dailymotion.com", "www.dailymotion.com"}

_YOUTUBE_ID_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?.*v=|youtu\.be/)([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtube\.com/embed/([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtube\.com/v/([a-zA-Z0-9_-]{11})"),
]


class LinkType(Enum):
    VIDEO = "video"
    ARTICLE = "article"


def extract_urls(text: str) -> list[str]:
    """Extract all HTTP(S) URLs from text."""
    return URL_PATTERN.findall(text)


def is_link_message(text: str) -> bool:
    """Return True if the text is primarily a URL (< 30 chars of non-URL text)."""
    if not text:
        return False
    urls = extract_urls(text)
    if not urls:
        return False
    remaining = text
    for url in urls:
        remaining = remaining.replace(url, "", 1)
    non_url_text = remaining.strip()
    return len(non_url_text) < 30


def classify_url(url: str) -> LinkType:
    """Classify URL as VIDEO or ARTICLE based on domain."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname in _VIDEO_DOMAINS:
        return LinkType.VIDEO
    return LinkType.ARTICLE


def extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    for pattern in _YOUTUBE_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def url_hash(url: str) -> str:
    """Generate a short, stable hash for callback_data."""
    return hashlib.blake2s(url.encode(), digest_size=5).hexdigest()
