"""Video processing utilities for extracting frames from Jira video attachments."""

import subprocess
from pathlib import Path

from koda.config import IMAGE_TEMP_DIR
from koda.logging_config import get_logger
from koda.utils.audio import is_ffmpeg_available

log = get_logger(__name__)

SUPPORTED_VIDEO_MIMES = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "video/x-msvideo",
        "video/x-matroska",
        "video/mpeg",
        "video/ogg",
    }
)
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_VIDEO_DURATION = 300  # 5 minutes
MAX_FRAMES = 20
FFMPEG_TIMEOUT = 120  # seconds


def is_video_mime(mime_type: str) -> bool:
    """Check if MIME type is a supported video format."""
    return mime_type.lower() in SUPPORTED_VIDEO_MIMES


def get_video_duration(video_path: str) -> float | None:
    """Get video duration in seconds using ffprobe. Returns None on error."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.error("ffprobe_failed", stderr=result.stderr[:200])
            return None
        return float(result.stdout.strip())
    except (TimeoutError, subprocess.TimeoutExpired):
        log.error("ffprobe_timeout")
        return None
    except (ValueError, FileNotFoundError) as e:
        log.error("ffprobe_error", error=str(e))
        return None


def calculate_frame_interval(duration: float) -> tuple[float, int]:
    """Calculate interval between frames and expected frame count.

    Returns (interval_seconds, expected_frame_count).
    """
    if duration <= 10:
        interval = 2.0
    elif duration <= 60:
        interval = 5.0
    else:
        interval = 15.0

    count = max(3, int(duration / interval) + 1)
    count = min(count, MAX_FRAMES)
    return interval, count


def extract_frames(video_path: str, output_prefix: str, interval: float) -> list[str]:
    """Extract frames from video using FFmpeg. Returns list of frame file paths."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                video_path,
                "-vf",
                f"fps=1/{interval},scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease",
                "-q:v",
                "5",
                "-frames:v",
                str(MAX_FRAMES),
                f"{output_prefix}_%03d.jpg",
            ],
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
        if result.returncode != 0:
            log.error("ffmpeg_extract_failed", stderr=result.stderr[:200])
            return []
    except (TimeoutError, subprocess.TimeoutExpired):
        log.error("ffmpeg_extract_timeout")
        return []
    except FileNotFoundError:
        log.error("ffmpeg_not_found")
        return []

    # Collect generated frame files
    parent = Path(output_prefix).parent
    prefix_name = Path(output_prefix).name
    frames = sorted(str(p) for p in parent.glob(f"{prefix_name}_*.jpg"))
    return frames


def _extract_and_transcribe_audio(video_path: str, attachment_id: str) -> str | None:
    """Extract audio from video and transcribe it. Returns transcription or None."""
    audio_path = str(IMAGE_TEMP_DIR / f"jira_video_audio_{attachment_id}.wav")
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i",
                video_path,
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-y",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT,
        )
        if result.returncode != 0:
            log.warning("video_audio_extract_failed", stderr=result.stderr[:200])
            return None

        if not Path(audio_path).exists() or Path(audio_path).stat().st_size < 1600:
            return None

        from koda.services.agent_settings import get_agent_runtime_settings
        from koda.utils.audio import transcribe_audio_sync

        runtime_settings = get_agent_runtime_settings()
        transcription = transcribe_audio_sync(
            audio_path,
            provider=(
                str(runtime_settings.get("transcription_provider") or "").strip().lower() if runtime_settings else None
            ),
            model=str(runtime_settings.get("transcription_model") or "").strip() if runtime_settings else None,
        )
        return transcription
    except (TimeoutError, subprocess.TimeoutExpired):
        log.warning("video_audio_extract_timeout")
        return None
    except Exception as e:
        log.warning("video_audio_transcribe_failed", error=str(e))
        return None
    finally:
        Path(audio_path).unlink(missing_ok=True)


def process_video_attachment(
    video_bytes: bytes,
    filename: str,
    attachment_id: str,
) -> tuple[list[str], str]:
    """Process a video attachment: save, extract frames, return paths and summary.

    Returns (frame_paths, summary_text).
    """
    if not is_ffmpeg_available():
        return [], "Error: FFmpeg is not available. Cannot extract video frames."

    IMAGE_TEMP_DIR.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix or ".mp4"
    video_path = str(IMAGE_TEMP_DIR / f"jira_video_{attachment_id}{ext}")

    try:
        Path(video_path).write_bytes(video_bytes)

        duration = get_video_duration(video_path)
        if duration is None:
            return [], "Error: Could not determine video duration."

        if duration > MAX_VIDEO_DURATION:
            return [], (f"Error: Video too long ({duration:.0f}s). Max duration: {MAX_VIDEO_DURATION}s.")

        interval, expected_count = calculate_frame_interval(duration)
        output_prefix = str(IMAGE_TEMP_DIR / f"jira_frame_{attachment_id}")
        frames = extract_frames(video_path, output_prefix, interval)

        if not frames:
            return [], "Error: Failed to extract frames from video."

        summary_lines = [
            f"Extracted {len(frames)} frames from '{filename}' (duration: {duration:.1f}s, interval: {interval:.0f}s).",
            "",
            "Frame files:",
        ]
        for f in frames:
            summary_lines.append(f"- {f}")

        # Extract and transcribe audio track
        transcription = _extract_and_transcribe_audio(video_path, attachment_id)
        if transcription:
            summary_lines.append("")
            summary_lines.append("### Audio Transcription:")
            summary_lines.append(transcription)

        return frames, "\n".join(summary_lines)

    finally:
        Path(video_path).unlink(missing_ok=True)


def cleanup_video_frames(frame_paths: list[str]) -> None:
    """Delete extracted frame files."""
    for path in frame_paths:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            log.warning("frame_cleanup_failed", path=path)
