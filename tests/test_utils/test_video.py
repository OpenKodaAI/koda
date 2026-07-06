"""Tests for video processing utilities."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from koda.utils.video import (
    MAX_FRAMES,
    calculate_frame_interval,
    cleanup_video_frames,
    extract_frames,
    get_video_duration,
    is_video_mime,
    process_video_attachment,
)


class TestIsVideoMime:
    def test_valid_mimes(self):
        assert is_video_mime("video/mp4")
        assert is_video_mime("video/quicktime")
        assert is_video_mime("video/webm")
        assert is_video_mime("video/x-msvideo")
        assert is_video_mime("video/x-matroska")
        assert is_video_mime("video/mpeg")
        assert is_video_mime("video/ogg")

    def test_invalid_mimes(self):
        assert not is_video_mime("image/png")
        assert not is_video_mime("audio/mp3")
        assert not is_video_mime("application/pdf")
        assert not is_video_mime("text/plain")
        assert not is_video_mime("")

    def test_case_insensitive(self):
        assert is_video_mime("Video/MP4")
        assert is_video_mime("VIDEO/WEBM")


class TestCalculateFrameInterval:
    def test_short_video(self):
        interval, count = calculate_frame_interval(1.0)
        assert interval == 2.0
        assert count == 3  # minimum

    def test_5s_video(self):
        interval, count = calculate_frame_interval(5.0)
        assert interval == 2.0
        assert count == 3

    def test_10s_video(self):
        interval, count = calculate_frame_interval(10.0)
        assert interval == 2.0
        assert count >= 3

    def test_30s_video(self):
        interval, count = calculate_frame_interval(30.0)
        assert interval == 5.0
        assert 3 <= count <= MAX_FRAMES

    def test_60s_video(self):
        interval, count = calculate_frame_interval(60.0)
        assert interval == 5.0
        assert 3 <= count <= MAX_FRAMES

    def test_120s_video(self):
        interval, count = calculate_frame_interval(120.0)
        assert interval == 15.0
        assert 3 <= count <= MAX_FRAMES

    def test_300s_video(self):
        interval, count = calculate_frame_interval(300.0)
        assert interval == 15.0
        assert count == MAX_FRAMES

    def test_max_cap(self):
        """Frame count never exceeds MAX_FRAMES."""
        _, count = calculate_frame_interval(300.0)
        assert count <= MAX_FRAMES
        _, count = calculate_frame_interval(600.0)
        assert count <= MAX_FRAMES


class TestGetVideoDuration:
    def test_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "42.5\n"
        with patch("koda.utils.video.subprocess.run", return_value=mock_result):
            duration = get_video_duration("/tmp/video.mp4")
        assert duration == 42.5

    def test_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        with patch("koda.utils.video.subprocess.run", return_value=mock_result):
            duration = get_video_duration("/tmp/video.mp4")
        assert duration is None

    def test_timeout(self):
        import subprocess

        with patch(
            "koda.utils.video.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffprobe", 30),
        ):
            duration = get_video_duration("/tmp/video.mp4")
        assert duration is None

    def test_not_found(self):
        with patch(
            "koda.utils.video.subprocess.run",
            side_effect=FileNotFoundError("ffprobe not found"),
        ):
            duration = get_video_duration("/tmp/video.mp4")
        assert duration is None


class TestExtractFrames:
    def test_success(self, tmp_path):
        # Create fake frame files
        prefix = str(tmp_path / "frame")
        for i in range(1, 4):
            (tmp_path / f"frame_{i:03d}.jpg").write_bytes(b"fake")

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("koda.utils.video.subprocess.run", return_value=mock_result):
            frames = extract_frames("/tmp/video.mp4", prefix, 5.0)
        assert len(frames) == 3
        assert all(f.endswith(".jpg") for f in frames)

    def test_ffmpeg_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        with patch("koda.utils.video.subprocess.run", return_value=mock_result):
            frames = extract_frames("/tmp/video.mp4", "/tmp/frame", 5.0)
        assert frames == []

    def test_ffmpeg_timeout(self):
        import subprocess

        with patch(
            "koda.utils.video.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 120),
        ):
            frames = extract_frames("/tmp/video.mp4", "/tmp/frame", 5.0)
        assert frames == []


class TestProcessVideoAttachment:
    def test_video_audio_transcription_uses_agent_runtime_defaults(self, tmp_path):
        ffmpeg_result = MagicMock()
        ffmpeg_result.returncode = 0
        ffmpeg_result.stderr = ""
        audio_path = tmp_path / "jira_video_audio_123.wav"

        def _fake_run(*args, **kwargs):
            audio_path.write_bytes(b"x" * 2000)
            return ffmpeg_result

        with (
            patch("koda.utils.video.IMAGE_TEMP_DIR", tmp_path),
            patch("koda.utils.video.subprocess.run", side_effect=_fake_run),
            patch(
                "koda.services.agent_settings.get_agent_runtime_settings",
                return_value={
                    "transcription_provider": "codex",
                    "transcription_model": "gpt-4o-transcribe",
                },
            ),
            patch("koda.utils.audio.transcribe_audio_sync", return_value="texto") as mock_transcribe,
        ):
            from koda.utils.video import _extract_and_transcribe_audio

            result = _extract_and_transcribe_audio("/tmp/video.mp4", "123")

        assert result == "texto"
        mock_transcribe.assert_called_once_with(
            str(audio_path),
            provider="codex",
            model="gpt-4o-transcribe",
        )
        assert not audio_path.exists()

    def test_no_ffmpeg(self):
        with patch("koda.utils.video.is_ffmpeg_available", return_value=False):
            frames, summary = process_video_attachment(b"data", "test.mp4", "123")
        assert frames == []
        assert "FFmpeg is not available" in summary

    def test_too_long(self, tmp_path):
        with (
            patch("koda.utils.video.is_ffmpeg_available", return_value=True),
            patch("koda.utils.video.IMAGE_TEMP_DIR", tmp_path),
            patch("koda.utils.video.get_video_duration", return_value=400.0),
        ):
            frames, summary = process_video_attachment(b"data", "test.mp4", "123")
        assert frames == []
        assert "too long" in summary

    def test_success(self, tmp_path):
        fake_frames = [str(tmp_path / f"frame_{i:03d}.jpg") for i in range(1, 4)]
        for f in fake_frames:
            Path(f).write_bytes(b"fake")

        with (
            patch("koda.utils.video.is_ffmpeg_available", return_value=True),
            patch("koda.utils.video.IMAGE_TEMP_DIR", tmp_path),
            patch("koda.utils.video.get_video_duration", return_value=15.0),
            patch("koda.utils.video.extract_frames", return_value=fake_frames),
        ):
            frames, summary = process_video_attachment(b"data", "test.mp4", "123")
        assert len(frames) == 3
        assert "Extracted 3 frames" in summary
        assert "test.mp4" in summary

    def test_duration_unknown(self, tmp_path):
        with (
            patch("koda.utils.video.is_ffmpeg_available", return_value=True),
            patch("koda.utils.video.IMAGE_TEMP_DIR", tmp_path),
            patch("koda.utils.video.get_video_duration", return_value=None),
        ):
            frames, summary = process_video_attachment(b"data", "test.mp4", "123")
        assert frames == []
        assert "Could not determine" in summary

    def test_extract_failure(self, tmp_path):
        with (
            patch("koda.utils.video.is_ffmpeg_available", return_value=True),
            patch("koda.utils.video.IMAGE_TEMP_DIR", tmp_path),
            patch("koda.utils.video.get_video_duration", return_value=15.0),
            patch("koda.utils.video.extract_frames", return_value=[]),
        ):
            frames, summary = process_video_attachment(b"data", "test.mp4", "123")
        assert frames == []
        assert "Failed to extract" in summary

    def test_video_source_cleaned_up(self, tmp_path):
        """Video source file is deleted even if extraction fails."""
        with (
            patch("koda.utils.video.is_ffmpeg_available", return_value=True),
            patch("koda.utils.video.IMAGE_TEMP_DIR", tmp_path),
            patch("koda.utils.video.get_video_duration", return_value=15.0),
            patch("koda.utils.video.extract_frames", return_value=[]),
        ):
            process_video_attachment(b"data", "test.mp4", "cleanup_test")
        # Video source should be deleted
        assert not (tmp_path / "jira_video_cleanup_test.mp4").exists()


class TestCleanupVideoFrames:
    def test_deletes_files(self, tmp_path):
        paths = []
        for i in range(3):
            p = tmp_path / f"frame_{i}.jpg"
            p.write_bytes(b"data")
            paths.append(str(p))

        cleanup_video_frames(paths)
        for p in paths:
            assert not Path(p).exists()

    def test_handles_missing_files(self, tmp_path):
        paths = [str(tmp_path / "nonexistent.jpg")]
        cleanup_video_frames(paths)  # Should not raise

    def test_empty_list(self):
        cleanup_video_frames([])  # Should not raise
