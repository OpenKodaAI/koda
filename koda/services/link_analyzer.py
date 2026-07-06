"""Link metadata fetching, keyboard building, and prompt construction for link analysis."""

import asyncio
import json
import re
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from koda.logging_config import get_logger
from koda.utils.url_detector import LinkType, classify_url, extract_youtube_id, url_hash

log = get_logger(__name__)


@dataclass
class LinkMetadata:
    url: str
    link_type: LinkType
    title: str = ""
    description: str = ""
    site_name: str = ""
    thumbnail_url: str = ""
    youtube_id: str | None = None
    duration: str = ""
    has_transcript: bool = False

    def summary_text(self) -> str:
        """Format metadata as a preview message."""
        parts = []
        if self.site_name:
            parts.append(f"🌐 <b>{_escape(self.site_name)}</b>")
        if self.title:
            parts.append(f"📄 <b>{_escape(self.title)}</b>")
        if self.description:
            desc = self.description[:200]
            if len(self.description) > 200:
                desc += "…"
            parts.append(f"\n{_escape(desc)}")
        if self.duration:
            parts.append(f"⏱ {_escape(self.duration)}")
        if not parts:
            parts.append(f"🔗 {_escape(self.url)}")
        return "\n".join(parts)


def _escape(text: str) -> str:
    """Escape HTML special characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def fetch_link_metadata(url: str) -> LinkMetadata:
    """Fetch metadata for a URL. Dispatches to YouTube or OG tags."""
    link_type = classify_url(url)
    meta = LinkMetadata(url=url, link_type=link_type)

    youtube_id = extract_youtube_id(url)
    if youtube_id:
        meta.youtube_id = youtube_id
        meta.link_type = LinkType.VIDEO
        await _fetch_youtube_metadata(meta)
    else:
        await _fetch_og_metadata(meta)

    return meta


async def _fetch_og_metadata(meta: LinkMetadata) -> None:
    """Extract OpenGraph tags from HTML."""
    from koda.services.http_client import fetch_url

    html = await fetch_url(meta.url)
    if html.startswith("Error:"):
        log.warning("og_fetch_failed", url=meta.url, error=html)
        return

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        og_title = soup.find("meta", property="og:title")
        og_title_content = og_title.get("content") if og_title else None
        if isinstance(og_title_content, str) and og_title_content:
            meta.title = og_title_content
        elif soup.title:
            meta.title = soup.title.get_text(strip=True)

        og_desc = soup.find("meta", property="og:description")
        og_desc_content = og_desc.get("content") if og_desc else None
        if isinstance(og_desc_content, str) and og_desc_content:
            meta.description = og_desc_content

        og_site = soup.find("meta", property="og:site_name")
        og_site_content = og_site.get("content") if og_site else None
        if isinstance(og_site_content, str) and og_site_content:
            meta.site_name = og_site_content

        og_image = soup.find("meta", property="og:image")
        og_image_content = og_image.get("content") if og_image else None
        if isinstance(og_image_content, str) and og_image_content:
            meta.thumbnail_url = og_image_content

    except ImportError:
        log.warning("beautifulsoup4_not_installed")
        # Try basic regex fallback for title
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        if title_match:
            meta.title = title_match.group(1).strip()


async def _fetch_youtube_metadata(meta: LinkMetadata) -> None:
    """Fetch YouTube metadata using yt-dlp."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            meta.url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            log.warning("ytdlp_failed", url=meta.url, stderr=stderr.decode()[:200])
            await _fetch_og_metadata(meta)
            return

        data = json.loads(stdout.decode())
        meta.title = data.get("title", "")
        meta.description = data.get("description", "")[:500]
        meta.site_name = "YouTube"
        meta.thumbnail_url = data.get("thumbnail", "")

        duration_secs = data.get("duration")
        if duration_secs:
            mins, secs = divmod(int(duration_secs), 60)
            hours, mins = divmod(mins, 60)
            if hours:
                meta.duration = f"{hours}h{mins:02d}m{secs:02d}s"
            else:
                meta.duration = f"{mins}m{secs:02d}s"

        # Check if subtitles are available
        subtitles = data.get("subtitles", {})
        auto_subs = data.get("automatic_captions", {})
        meta.has_transcript = bool(subtitles or auto_subs)

    except FileNotFoundError:
        log.warning("ytdlp_not_found", url=meta.url)
        await _fetch_og_metadata(meta)
    except Exception as e:
        log.warning("ytdlp_error", url=meta.url, error=str(e))
        await _fetch_og_metadata(meta)


async def fetch_youtube_transcript(url: str, lang: str = "pt") -> str | None:
    """Fetch YouTube transcript using yt-dlp subtitles."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = str(Path(tmpdir) / "sub")
        try:
            proc = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang",
                f"{lang},en",
                "--skip-download",
                "--sub-format",
                "vtt",
                "-o",
                output_template,
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)

            # Find the subtitle file
            tmppath = Path(tmpdir)
            vtt_files = list(tmppath.glob("*.vtt"))
            if not vtt_files:
                return None

            # Parse VTT to plain text
            content = vtt_files[0].read_text(encoding="utf-8", errors="replace")
            return _parse_vtt(content)

        except FileNotFoundError:
            log.warning("ytdlp_not_found_transcript")
            return None
        except Exception as e:
            log.warning("transcript_error", error=str(e))
            return None


def _parse_vtt(vtt_content: str) -> str:
    """Parse VTT subtitle content to plain text with timestamps."""
    lines = vtt_content.split("\n")
    result = []
    timestamp_pattern = re.compile(r"(\d{2}:\d{2}:\d{2})\.\d{3}\s*-->")
    seen_text = set()

    current_time = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue

        ts_match = timestamp_pattern.match(line)
        if ts_match:
            current_time = ts_match.group(1)
            continue

        # Skip numeric cue identifiers
        if line.isdigit():
            continue

        # Remove HTML tags from subtitle text
        clean = re.sub(r"<[^>]+>", "", line)
        if clean and clean not in seen_text:
            seen_text.add(clean)
            if current_time:
                result.append(f"[{current_time}] {clean}")
            else:
                result.append(clean)

    return "\n".join(result)


def build_link_keyboard(meta: LinkMetadata) -> InlineKeyboardMarkup:
    """Build inline keyboard with analysis options."""
    h = url_hash(meta.url)

    if meta.link_type == LinkType.VIDEO:
        rows = [
            [
                InlineKeyboardButton("📜 Transcript", callback_data=f"link:transcript:{h}"),
                InlineKeyboardButton("🖼 Thumbnail", callback_data=f"link:thumbnail:{h}"),
            ],
            [
                InlineKeyboardButton("📝 Summary", callback_data=f"link:summary:{h}"),
                InlineKeyboardButton("💡 Main Idea", callback_data=f"link:main_idea:{h}"),
            ],
            [
                InlineKeyboardButton("📋 Structure", callback_data=f"link:structure:{h}"),
                InlineKeyboardButton("🔍 Full Analysis", callback_data=f"link:full:{h}"),
            ],
        ]
    else:
        rows = [
            [
                InlineKeyboardButton("📝 Summary", callback_data=f"link:summary:{h}"),
                InlineKeyboardButton("🔑 Key Points", callback_data=f"link:key_points:{h}"),
            ],
            [
                InlineKeyboardButton("🔍 Full Analysis", callback_data=f"link:full:{h}"),
            ],
        ]

    return InlineKeyboardMarkup(rows)


def build_analysis_prompt(action: str, meta: LinkMetadata, transcript_text: str | None = None) -> str:
    """Build a prompt for provider execution based on the selected action."""
    base = f"Analyze the content at this link: {meta.url}"
    if meta.title:
        base += f"\nTitle: {meta.title}"
    if meta.description:
        base += f"\nDescription: {meta.description[:300]}"

    prompts = {
        "summary": (
            f"{base}\n\n"
            "Write a concise, well-structured summary of the content.\n"
            "1. Start with one sentence that captures the essence of the content.\n"
            "2. List the main points covered as bullet points.\n"
            "3. Include relevant data, numbers, or quotes when available.\n"
            "4. End with conclusions or practical takeaways.\n"
            "Keep the summary objective and informative — the reader should understand the content without needing "
            "to open the link."
        ),
        "main_idea": (
            f"{base}\n\n"
            "Identify and explain the main idea / central thesis of the content in 2–3 paragraphs.\n"
            "Be direct: what is the most important message the author is trying to convey?\n"
            "If supporting arguments are present, mention the strongest ones."
        ),
        "key_points": (
            f"{base}\n\n"
            "List the key points of the content as bullet points.\n"
            "Focus on: verifiable facts, quantitative data, core arguments, and conclusions.\n"
            "Order by relevance (most important first). Omit secondary details."
        ),
        "structure": (
            f"{base}\n\n"
            "Describe how the content is organized:\n"
            "- What are the main sections / chapters / topics?\n"
            "- How do they connect (logical sequence, progression, comparison)?\n"
            "- What is the thread that ties the parts together?\n"
            "This helps understand the author's logic without reading the full content."
        ),
        "full": (
            f"{base}\n\n"
            "Produce a complete, detailed analysis of the content:\n"
            "1. Overall summary (2–3 paragraphs)\n"
            "2. Key points (bullet points of the main facts and arguments)\n"
            "3. Main idea / central thesis\n"
            "4. Strengths (what the content does well)\n"
            "5. Weaknesses or gaps (what is missing or could be better)\n"
            "6. Conclusions and practical takeaways for the reader"
        ),
    }

    if action == "transcript" and transcript_text:
        return (
            f"{base}\n\n"
            "Below is the video transcript. Format it in a clear, readable way:\n"
            "1. Group by topic / section when the subject changes.\n"
            "2. Keep timestamps relevant to the main points.\n"
            "3. Correct obvious auto-transcription errors.\n"
            "4. Remove unnecessary repetition and hesitations.\n\n"
            f"<transcript>\n{transcript_text}\n</transcript>"
        )

    return prompts.get(action, f"{base}\n\nAnalyze this content.")


def meta_to_dict(meta: LinkMetadata) -> dict:
    """Serialize LinkMetadata to dict for persistence."""
    return {
        "url": meta.url,
        "link_type": meta.link_type.value,
        "title": meta.title,
        "description": meta.description,
        "site_name": meta.site_name,
        "thumbnail_url": meta.thumbnail_url,
        "youtube_id": meta.youtube_id,
        "duration": meta.duration,
        "has_transcript": meta.has_transcript,
    }


def dict_to_meta(d: dict) -> LinkMetadata:
    """Deserialize dict to LinkMetadata."""
    return LinkMetadata(
        url=d["url"],
        link_type=LinkType(d["link_type"]),
        title=d.get("title", ""),
        description=d.get("description", ""),
        site_name=d.get("site_name", ""),
        thumbnail_url=d.get("thumbnail_url", ""),
        youtube_id=d.get("youtube_id"),
        duration=d.get("duration", ""),
        has_transcript=d.get("has_transcript", False),
    )
