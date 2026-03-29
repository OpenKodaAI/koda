"""Additional operational coverage for command handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from koda.handlers.commands import (
    cmd_dbenv,
    cmd_digest,
    cmd_export,
    cmd_featuremodel,
    cmd_forget,
    cmd_git,
    cmd_help,
    cmd_history,
    cmd_jobs,
    cmd_model,
    cmd_ping,
    cmd_provider,
    cmd_retry,
    cmd_schedule,
    cmd_setdir,
    cmd_shell,
    cmd_task,
    cmd_tasks,
    cmd_voice,
    init_user_data,
)


def _runtime_settings(
    *,
    provider: str = "codex",
    model: str = "gpt-5.4",
    function_id: str = "general",
) -> dict[str, object]:
    functional_defaults = {
        "general": {"provider_id": provider, "model_id": model},
        function_id: {"provider_id": provider, "model_id": model},
    }
    selectable = {
        "general": [{"provider_id": provider, "model_id": model, "provider_title": provider.title(), "title": model}],
        function_id: [{"provider_id": provider, "model_id": model, "provider_title": provider.title(), "title": model}],
    }
    return {
        "default_provider": provider,
        "general_model": model,
        "default_models_by_provider": {provider: model},
        "functional_defaults": functional_defaults,
        "transcription_provider": "whispercpp",
        "transcription_model": "whisper-cpp-local",
        "audio_provider": "kokoro",
        "audio_model": "kokoro-v1",
        "tts_voice": "pf_dora",
        "tts_voice_label": "Dora",
        "tts_voice_language": "pt-br",
        "selectable_function_options": selectable,
    }


class TestCmdHelpAndSetdirCoverage:
    @pytest.mark.asyncio
    async def test_help_shows_runtime_state(self, mock_update, mock_context):
        mock_context.user_data.update(
            {
                "work_dir": "/tmp/work",
                "provider": "claude",
                "model": "claude-sonnet-4-6",
                "session_id": "sess-123",
                "auto_model": True,
            }
        )
        init_user_data(mock_context.user_data)

        await cmd_help(mock_update, mock_context)

        text = mock_update.message.reply_text.call_args.args[0]
        assert "Provider" in text
        assert "sess-123" in text

    @pytest.mark.asyncio
    async def test_setdir_sets_existing_directory(self, mock_update, mock_context, tmp_path):
        mock_context.args = [str(tmp_path)]
        init_user_data(mock_context.user_data)

        await cmd_setdir(mock_update, mock_context)

        assert mock_context.user_data["work_dir"] == str(tmp_path)
        assert "Working directory set" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_setdir_without_project_dirs_reports_configuration_gap(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)

        with patch("koda.handlers.commands.PROJECT_DIRS", []):
            await cmd_setdir(mock_update, mock_context)

        assert "No PROJECT_DIRS configured" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_setdir_without_args_shows_directory_buttons(self, mock_update, mock_context, tmp_path):
        mock_context.args = []
        init_user_data(mock_context.user_data)

        with patch("koda.handlers.commands.PROJECT_DIRS", [str(tmp_path)]):
            await cmd_setdir(mock_update, mock_context)

        reply_markup = mock_update.message.reply_text.call_args.kwargs["reply_markup"]
        assert reply_markup.inline_keyboard


class TestCmdProviderModelDbEnvCoverage:
    @pytest.mark.asyncio
    async def test_provider_with_arg_sets_provider(self, mock_update, mock_context):
        mock_context.args = ["codex"]
        init_user_data(mock_context.user_data)

        with patch(
            "koda.handlers.commands.set_agent_general_provider",
            return_value=_runtime_settings(provider="codex", model="gpt-5.4"),
        ):
            await cmd_provider(mock_update, mock_context)

        assert mock_context.user_data["provider"] == "codex"

    @pytest.mark.asyncio
    async def test_provider_with_arg_persists_agent_local_override(self, mock_update, mock_context):
        mock_context.args = ["codex"]
        init_user_data(mock_context.user_data)

        with patch(
            "koda.handlers.commands.set_agent_general_provider",
            return_value=_runtime_settings(provider="codex", model="gpt-5.4"),
        ) as mock_persist:
            await cmd_provider(mock_update, mock_context)

        mock_persist.assert_called_once_with("codex")
        assert mock_context.user_data["provider"] == "codex"
        assert mock_context.user_data["model"] == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_provider_with_brand_alias_maps_to_canonical_agent_local_provider(self, mock_update, mock_context):
        mock_context.args = ["openai"]
        init_user_data(mock_context.user_data)

        with patch(
            "koda.handlers.commands.set_agent_general_provider",
            return_value=_runtime_settings(provider="codex", model="gpt-5.4"),
        ) as mock_persist:
            await cmd_provider(mock_update, mock_context)

        mock_persist.assert_called_once_with("codex")
        assert mock_context.user_data["provider"] == "codex"
        assert mock_context.user_data["model"] == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_provider_with_arg_does_not_mutate_local_state_when_persist_fails(self, mock_update, mock_context):
        mock_context.args = ["codex"]
        init_user_data(mock_context.user_data)
        original_provider = mock_context.user_data["provider"]
        original_model = mock_context.user_data["model"]

        with patch("koda.handlers.commands.set_agent_general_provider", side_effect=ValueError("boom")):
            await cmd_provider(mock_update, mock_context)

        assert mock_context.user_data["provider"] == original_provider
        assert mock_context.user_data["model"] == original_model

    @pytest.mark.asyncio
    async def test_provider_without_args_shows_keyboard(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)

        await cmd_provider(mock_update, mock_context)

        assert mock_update.message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard

    @pytest.mark.asyncio
    async def test_model_auto_enables_router(self, mock_update, mock_context):
        mock_context.args = ["auto"]
        init_user_data(mock_context.user_data)

        await cmd_model(mock_update, mock_context)

        assert mock_context.user_data["auto_model"] is True

    @pytest.mark.asyncio
    async def test_model_manual_disables_router(self, mock_update, mock_context):
        mock_context.args = ["manual"]
        mock_context.user_data["auto_model"] = True
        init_user_data(mock_context.user_data)

        await cmd_model(mock_update, mock_context)

        assert mock_context.user_data["auto_model"] is False

    @pytest.mark.asyncio
    async def test_model_invalid_name_shows_error(self, mock_update, mock_context):
        mock_context.args = ["not-a-real-model"]
        init_user_data(mock_context.user_data)

        await cmd_model(mock_update, mock_context)

        assert "Unknown model" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_model_without_args_shows_keyboard(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)

        await cmd_model(mock_update, mock_context)

        reply_markup = mock_update.message.reply_text.call_args.kwargs["reply_markup"]
        assert reply_markup.inline_keyboard

    @pytest.mark.asyncio
    async def test_model_with_arg_persists_agent_local_override(self, mock_update, mock_context):
        mock_context.user_data["provider"] = "codex"
        mock_context.args = ["gpt-5.4"]
        init_user_data(mock_context.user_data)
        mock_context.user_data["available_models_by_provider"] = {"codex": ["gpt-5.4", "o3"]}

        with patch(
            "koda.handlers.commands.set_agent_general_model",
            return_value=_runtime_settings(provider="codex", model="gpt-5.4"),
        ) as mock_persist:
            await cmd_model(mock_update, mock_context)

        mock_persist.assert_called_once_with("codex", "gpt-5.4")
        assert mock_context.user_data["model"] == "gpt-5.4"

    @pytest.mark.asyncio
    async def test_model_with_arg_does_not_mutate_local_state_when_persist_fails(self, mock_update, mock_context):
        mock_context.user_data["provider"] = "codex"
        mock_context.user_data["model"] = "o3"
        mock_context.args = ["gpt-5.4"]
        init_user_data(mock_context.user_data)
        mock_context.user_data["available_models_by_provider"] = {"codex": ["gpt-5.4", "o3"]}

        with patch("koda.handlers.commands.set_agent_general_model", side_effect=ValueError("boom")):
            await cmd_model(mock_update, mock_context)

        assert mock_context.user_data["model"] == "o3"

    @pytest.mark.asyncio
    async def test_featuremodel_shows_function_keyboard(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        settings = _runtime_settings(provider="codex", model="gpt-5.4", function_id="image")
        settings["selectable_function_options"]["image"] = [
            {
                "provider_id": "codex",
                "model_id": "gpt-image-1.5",
                "provider_title": "OpenAI",
                "title": "GPT Image 1.5",
            }
        ]
        settings["functional_defaults"]["image"] = {"provider_id": "codex", "model_id": "gpt-image-1.5"}
        with patch("koda.handlers.commands.get_agent_runtime_settings", return_value=settings):
            await cmd_featuremodel(mock_update, mock_context)

        reply_markup = mock_update.message.reply_text.call_args.kwargs["reply_markup"]
        callbacks = [row[0].callback_data for row in reply_markup.inline_keyboard]
        assert "fmodelf:general" in callbacks
        assert "fmodelf:image" in callbacks

    @pytest.mark.asyncio
    async def test_featuremodel_list_and_text_setter_paths(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        settings = _runtime_settings(provider="codex", model="gpt-5.4", function_id="image")
        settings["selectable_function_options"]["image"] = [
            {
                "provider_id": "codex",
                "model_id": "gpt-image-1.5",
                "provider_title": "OpenAI",
                "title": "GPT Image 1.5",
            }
        ]
        settings["functional_defaults"]["image"] = {"provider_id": "codex", "model_id": "gpt-image-1.5"}

        mock_context.args = ["list"]
        with patch("koda.handlers.commands.get_agent_runtime_settings", return_value=settings):
            await cmd_featuremodel(mock_update, mock_context)
        assert "Modelos padrao por funcionalidade deste AGENT" in mock_update.message.reply_text.call_args.args[0]

        mock_context.args = ["image"]
        with patch("koda.handlers.commands.get_agent_runtime_settings", return_value=settings):
            await cmd_featuremodel(mock_update, mock_context)
        assert "GPT Image 1.5" in mock_update.message.reply_text.call_args.args[0]

        mock_context.args = ["image", "codex", "gpt-image-1.5"]
        with (
            patch("koda.handlers.commands.get_agent_runtime_settings", return_value=settings),
            patch(
                "koda.handlers.commands.set_agent_functional_default",
                return_value=settings,
            ) as mock_set,
        ):
            await cmd_featuremodel(mock_update, mock_context)
        mock_set.assert_called_once_with("image", "codex", "gpt-image-1.5")
        assert "Modelo padrao do AGENT atualizado" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_featuremodel_text_setter_accepts_non_llm_function_provider_ids(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        settings = _runtime_settings(provider="codex", model="gpt-5.4", function_id="audio")
        settings["selectable_function_options"]["audio"] = [
            {
                "provider_id": "kokoro",
                "model_id": "kokoro-v1",
                "provider_title": "Kokoro",
                "title": "Kokoro v1",
            }
        ]
        settings["functional_defaults"]["audio"] = {"provider_id": "kokoro", "model_id": "kokoro-v1"}

        mock_context.args = ["audio", "kokoro", "kokoro-v1"]
        with (
            patch("koda.handlers.commands.get_agent_runtime_settings", return_value=settings),
            patch(
                "koda.handlers.commands.set_agent_functional_default",
                return_value=settings,
            ) as mock_set,
        ):
            await cmd_featuremodel(mock_update, mock_context)

        mock_set.assert_called_once_with("audio", "kokoro", "kokoro-v1")

    @pytest.mark.asyncio
    async def test_featuremodel_accepts_portuguese_function_aliases(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        settings = _runtime_settings(provider="codex", model="gpt-5.4", function_id="image")
        settings["selectable_function_options"]["image"] = [
            {
                "provider_id": "codex",
                "model_id": "gpt-image-1.5",
                "provider_title": "OpenAI",
                "title": "GPT Image 1.5",
            }
        ]

        mock_context.args = ["imagem", "codex", "gpt-image-1.5"]
        with (
            patch("koda.handlers.commands.get_agent_runtime_settings", return_value=settings),
            patch(
                "koda.handlers.commands.set_agent_functional_default",
                return_value=settings,
            ) as mock_set,
        ):
            await cmd_featuremodel(mock_update, mock_context)

        mock_set.assert_called_once_with("image", "codex", "gpt-image-1.5")

    @pytest.mark.asyncio
    async def test_featuremodel_text_setter_accepts_brand_and_provider_aliases(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        settings = _runtime_settings(provider="codex", model="gpt-5.4", function_id="video")
        settings["selectable_function_options"]["video"] = [
            {
                "provider_id": "codex",
                "model_id": "sora-2",
                "provider_title": "OpenAI",
                "title": "Sora 2",
            }
        ]
        settings["selectable_function_options"]["transcription"] = [
            {
                "provider_id": "whispercpp",
                "model_id": "whisper-cpp-local",
                "provider_title": "Whisper CPP",
                "title": "Whisper CPP Local",
            }
        ]

        mock_context.args = ["video", "sora", "sora-2"]
        with (
            patch("koda.handlers.commands.get_agent_runtime_settings", return_value=settings),
            patch(
                "koda.handlers.commands.set_agent_functional_default",
                return_value=settings,
            ) as mock_set_video,
        ):
            await cmd_featuremodel(mock_update, mock_context)

        mock_set_video.assert_called_once_with("video", "codex", "sora-2")

        mock_context.args = ["transcricao", "whisper", "whisper-cpp-local"]
        with (
            patch("koda.handlers.commands.get_agent_runtime_settings", return_value=settings),
            patch(
                "koda.handlers.commands.set_agent_functional_default",
                return_value=settings,
            ) as mock_set_transcription,
        ):
            await cmd_featuremodel(mock_update, mock_context)

        mock_set_transcription.assert_called_once_with("transcription", "whispercpp", "whisper-cpp-local")

    @pytest.mark.asyncio
    async def test_voice_lists_dynamic_kokoro_voices(self, mock_update, mock_context):
        mock_context.args = ["voices"]
        init_user_data(mock_context.user_data)

        with patch(
            "koda.services.kokoro_manager.list_kokoro_voices",
            return_value=[
                {
                    "voice_id": "bf_alice",
                    "name": "Alice",
                    "language_id": "en-gb",
                    "language_label": "British English",
                    "downloaded": False,
                },
                {
                    "voice_id": "pm_alex",
                    "name": "Alex",
                    "language_id": "pt-br",
                    "language_label": "Brazilian Portuguese",
                    "downloaded": True,
                },
            ],
        ):
            await cmd_voice(mock_update, mock_context)

        text = mock_update.message.reply_text.call_args.args[0]
        assert "bf_alice" in text
        assert "British English" in text
        assert "⬇" in text

    @pytest.mark.asyncio
    async def test_voice_accepts_dynamic_kokoro_voice_id(self, mock_update, mock_context):
        mock_context.args = ["bf_alice"]
        init_user_data(mock_context.user_data)

        with (
            patch(
                "koda.services.kokoro_manager.kokoro_voice_metadata",
                return_value={
                    "voice_id": "bf_alice",
                    "name": "Alice",
                    "language_id": "en-gb",
                },
            ),
            patch(
                "koda.handlers.commands.set_agent_voice_default",
                return_value={
                    **_runtime_settings(provider="codex", model="gpt-5.4"),
                    "tts_voice": "bf_alice",
                    "tts_voice_label": "Alice",
                    "tts_voice_language": "en-gb",
                },
            ) as mock_persist,
        ):
            await cmd_voice(mock_update, mock_context)

        mock_persist.assert_called_once_with("bf_alice", voice_label="Alice", voice_language="en-gb")
        assert mock_context.user_data["tts_voice"] == "bf_alice"

    @pytest.mark.asyncio
    async def test_voice_does_not_mutate_local_state_when_persist_fails(self, mock_update, mock_context):
        mock_context.args = ["brian"]
        init_user_data(mock_context.user_data)
        original_voice = mock_context.user_data["tts_voice"]

        with patch("koda.handlers.commands.set_agent_voice_default", side_effect=ValueError("boom")):
            await cmd_voice(mock_update, mock_context)

        assert mock_context.user_data["tts_voice"] == original_voice

    @pytest.mark.asyncio
    async def test_dbenv_unconfigured_reports_absence(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)

        with (
            patch("koda.config.POSTGRES_ENABLED", False),
            patch(
                "koda.services.db_manager.DBManager.available_envs",
                new_callable=PropertyMock,
                return_value=["prod"],
            ),
        ):
            await cmd_dbenv(mock_update, mock_context)

        assert "not configured" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_dbenv_invalid_env_shows_error(self, mock_update, mock_context):
        mock_context.args = ["qa"]
        init_user_data(mock_context.user_data)

        with (
            patch("koda.config.POSTGRES_ENABLED", True),
            patch(
                "koda.services.db_manager.DBManager.available_envs",
                new_callable=PropertyMock,
                return_value=["prod", "dev"],
            ),
        ):
            await cmd_dbenv(mock_update, mock_context)

        assert "Unknown env" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_dbenv_sets_selected_env(self, mock_update, mock_context):
        mock_context.args = ["dev"]
        init_user_data(mock_context.user_data)

        with (
            patch("koda.config.POSTGRES_ENABLED", True),
            patch(
                "koda.services.db_manager.DBManager.available_envs",
                new_callable=PropertyMock,
                return_value=["prod", "dev"],
            ),
        ):
            await cmd_dbenv(mock_update, mock_context)

        assert mock_context.user_data["postgres_env"] == "dev"

    @pytest.mark.asyncio
    async def test_dbenv_without_args_shows_keyboard(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)

        with (
            patch("koda.config.POSTGRES_ENABLED", True),
            patch(
                "koda.services.db_manager.DBManager.available_envs",
                new_callable=PropertyMock,
                return_value=["prod", "dev"],
            ),
        ):
            await cmd_dbenv(mock_update, mock_context)

        reply_markup = mock_update.message.reply_text.call_args.kwargs["reply_markup"]
        assert reply_markup.inline_keyboard


class TestCmdTasksTaskCoverage:
    @pytest.mark.asyncio
    async def test_tasks_empty_state(self, mock_update, mock_context):
        with (
            patch("koda.handlers.commands.get_active_tasks", return_value=[]),
            patch("koda.handlers.commands.get_user_tasks", return_value=[]),
        ):
            await cmd_tasks(mock_update, mock_context)

        assert mock_update.message.reply_text.call_args.args[0] == "No tasks."

    @pytest.mark.asyncio
    async def test_tasks_formats_active_and_db_rows(self, mock_update, mock_context):
        active = [SimpleNamespace(task_id=7, status="running", query_text="Deploy service", started_at=1.0, attempt=1)]
        db_rows = [
            (
                9,
                "completed",
                "Post-deploy verification query",
                "claude",
                "claude-sonnet-4-6",
                0.1234,
                "",
                "2026-03-18T10:00:00",
                "2026-03-18T10:01:00",
                "2026-03-18T10:02:00",
                1,
                3,
                "/tmp/work",
            )
        ]
        with (
            patch("koda.handlers.commands.get_active_tasks", return_value=active),
            patch("koda.handlers.commands.get_user_tasks", return_value=db_rows),
            patch("time.time", return_value=31.0),
        ):
            await cmd_tasks(mock_update, mock_context)

        text = mock_update.message.reply_text.call_args.args[0]
        assert "#7" in text
        assert "#9" in text

    @pytest.mark.asyncio
    async def test_task_requires_id(self, mock_update, mock_context):
        mock_context.args = []

        await cmd_task(mock_update, mock_context)

        assert "Usage: /task <id>" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_task_rejects_other_users(self, mock_update, mock_context):
        mock_context.args = ["7"]
        row = (
            7,
            999,
            111,
            "running",
            "Deploy",
            "claude",
            "claude-sonnet-4-6",
            "/tmp",
            1,
            3,
            0.0,
            "",
            "",
            "",
            "",
            "sess",
            "native",
        )
        with (
            patch("koda.handlers.commands.get_task_info", return_value=None),
            patch("koda.handlers.commands.get_task", return_value=row),
        ):
            await cmd_task(mock_update, mock_context)

        assert "not found" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_task_formats_running_details(self, mock_update, mock_context):
        mock_context.args = ["7"]
        row = (
            7,
            111,
            111,
            "running",
            "Deploy service safely",
            "claude",
            "claude-sonnet-4-6",
            "/tmp/work",
            2,
            3,
            0.25,
            "",
            "2026-03-18T10:00:00",
            "2026-03-18T10:01:00",
            None,
            "sess-1",
            "native-1",
        )
        ti = SimpleNamespace(started_at=1.0)
        with (
            patch("koda.handlers.commands.get_task_info", return_value=ti),
            patch("koda.handlers.commands.get_task", return_value=row),
            patch("time.time", return_value=75.0),
        ):
            await cmd_task(mock_update, mock_context)

        text = mock_update.message.reply_text.call_args.args[0]
        assert "Tarefa #7" in text
        assert "Provider" in text


class TestCmdRuntimeCoverage:
    @pytest.mark.asyncio
    async def test_shell_executes_allowed_command(self, mock_update, mock_context):
        mock_context.args = ["pwd"]
        init_user_data(mock_context.user_data)

        with (
            patch(
                "koda.handlers.commands.run_shell_command",
                new_callable=AsyncMock,
                return_value="/tmp",
            ) as mock_run,
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_shell(mock_update, mock_context)

        mock_run.assert_awaited_once()
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_git_rejects_disallowed_subcommand(self, mock_update, mock_context):
        mock_context.args = ["bogus"]
        init_user_data(mock_context.user_data)

        await cmd_git(mock_update, mock_context)

        assert "is not allowed" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_git_executes_allowed_subcommand(self, mock_update, mock_context):
        mock_context.args = ["status"]
        init_user_data(mock_context.user_data)

        with (
            patch(
                "koda.handlers.commands.run_shell_command",
                new_callable=AsyncMock,
                return_value="clean",
            ) as mock_run,
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_git(mock_update, mock_context)

        mock_run.assert_awaited_once()
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ping_reports_runtime_status(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.user_data["session_id"] = "sess-42"
        with (
            patch("koda.handlers.commands.agent_start_time", 0.0),
            patch("time.time", return_value=65.0),
            patch("koda.handlers.commands.get_queue_depth", return_value=3),
            patch("koda.handlers.commands.is_process_running", return_value=True),
        ):
            await cmd_ping(mock_update, mock_context)

        text = mock_update.message.reply_text.call_args.args[0]
        assert "Queue depth: 3" in text
        assert "Process running: yes" in text

    @pytest.mark.asyncio
    async def test_retry_missing_image_is_rejected(self, mock_update, mock_context, tmp_path):
        init_user_data(mock_context.user_data)
        missing = str(tmp_path / "missing.png")
        mock_context.user_data["last_query"] = {"text": "retry me", "image_paths": [missing], "artifact_bundle": None}

        await cmd_retry(mock_update, mock_context)

        assert "no longer exist" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_retry_enqueues_previous_query(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.user_data["last_query"] = {"text": "retry me", "image_paths": None, "artifact_bundle": None}

        with (
            patch("koda.handlers.commands.acquire_rate_limit", new_callable=AsyncMock, return_value=True),
            patch("koda.handlers.commands.enqueue", new_callable=AsyncMock) as mock_enqueue,
        ):
            await cmd_retry(mock_update, mock_context)

        mock_enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_without_last_query_reports_empty_state(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)

        await cmd_retry(mock_update, mock_context)

        assert "No previous query to retry." in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_retry_rate_limit_blocks_enqueue(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.user_data["last_query"] = {"text": "retry me", "image_paths": None, "artifact_bundle": None}

        with patch("koda.handlers.commands.acquire_rate_limit", new_callable=AsyncMock, return_value=False):
            await cmd_retry(mock_update, mock_context)

        assert "Rate limited" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_history_reports_empty_state(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.get_history", return_value=[]):
            await cmd_history(mock_update, mock_context)

        assert "No query history" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_history_formats_rows(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        rows = [("2026-03-18T10:00:00", "claude", "claude-sonnet-4-6", 0.1234, "Explain issue", 0)]
        with (
            patch("koda.handlers.commands.get_history", return_value=rows),
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
        ):
            await cmd_history(mock_update, mock_context)

        assert "Last 1 queries" in mock_send.call_args.args[1]

    @pytest.mark.asyncio
    async def test_history_invalid_limit_falls_back_to_default(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["oops"]
        rows = [("2026-03-18T10:00:00", "claude", "claude-sonnet-4-6", 0.1234, "Explain issue", 0)]
        with (
            patch("koda.handlers.commands.get_history", return_value=rows) as mock_history,
            patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock),
        ):
            await cmd_history(mock_update, mock_context)

        assert mock_history.call_args.args[1] == 10

    @pytest.mark.asyncio
    async def test_export_no_rows_reports_empty_state(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        with patch("koda.handlers.commands.get_full_history", return_value=[]):
            await cmd_export(mock_update, mock_context)

        assert "No query history to export." in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_export_sends_document(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        rows = [("2026-03-18T10:00:00", "claude", "claude-sonnet-4-6", 0.1, "Q", "R", "/tmp", 0)]
        with patch("koda.handlers.commands.get_full_history", return_value=rows):
            await cmd_export(mock_update, mock_context)

        mock_update.message.reply_document.assert_awaited_once()


class TestCmdSchedulingAndJobsCoverage:
    @pytest.mark.asyncio
    async def test_schedule_requires_interval_and_query(self, mock_update, mock_context):
        mock_context.args = []
        init_user_data(mock_context.user_data)

        await cmd_schedule(mock_update, mock_context)

        assert "Usage: /schedule every" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_schedule_rejects_invalid_prefix(self, mock_update, mock_context):
        mock_context.args = ["later", "2h", "check"]
        init_user_data(mock_context.user_data)

        await cmd_schedule(mock_update, mock_context)

        assert "Usage: /schedule every" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_schedule_rejects_invalid_interval(self, mock_update, mock_context):
        mock_context.args = ["every", "banana", "check", "status"]
        init_user_data(mock_context.user_data)

        with patch("koda.services.scheduler.parse_interval", return_value=None):
            await cmd_schedule(mock_update, mock_context)

        assert "Invalid interval" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_schedule_uses_scheduler_service(self, mock_update, mock_context):
        mock_context.args = ["every", "2h", "check", "status"]
        init_user_data(mock_context.user_data)

        with (
            patch("koda.services.scheduler.parse_interval", return_value=7200),
            patch(
                "koda.services.scheduler.schedule_recurring",
                new_callable=AsyncMock,
                return_value="Scheduled!",
            ) as mock_schedule,
        ):
            await cmd_schedule(mock_update, mock_context)

        mock_schedule.assert_awaited_once()
        assert mock_update.message.reply_text.call_args.args[0] == "Scheduled!"

    @pytest.mark.asyncio
    async def test_jobs_show_and_runs_paths(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        with patch("koda.services.scheduler.cancel_user_jobs", return_value=0):
            mock_context.args = ["show", "7"]
            with patch(
                "koda.services.scheduled_jobs.get_job",
                return_value={
                    "id": 7,
                    "job_type": "agent_query",
                    "trigger_type": "interval",
                    "status": "active",
                    "schedule_expr": "every 2h",
                    "timezone": "UTC",
                    "provider_preference": "claude",
                    "model_preference": "claude-sonnet-4-6",
                    "work_dir": "/tmp",
                    "next_run_at": "2026-03-18T12:00:00",
                    "last_success_at": None,
                    "last_failure_at": None,
                    "payload": {"query": "Check deploy status"},
                },
            ):
                await cmd_jobs(mock_update, mock_context)
            assert "Job #7" in mock_update.message.reply_text.call_args.args[0]

            mock_context.args = ["runs", "7"]
            with (
                patch(
                    "koda.services.scheduled_jobs.list_job_runs",
                    return_value=[
                        {
                            "id": 1,
                            "status": "done",
                            "trigger_reason": "manual",
                            "scheduled_for": "now",
                            "task_id": 42,
                            "verification_status": "verified",
                        }
                    ],
                ),
                patch("koda.handlers.commands.send_long_message", new_callable=AsyncMock) as mock_send,
            ):
                await cmd_jobs(mock_update, mock_context)
            assert "Runs for job #7" in mock_send.call_args.args[1]

    @pytest.mark.asyncio
    async def test_jobs_other_actions_and_unknown_action(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)

        action_matrix = {
            "validate": ("koda.services.scheduled_jobs.queue_validation_run", (123, "Queued validation.")),
            "activate": ("koda.services.scheduled_jobs.activate_job", (True, "Activated.")),
            "pause": ("koda.services.scheduled_jobs.pause_job", (True, "Paused.")),
            "resume": ("koda.services.scheduled_jobs.resume_job", (True, "Resumed.")),
            "delete": ("koda.services.scheduled_jobs.delete_job", (True, "Deleted.")),
            "run": ("koda.services.scheduled_jobs.run_job_now", (321, "Triggered.")),
        }
        for action, (target, result) in action_matrix.items():
            mock_context.args = [action, "7"]
            with patch(target, return_value=result):
                await cmd_jobs(mock_update, mock_context)
            assert mock_update.message.reply_text.call_args.args[0] == result[1]

        mock_context.args = ["mystery", "7"]
        await cmd_jobs(mock_update, mock_context)
        assert "Unknown action" in mock_update.message.reply_text.call_args.args[0]


class TestCmdVoiceMemoryCoverage:
    @pytest.mark.asyncio
    async def test_voice_toggle_and_list(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        await cmd_voice(mock_update, mock_context)
        assert mock_context.user_data["audio_response"] is True

        mock_context.args = ["voices"]
        await cmd_voice(mock_update, mock_context)
        assert "Available voices" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_voice_search_and_selection_paths(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)

        mock_context.args = ["search"]
        await cmd_voice(mock_update, mock_context)
        assert "Usage: /voice search" in mock_update.message.reply_text.call_args.args[0]

        mock_context.args = ["search", "brazilian"]
        voice = SimpleNamespace(name="Maria", gender="female", accent="BR", language="pt", voice_id="voice-1")
        with patch("koda.utils.tts.search_elevenlabs_voices", new_callable=AsyncMock, return_value=[voice]):
            await cmd_voice(mock_update, mock_context)
        assert "Results for" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_voice_direct_selection_and_unknown_option(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)

        mock_context.args = ["brian"]
        await cmd_voice(mock_update, mock_context)
        assert "Voice set to" in mock_update.message.reply_text.call_args.args[0]

        mock_context.args = ["mystery"]
        await cmd_voice(mock_update, mock_context)
        assert "Unknown option" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_forget_and_digest_paths(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)

        with patch("koda.memory.config.MEMORY_ENABLED", False):
            await cmd_forget(mock_update, mock_context)
        assert "Memory system is disabled" in mock_update.message.reply_text.call_args.args[0]

        with (
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.config.MEMORY_DIGEST_ENABLED", True),
            patch("koda.memory.digest_store.get_preference", return_value=None),
        ):
            mock_context.args = []
            await cmd_digest(mock_update, mock_context)
        assert "Digest não configurado" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_forget_usage_and_invalid_id_paths(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)

        with patch("koda.memory.config.MEMORY_ENABLED", True):
            mock_context.args = []
            await cmd_forget(mock_update, mock_context)
        assert "Usage: /forget" in mock_update.message.reply_text.call_args.args[0]

        mock_context.args = ["abc"]
        manager = type("Manager", (), {"store": object()})()
        with (
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.get_memory_manager", return_value=manager),
        ):
            await cmd_forget(mock_update, mock_context)
        assert "Invalid ID" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_forget_store_missing_and_success_path(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["7"]

        manager = type("Manager", (), {"store": None})()
        with (
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.get_memory_manager", return_value=manager),
        ):
            await cmd_forget(mock_update, mock_context)
        assert "not initialized" in mock_update.message.reply_text.call_args.args[0]

        store = type("Store", (), {"deactivate": AsyncMock(return_value=True)})()
        manager = type("Manager", (), {"store": store})()
        with (
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.get_memory_manager", return_value=manager),
            patch("koda.memory.recall.clear_recall_cache"),
        ):
            await cmd_forget(mock_update, mock_context)
        assert "forgotten" in mock_update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_digest_mutation_commands(self, mock_update, mock_context):
        init_user_data(mock_context.user_data)
        mock_context.args = ["on"]
        with (
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.config.MEMORY_DIGEST_ENABLED", True),
            patch("koda.memory.digest_store.get_preference", return_value=None),
            patch("koda.memory.digest_store.set_preference") as mock_set,
        ):
            await cmd_digest(mock_update, mock_context)
        mock_set.assert_called_once()

        mock_context.args = ["time", "99:00"]
        with (
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.config.MEMORY_DIGEST_ENABLED", True),
        ):
            await cmd_digest(mock_update, mock_context)
        assert "Horário inválido" in mock_update.message.reply_text.call_args.args[0]

        mock_context.args = ["now"]
        with (
            patch("koda.memory.config.MEMORY_ENABLED", True),
            patch("koda.memory.config.MEMORY_DIGEST_ENABLED", True),
            patch("koda.memory.digest.build_digest", return_value="<b>Digest</b>"),
        ):
            await cmd_digest(mock_update, mock_context)
        assert mock_update.message.reply_text.call_args.args[0] == "<b>Digest</b>"
