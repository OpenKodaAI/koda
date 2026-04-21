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
    base = f"Analise o conteúdo do link: {meta.url}"
    if meta.title:
        base += f"\nTítulo: {meta.title}"
    if meta.description:
        base += f"\nDescrição: {meta.description[:300]}"

    prompts = {
        "summary": (
            f"{base}\n\n"
            "Faça um resumo conciso e bem estruturado do conteúdo.\n"
            "1. Comece com uma frase que capture a essência do conteúdo.\n"
            "2. Liste os principais pontos abordados com bullet points.\n"
            "3. Inclua dados, números ou citações relevantes quando houver.\n"
            "4. Termine com as conclusões ou takeaways práticos.\n"
            "Mantenha o resumo objetivo e informativo — o leitor deve entender o conteúdo sem precisar acessar o link."
        ),
        "main_idea": (
            f"{base}\n\n"
            "Identifique e explique a ideia principal/tese central do conteúdo em 2-3 parágrafos.\n"
            "Seja direto: qual é a mensagem mais importante que o autor quer transmitir?\n"
            "Se houver argumentos que sustentam essa tese, mencione os mais fortes."
        ),
        "key_points": (
            f"{base}\n\n"
            "Liste os pontos-chave do conteúdo em formato de bullet points.\n"
            "Foque em: fatos verificáveis, dados quantitativos, argumentos centrais e conclusões.\n"
            "Ordene por relevância (mais importante primeiro). Omita detalhes secundários."
        ),
        "structure": (
            f"{base}\n\n"
            "Descreva como o conteúdo está organizado:\n"
            "- Quais são as seções/capítulos/tópicos principais?\n"
            "- Como eles se conectam (sequência lógica, progressão, comparação)?\n"
            "- Qual é o fio condutor que liga as partes?\n"
            "Isso ajuda a entender a lógica do autor sem ler o conteúdo completo."
        ),
        "full": (
            f"{base}\n\n"
            "Faça uma análise completa e detalhada do conteúdo:\n"
            "1. Resumo geral (2-3 parágrafos)\n"
            "2. Pontos-chave (bullet points dos fatos e argumentos principais)\n"
            "3. Ideia principal/tese central\n"
            "4. Pontos fortes (o que o conteúdo faz bem)\n"
            "5. Pontos fracos ou lacunas (o que falta ou poderia ser melhor)\n"
            "6. Conclusões e takeaways práticos para o leitor"
        ),
    }

    if action == "transcript" and transcript_text:
        return (
            f"{base}\n\n"
            "Abaixo está a transcrição do vídeo. Formate-a de forma clara e legível:\n"
            "1. Organize por tópicos/seções quando houver mudança de assunto.\n"
            "2. Mantenha timestamps relevantes para os pontos principais.\n"
            "3. Corrija erros óbvios de transcrição automática.\n"
            "4. Remova repetições e hesitações desnecessárias.\n\n"
            f"<transcript>\n{transcript_text}\n</transcript>"
        )

    return prompts.get(action, f"{base}\n\nAnalise este conteúdo.")


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
