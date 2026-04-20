"""Entry point for koda."""

import argparse
import asyncio
import contextlib
import os
import signal
from collections.abc import Callable, Coroutine
from typing import Any, cast

from koda.logging_config import get_logger, setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Koda")
    parser.add_argument("--agent-id", type=str, default=None, help="Agent ID (AGENT_A, AGENT_B, AGENT_C)")
    args = parser.parse_args()

    if args.agent_id:
        os.environ["AGENT_ID"] = args.agent_id.upper()

    agent_id = (args.agent_id or os.environ.get("AGENT_ID") or "").upper() or None
    if agent_id:
        from koda.control_plane.bootstrap import apply_runtime_env_from_control_plane

        apply_runtime_env_from_control_plane(agent_id)

    from koda.logging_config import ctx_agent_id

    ctx_agent_id.set(agent_id)

    # ALL koda imports go here, AFTER AGENT_ID is set in env
    from telegram.ext import (
        Application,
        CallbackContext,
        CallbackQueryHandler,
        CommandHandler,
        ExtBot,
        MessageHandler,
        filters,
    )

    from koda.config import (
        AGENT_NAME,
        AGENT_TOKEN,
        ALLOWED_USER_IDS,
        BROWSER_FEATURES_ENABLED,
        IMAGE_TEMP_DIR,
        POSTGRES_ENABLED,
        STATE_BACKEND,
    )
    from koda.handlers.atlassian import cmd_confluence, cmd_jboard, cmd_jira, cmd_jissue, cmd_jsprint
    from koda.handlers.automation import cmd_cron, cmd_curl, cmd_fetch, cmd_http, cmd_search
    from koda.handlers.browser import cmd_browse, cmd_click, cmd_js, cmd_screenshot, cmd_type
    from koda.handlers.callbacks import (
        callback_agent_cmd_approval,
        callback_approval,
        callback_bookmark,
        callback_dbenv,
        callback_feature_model_function,
        callback_feature_model_home,
        callback_feature_model_model,
        callback_feature_model_provider,
        callback_feedback,
        callback_link_analysis,
        callback_memory_forget,
        callback_mode,
        callback_model,
        callback_provider,
        callback_setdir,
        callback_settings_featuremodel,
        callback_settings_home,
        callback_settings_mode,
        callback_settings_model,
        callback_settings_newsession,
        callback_settings_provider,
        callback_settings_voice,
        callback_supervised,
        callback_voice_elevenlabs,
    )
    from koda.handlers.commands import (
        cmd_bookmarks,
        cmd_cancel,
        cmd_cost,
        cmd_dbenv,
        cmd_delbookmark,
        cmd_digest,
        cmd_dlq,
        cmd_export,
        cmd_featuremodel,
        cmd_file,
        cmd_forget,
        cmd_git,
        cmd_help,
        cmd_history,
        cmd_jobs,
        cmd_knowledge,
        cmd_ls,
        cmd_memory,
        cmd_mode,
        cmd_model,
        cmd_name,
        cmd_napkin,
        cmd_newsession,
        cmd_ping,
        cmd_provider,
        cmd_remind,
        cmd_resetcost,
        cmd_retry,
        cmd_schedule,
        cmd_session,
        cmd_sessions,
        cmd_setdir,
        cmd_settings,
        cmd_shell,
        cmd_skill,
        cmd_start,
        cmd_system,
        cmd_task,
        cmd_tasks,
        cmd_template,
        cmd_templates,
        cmd_voice,
    )
    from koda.handlers.devops import cmd_docker, cmd_gh, cmd_glab
    from koda.handlers.fileops import cmd_cat, cmd_edit, cmd_mkdir, cmd_rm, cmd_write
    from koda.handlers.google_workspace import cmd_gcal, cmd_gdrive, cmd_gmail, cmd_gsheets, cmd_gws
    from koda.handlers.messages import (
        handle_audio,
        handle_document,
        handle_message,
        handle_photo,
        handle_voice,
    )
    from koda.handlers.packages import cmd_npm, cmd_pip
    from koda.services.health import start_health_server, stop_health_server
    from koda.services.queue_manager import active_processes

    log = get_logger(__name__)

    from koda.config import LOG_FORMAT

    setup_logging(json_output=(LOG_FORMAT == "json"))

    if not AGENT_TOKEN.strip():
        raise RuntimeError(
            "AGENT_TOKEN is not configured for this agent runtime. "
            "Complete setup in the control-plane onboarding first."
        )
    if not ALLOWED_USER_IDS:
        log.warning(
            "allowed_user_ids_empty",
            msg="ALLOWED_USER_IDS is not configured — agent will reject all messages until allowed user IDs are set "
            "in the channel settings.",
        )

    IMAGE_TEMP_DIR.mkdir(exist_ok=True)

    # Reset any asyncpg pools that were created on transient event loops
    # during module import / bootstrap. The Telegram Application.run_polling()
    # will start the real event loop, and the bridge thread will create fresh
    # pool connections bound to its own persistent loop.
    try:
        from koda.knowledge.v2 import common as _k2c

        _k2c._SHARED_POSTGRES_BACKENDS.clear()
    except Exception:
        pass
    try:
        import koda.state_primary as _sp

        _sp._BRIDGE_LOOP = None
        _sp._BRIDGE_THREAD = None
    except Exception:
        pass

    builder = Application.builder().token(AGENT_TOKEN)
    log.info("telegram_runtime_stateless_bootstrap", state_backend=STATE_BACKEND)

    app = builder.build()

    from telegram import Update as TelegramUpdate

    HandlerCallback = Callable[
        [TelegramUpdate, CallbackContext[ExtBot[None], dict[Any, Any], dict[Any, Any], dict[Any, Any]]],
        Coroutine[Any, Any, Any],
    ]

    def _as_handler(callback: Callable[..., Coroutine[Any, Any, Any]]) -> HandlerCallback:
        return cast(HandlerCallback, callback)

    async def error_handler(update: object, context: Any) -> None:
        """Log errors and notify user."""
        from telegram import Update

        log.error("unhandled_error", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("An error occurred processing your request. Please try again.")

    app.add_error_handler(error_handler)

    # Commands
    app.add_handler(CommandHandler("start", _as_handler(cmd_start)))
    app.add_handler(CommandHandler("help", _as_handler(cmd_help)))
    app.add_handler(CommandHandler("settings", _as_handler(cmd_settings)))
    app.add_handler(CommandHandler("newsession", _as_handler(cmd_newsession)))
    app.add_handler(CommandHandler("setdir", _as_handler(cmd_setdir)))
    app.add_handler(CommandHandler("cost", _as_handler(cmd_cost)))
    app.add_handler(CommandHandler("provider", _as_handler(cmd_provider)))
    app.add_handler(CommandHandler("model", _as_handler(cmd_model)))
    app.add_handler(CommandHandler("featuremodel", _as_handler(cmd_featuremodel)))
    app.add_handler(CommandHandler("mode", _as_handler(cmd_mode)))
    app.add_handler(CommandHandler("cancel", _as_handler(cmd_cancel)))
    app.add_handler(CommandHandler("tasks", _as_handler(cmd_tasks)))
    app.add_handler(CommandHandler("task", _as_handler(cmd_task)))
    app.add_handler(CommandHandler("system", _as_handler(cmd_system)))
    app.add_handler(CommandHandler("shell", _as_handler(cmd_shell)))
    app.add_handler(CommandHandler("git", _as_handler(cmd_git)))
    app.add_handler(CommandHandler("ping", _as_handler(cmd_ping)))
    app.add_handler(CommandHandler("resetcost", _as_handler(cmd_resetcost)))
    app.add_handler(CommandHandler("retry", _as_handler(cmd_retry)))
    app.add_handler(CommandHandler("history", _as_handler(cmd_history)))
    app.add_handler(CommandHandler("export", _as_handler(cmd_export)))

    # File commands
    app.add_handler(CommandHandler("file", _as_handler(cmd_file)))
    app.add_handler(CommandHandler("ls", _as_handler(cmd_ls)))
    app.add_handler(CommandHandler("cat", _as_handler(cmd_cat)))
    app.add_handler(CommandHandler("write", _as_handler(cmd_write)))
    app.add_handler(CommandHandler("edit", _as_handler(cmd_edit)))
    app.add_handler(CommandHandler("rm", _as_handler(cmd_rm)))
    app.add_handler(CommandHandler("mkdir", _as_handler(cmd_mkdir)))

    # Template commands
    app.add_handler(CommandHandler("templates", _as_handler(cmd_templates)))
    app.add_handler(CommandHandler("template", _as_handler(cmd_template)))

    # Skill commands
    app.add_handler(CommandHandler("skill", _as_handler(cmd_skill)))
    app.add_handler(CommandHandler("skills", _as_handler(cmd_templates)))

    # Bookmark commands
    app.add_handler(CommandHandler("bookmarks", _as_handler(cmd_bookmarks)))
    app.add_handler(CommandHandler("delbookmark", _as_handler(cmd_delbookmark)))

    # Session commands
    app.add_handler(CommandHandler("sessions", _as_handler(cmd_sessions)))
    app.add_handler(CommandHandler("session", _as_handler(cmd_session)))
    app.add_handler(CommandHandler("name", _as_handler(cmd_name)))

    # Scheduling commands
    app.add_handler(CommandHandler("remind", _as_handler(cmd_remind)))
    app.add_handler(CommandHandler("schedule", _as_handler(cmd_schedule)))
    app.add_handler(CommandHandler("jobs", _as_handler(cmd_jobs)))

    # Voice/TTS commands
    app.add_handler(CommandHandler("voice", _as_handler(cmd_voice)))

    # Memory commands
    app.add_handler(CommandHandler("memory", _as_handler(cmd_memory)))
    app.add_handler(CommandHandler("knowledge", _as_handler(cmd_knowledge)))
    app.add_handler(CommandHandler("napkin", _as_handler(cmd_napkin)))
    app.add_handler(CommandHandler("forget", _as_handler(cmd_forget)))
    app.add_handler(CommandHandler("digest", _as_handler(cmd_digest)))

    # DevOps commands
    app.add_handler(CommandHandler("gh", _as_handler(cmd_gh)))
    app.add_handler(CommandHandler("glab", _as_handler(cmd_glab)))
    app.add_handler(CommandHandler("docker", _as_handler(cmd_docker)))

    # Google Workspace commands
    app.add_handler(CommandHandler("gws", _as_handler(cmd_gws)))
    app.add_handler(CommandHandler("gmail", _as_handler(cmd_gmail)))
    app.add_handler(CommandHandler("gcal", _as_handler(cmd_gcal)))
    app.add_handler(CommandHandler("gdrive", _as_handler(cmd_gdrive)))
    app.add_handler(CommandHandler("gsheets", _as_handler(cmd_gsheets)))

    # Atlassian commands
    app.add_handler(CommandHandler("jira", _as_handler(cmd_jira)))
    app.add_handler(CommandHandler("jissue", _as_handler(cmd_jissue)))
    app.add_handler(CommandHandler("jboard", _as_handler(cmd_jboard)))
    app.add_handler(CommandHandler("jsprint", _as_handler(cmd_jsprint)))
    app.add_handler(CommandHandler("confluence", _as_handler(cmd_confluence)))

    # Package manager commands
    app.add_handler(CommandHandler("pip", _as_handler(cmd_pip)))
    app.add_handler(CommandHandler("npm", _as_handler(cmd_npm)))

    # Database commands
    app.add_handler(CommandHandler("dbenv", _as_handler(cmd_dbenv)))
    app.add_handler(CommandHandler("dlq", _as_handler(cmd_dlq)))

    # Automation commands
    app.add_handler(CommandHandler("cron", _as_handler(cmd_cron)))
    app.add_handler(CommandHandler("search", _as_handler(cmd_search)))
    app.add_handler(CommandHandler("fetch", _as_handler(cmd_fetch)))
    app.add_handler(CommandHandler("http", _as_handler(cmd_http)))
    app.add_handler(CommandHandler("curl", _as_handler(cmd_curl)))

    # Browser commands
    app.add_handler(CommandHandler("browse", _as_handler(cmd_browse)))
    app.add_handler(CommandHandler("click", _as_handler(cmd_click)))
    app.add_handler(CommandHandler("type", _as_handler(cmd_type)))
    app.add_handler(CommandHandler("screenshot", _as_handler(cmd_screenshot)))
    app.add_handler(CommandHandler("js", _as_handler(cmd_js)))

    # Callback queries
    app.add_handler(CallbackQueryHandler(_as_handler(callback_approval), pattern=r"^approve:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_agent_cmd_approval), pattern=r"^acmd:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_setdir), pattern=r"^setdir:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_provider), pattern=r"^provider:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_model), pattern=r"^model:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_settings_home), pattern=r"^settings:home$|^settings$"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_settings_provider), pattern=r"^settings:provider$"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_settings_model), pattern=r"^settings:model$"))
    app.add_handler(
        CallbackQueryHandler(_as_handler(callback_settings_featuremodel), pattern=r"^settings:featuremodel$")
    )
    app.add_handler(CallbackQueryHandler(_as_handler(callback_settings_mode), pattern=r"^settings:mode$"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_settings_voice), pattern=r"^settings:voice$"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_settings_newsession), pattern=r"^settings:newsession$"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_feature_model_home), pattern=r"^fmodelhome$"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_feature_model_function), pattern=r"^fmodelf:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_feature_model_provider), pattern=r"^fmodelp:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_feature_model_model), pattern=r"^fmodelm:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_bookmark), pattern=r"^bookmark:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_feedback), pattern=r"^feedback:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_mode), pattern=r"^mode:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_supervised), pattern=r"^supervised:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_voice_elevenlabs), pattern=r"^voiceel:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_dbenv), pattern=r"^dbenv:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_link_analysis), pattern=r"^link:"))
    app.add_handler(CallbackQueryHandler(_as_handler(callback_memory_forget), pattern=r"^memory_forget:"))

    # Photo and image document handlers
    app.add_handler(MessageHandler(filters.PHOTO, _as_handler(handle_photo)))
    app.add_handler(MessageHandler(filters.Document.IMAGE, _as_handler(handle_photo)))

    # Non-image document handler
    app.add_handler(
        MessageHandler(
            filters.Document.ALL & ~filters.Document.IMAGE,
            _as_handler(handle_document),
        )
    )

    # Voice and audio handlers
    app.add_handler(MessageHandler(filters.VOICE, _as_handler(handle_voice)))
    app.add_handler(MessageHandler(filters.AUDIO, _as_handler(handle_audio)))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _as_handler(handle_message)))

    # Graceful shutdown
    async def _shutdown_cleanup(app: Application) -> None:
        log.info("shutdown_start")

        # Notify active users and wait for workers to finish
        from koda.services.queue_manager import initiate_shutdown

        await initiate_shutdown(app.bot)
        from koda.services.scheduled_jobs import stop_scheduler_dispatcher

        await stop_scheduler_dispatcher()
        try:
            from koda.services.health import set_runtime_startup_state

            set_runtime_startup_state("stopping")
        except Exception:
            log.exception("startup_state_stopping_publish_error")

        await stop_health_server()

        try:
            from koda.services.lifecycle_supervisor import get_background_loop_supervisor

            await get_background_loop_supervisor().stop()
        except Exception:
            log.exception("background_loop_supervisor_stop_error")

        try:
            from koda.services.runtime import get_runtime_controller

            await get_runtime_controller().stop()
        except Exception:
            log.exception("runtime_stop_error")

        try:
            from koda.knowledge.runtime_supervisor import get_knowledge_runtime_supervisor

            await get_knowledge_runtime_supervisor(agent_id).close()
        except Exception:
            log.exception("knowledge_runtime_supervisor_stop_error")

        # Close shared HTTP client session
        try:
            from koda.services.http_client import close_session

            await close_session()
        except Exception:
            log.exception("http_session_close_error")

        # Stop database pool if running
        if POSTGRES_ENABLED:
            from koda.services.db_manager import db_manager

            await db_manager.stop()

        # Stop browser if running
        if BROWSER_FEATURES_ENABLED:
            from koda.services.browser_manager import browser_manager

            await browser_manager.stop()

        for _tid, proc in list(active_processes.items()):
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.send_signal(signal.SIGTERM)
        await asyncio.sleep(5)
        for _tid, proc in list(active_processes.items()):
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
        active_processes.clear()
        from koda.services.audit import emit_task_lifecycle

        emit_task_lifecycle("system.agent_shutdown")
        log.info("shutdown_complete")

    app.post_shutdown = _shutdown_cleanup

    # Start health server and restore cron jobs
    async def _post_init(app: Application) -> None:
        from telegram import BotCommand

        from koda.config import RUNBOOK_GOVERNANCE_ENABLED
        from koda.knowledge.config import KNOWLEDGE_ENABLED
        from koda.memory.config import (
            MEMORY_DIGEST_ENABLED,
            MEMORY_EMBEDDING_REPAIR_ENABLED,
            MEMORY_ENABLED,
            MEMORY_MAINTENANCE_ENABLED,
        )
        from koda.services.cache_config import CACHE_ENABLED, SCRIPT_LIBRARY_ENABLED
        from koda.services.health import set_runtime_startup_state
        from koda.services.lifecycle_supervisor import get_background_loop_supervisor

        expected_background_loops = {"temp_cleanup", "approval_cleanup", "db_maintenance"}
        if MEMORY_ENABLED and MEMORY_MAINTENANCE_ENABLED:
            expected_background_loops.add("memory_maintenance")
        if MEMORY_ENABLED and MEMORY_EMBEDDING_REPAIR_ENABLED:
            expected_background_loops.add("memory_embedding_repair")
        if MEMORY_ENABLED and MEMORY_DIGEST_ENABLED:
            expected_background_loops.add("memory_digest")
        if KNOWLEDGE_ENABLED and RUNBOOK_GOVERNANCE_ENABLED:
            expected_background_loops.add("runbook_governance")
        if CACHE_ENABLED or SCRIPT_LIBRARY_ENABLED:
            expected_background_loops.add("cache_maintenance")
        set_runtime_startup_state(
            "bootstrapping",
            expected_background_loops=expected_background_loops,
        )

        commands = [
            BotCommand("start", "Iniciar"),
            BotCommand("help", "Ajuda curta"),
            BotCommand("settings", "Ajustes deste AGENT"),
            BotCommand("newsession", "Nova sessao"),
            BotCommand("sessions", "Listar sessoes"),
            BotCommand("voice", "Vozes e TTS"),
            BotCommand("tasks", "Tarefas em andamento"),
            BotCommand("cancel", "Cancelar execucao"),
        ]
        with contextlib.suppress(Exception):
            await app.bot.set_my_commands(commands)

        loop_supervisor = get_background_loop_supervisor()
        critical_startup_issues: list[str] = []
        noncritical_startup_issues: list[str] = []

        try:
            from koda.services.queue_manager import recover_pending_tasks
            from koda.services.runtime import get_runtime_controller

            await get_runtime_controller().start(app)
            recovery_summary = await recover_pending_tasks(app)
            if any(recovery_summary.values()):
                log.info("queue_recovery_completed", **recovery_summary)
        except Exception:
            critical_startup_issues.append("runtime_start_error")
            log.exception("runtime_start_error")

        try:
            await start_health_server()
        except Exception:
            set_runtime_startup_state(
                "failed",
                details={"critical_issues": ["health_server_start_error"]},
                expected_background_loops=expected_background_loops,
            )
            raise

        from koda.services.scheduled_jobs import start_scheduler_dispatcher

        try:
            await start_scheduler_dispatcher(app)
        except Exception:
            critical_startup_issues.append("scheduler_dispatcher_start_error")
            set_runtime_startup_state(
                "failed",
                details={"critical_issues": list(critical_startup_issues)},
                expected_background_loops=expected_background_loops,
            )
            raise

        # Initialize memory system
        memory_store = None
        try:
            if MEMORY_ENABLED:
                from koda.memory import get_memory_manager

                mm = get_memory_manager()
                await mm.initialize()
                memory_store = mm.store
                log.info("memory_system_initialized")

                # Start maintenance loop
                from koda.memory.config import MEMORY_MAINTENANCE_ENABLED

                if MEMORY_MAINTENANCE_ENABLED and mm.store:
                    from koda.memory.maintenance_scheduler import start_maintenance_loop

                    memory_store_for_maintenance = mm.store
                    await loop_supervisor.start_loop(
                        "memory_maintenance",
                        lambda: start_maintenance_loop(memory_store_for_maintenance),
                    )

                from koda.memory.config import MEMORY_EMBEDDING_REPAIR_ENABLED

                if MEMORY_EMBEDDING_REPAIR_ENABLED and mm.store:
                    from koda.memory.embedding_scheduler import start_embedding_repair_loop

                    memory_store_for_repair = mm.store
                    await loop_supervisor.start_loop(
                        "memory_embedding_repair",
                        lambda: start_embedding_repair_loop(memory_store_for_repair),
                    )

                # Start digest loop
                from koda.memory.config import MEMORY_DIGEST_ENABLED

                if MEMORY_DIGEST_ENABLED:
                    from koda.memory.digest_scheduler import start_digest_loop

                    await loop_supervisor.start_loop(
                        "memory_digest",
                        lambda: start_digest_loop(app.bot),
                    )
        except Exception:
            noncritical_startup_issues.append("memory_init_error")
            log.exception("memory_init_error")

        # Initialize sourced knowledge retrieval
        try:
            if KNOWLEDGE_ENABLED:
                from koda.knowledge import get_knowledge_manager

                km = get_knowledge_manager()
                await km.initialize(memory_store=memory_store)
                from koda.knowledge.runtime_supervisor import get_knowledge_runtime_supervisor

                await get_knowledge_runtime_supervisor(agent_id).start()
                log.info("knowledge_system_initialized")
                if RUNBOOK_GOVERNANCE_ENABLED:
                    from koda.knowledge.governance_scheduler import start_runbook_governance_loop

                    await loop_supervisor.start_loop(
                        "runbook_governance",
                        start_runbook_governance_loop,
                    )
        except Exception:
            noncritical_startup_issues.append("knowledge_init_error")
            log.exception("knowledge_init_error")

        # Initialize cache and script library systems
        try:
            if CACHE_ENABLED:
                from koda.services.cache_manager import get_cache_manager

                cm = get_cache_manager()
                await cm.initialize(memory_store=memory_store)
                log.info("cache_system_initialized")

            if SCRIPT_LIBRARY_ENABLED:
                from koda.services.script_manager import get_script_manager

                sm = get_script_manager()
                await sm.initialize(memory_store=memory_store)
                log.info("script_library_initialized")

            if CACHE_ENABLED or SCRIPT_LIBRARY_ENABLED:
                from koda.services.cache_maintenance import start_cache_maintenance_loop

                await loop_supervisor.start_loop(
                    "cache_maintenance",
                    start_cache_maintenance_loop,
                )
        except Exception:
            noncritical_startup_issues.append("cache_script_init_error")
            log.exception("cache_script_init_error")

        # --- MCP Bridge Bootstrap ---
        from koda.config import MCP_ENABLED

        if MCP_ENABLED:
            try:
                from koda.services.mcp_bootstrap import bootstrap_mcp_for_agent

                _mcp_agent_id = os.environ.get("AGENT_ID", "")
                if _mcp_agent_id:
                    _mcp_result = await bootstrap_mcp_for_agent(_mcp_agent_id)
                    if _mcp_result.get("errors"):
                        for _err in _mcp_result["errors"]:
                            noncritical_startup_issues.append(f"MCP: {_err}")
            except Exception as _mcp_exc:
                noncritical_startup_issues.append(f"MCP bootstrap: {_mcp_exc}")

        try:
            from koda.services.llm_runner import warm_provider_capabilities

            await warm_provider_capabilities()
            log.info("provider_capabilities_initialized")
        except Exception:
            noncritical_startup_issues.append("provider_capability_init_error")
            log.exception("provider_capability_init_error")

        # Start periodic temp file cleanup
        from koda.utils.images import start_temp_cleanup_loop

        await loop_supervisor.start_loop("temp_cleanup", start_temp_cleanup_loop)

        # Start periodic approval cleanup to prevent stale ops accumulation
        from koda.utils.approval import start_approval_cleanup

        await loop_supervisor.start_loop("approval_cleanup", start_approval_cleanup)

        # Start periodic database maintenance (WAL checkpoint, integrity check, old row cleanup)
        async def _db_maintenance_loop() -> None:
            while True:
                await asyncio.sleep(86400)  # 24 hours
                try:
                    from koda.state.history_store import run_maintenance

                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, run_maintenance)
                    log.info("db_maintenance_complete", **result)
                except Exception:
                    log.exception("db_maintenance_loop_error")

        await loop_supervisor.start_loop("db_maintenance", _db_maintenance_loop)

        # Start database pool if enabled
        if POSTGRES_ENABLED:
            from koda.services.db_manager import db_manager

            try:
                await db_manager.start()
            except Exception:
                critical_startup_issues.append("db_manager_start_error")
                set_runtime_startup_state(
                    "failed",
                    details={"critical_issues": list(critical_startup_issues)},
                    expected_background_loops=expected_background_loops,
                )
                raise

        # Start browser if enabled
        if BROWSER_FEATURES_ENABLED:
            from koda.services.browser_manager import browser_manager

            try:
                await browser_manager.start()
            except Exception:
                critical_startup_issues.append("browser_manager_start_error")
                set_runtime_startup_state(
                    "failed",
                    details={"critical_issues": list(critical_startup_issues)},
                    expected_background_loops=expected_background_loops,
                )
                raise

        # Initialize circuit breaker metrics and emit startup event
        try:
            from koda.services.resilience import init_breaker_metrics

            init_breaker_metrics()
        except ImportError:
            pass

        from koda.services.audit import emit_task_lifecycle

        emit_task_lifecycle("system.agent_started")
        startup_details: dict[str, Any] = {}
        if noncritical_startup_issues:
            startup_details["noncritical_issues"] = list(noncritical_startup_issues)
        if critical_startup_issues:
            startup_details["critical_issues"] = list(critical_startup_issues)
            set_runtime_startup_state(
                "failed",
                details=startup_details,
                expected_background_loops=expected_background_loops,
            )
        else:
            set_runtime_startup_state(
                "ready",
                details=startup_details,
                expected_background_loops=expected_background_loops,
            )

    app.post_init = _post_init

    log.info("agent_starting", agent_id=os.environ.get("AGENT_ID", "default"), agent_name=AGENT_NAME)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
