"""Generate a deterministic repository map for humans and modern LLM tooling."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "ai" / "repo-map.yaml"

ROOT_DOCS = [
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
]

AGENT_SUBTREE_GUIDES = [
    "koda/AGENTS.md",
    "koda/services/AGENTS.md",
    "koda/memory/AGENTS.md",
    "tests/AGENTS.md",
]

CLAUDE_SUBTREE_GUIDES = [
    "koda/CLAUDE.md",
    "koda/services/CLAUDE.md",
    "koda/memory/CLAUDE.md",
    "tests/CLAUDE.md",
]

SUBTREE_GUIDES = AGENT_SUBTREE_GUIDES + CLAUDE_SUBTREE_GUIDES

REFERENCE_DOCS = [
    "docs/ai/llm-compatibility.md",
    "docs/ai/architecture-overview.md",
    "docs/ai/runtime-flows.md",
    "docs/ai/configuration-and-prompts.md",
    "docs/ai/change-playbook.md",
]

REPO_SKILL_FILES = [
    "docs/ai/skills/repo-orientation/SKILL.md",
    "docs/ai/skills/runtime-flow-changes/SKILL.md",
    "docs/ai/skills/memory-pipeline-changes/SKILL.md",
    "docs/ai/skills/integration-and-safety-changes/SKILL.md",
]

REPO_SKILL_METADATA = [
    "docs/ai/skills/repo-orientation/agents/openai.yaml",
    "docs/ai/skills/runtime-flow-changes/agents/openai.yaml",
    "docs/ai/skills/memory-pipeline-changes/agents/openai.yaml",
    "docs/ai/skills/integration-and-safety-changes/agents/openai.yaml",
]

IGNORED_ROOTS = [
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
]

IGNORED_PATTERNS = [
    "*.db",
]


def rel(path: Path) -> str:
    """Return a repository-relative POSIX path."""
    return path.relative_to(ROOT).as_posix()


def list_python_files(directory: str, include_init: bool = False) -> list[str]:
    """List Python files directly under a repository directory."""
    base = ROOT / directory
    if not base.is_dir():
        return []

    files: list[str] = []
    for path in sorted(base.glob("*.py")):
        if not include_init and path.name == "__init__.py":
            continue
        files.append(rel(path))
    return files


def list_test_files(directory: str) -> list[str]:
    """List pytest files and local conftest files directly under a directory."""
    base = ROOT / directory
    if not base.is_dir():
        return []

    files: list[str] = []
    conftest = base / "conftest.py"
    if conftest.is_file():
        files.append(rel(conftest))

    for path in sorted(base.glob("test_*.py")):
        files.append(rel(path))
    return files


def build_repo_map(root: Path | None = None) -> dict[str, Any]:
    """Build the canonical repository map structure."""
    active_root = root or ROOT
    if active_root != ROOT:
        raise ValueError("build_repo_map currently expects the repository root used by this script.")

    handlers = list_python_files("koda/handlers")
    services = list_python_files("koda/services")
    memory = list_python_files("koda/memory")
    utils = list_python_files("koda/utils")
    runtime_skills = sorted(rel(path) for path in (ROOT / "koda" / "skills").glob("*.md"))

    handler_tests = list_test_files("tests/test_handlers")
    service_tests = list_test_files("tests/test_services")
    memory_tests = list_test_files("tests/test_memory")
    util_tests = list_test_files("tests/test_utils")
    ai_doc_tests = ["tests/test_ai_docs.py", "tests/test_repo_map.py"]

    return {
        "metadata": {
            "repo_name": "koda",
            "format_version": 1,
            "canonical_map_path": "docs/ai/repo-map.yaml",
            "generator_script": "scripts/generate_repo_map.py",
            "generation_mode": "deterministic-stdlib",
            "llm_targets": ["generic-llm", "codex", "claude-code"],
            "summary": (
                "Machine-readable index for repository structure, runtime flows, guardrails, "
                "change recipes, test ownership, and provider entrypoints."
            ),
            "source_roots": ["koda", "apps/web", "tests", "docs/ai", "scripts"],
            "ignored_roots": IGNORED_ROOTS,
            "ignored_patterns": IGNORED_PATTERNS,
            "notes": [
                "Semantic flows, guardrails, and change recipes are curated in the generator.",
                "File inventories for handlers, services, memory, skills, and tests are auto-discovered.",
                (
                    "Provider-neutral repository guidance lives in docs/ai, repo-map.yaml, "
                    "README.md, and each SKILL.md file."
                ),
                (
                    "Public product and contributor documentation lives under docs/, while docs/ai "
                    "remains the repository guidance layer for humans and modern LLM tooling."
                ),
                (
                    "AGENTS.md files are Codex-oriented entrypoints, while CLAUDE.md files "
                    "mirror the same guidance for Claude Code."
                ),
                "agents/openai.yaml files add optional Codex metadata and do not replace canonical skill instructions.",
                "The committed YAML is expected to match generator output exactly.",
            ],
        },
        "entrypoints": [
            {
                "id": "console-script",
                "summary": "Package script entrypoint that resolves to the control-plane supervisor bootstrap.",
                "paths": ["pyproject.toml", "koda/control_plane/__main__.py"],
                "related_tests": ["tests/test_control_plane_dashboard_api.py"],
                "related_docs": ["README.md", "AGENTS.md", "docs/ai/architecture-overview.md"],
            },
            {
                "id": "web-dashboard",
                "summary": "Next.js entrypoint for the Koda operations dashboard and runtime relay server.",
                "paths": [
                    "package.json",
                    "pnpm-workspace.yaml",
                    "apps/web/package.json",
                    "apps/web/server.mjs",
                ],
                "related_tests": [
                    "apps/web/src/app/sessions/page.test.tsx",
                    "apps/web/src/components/memory/memory-dashboard-api.test.ts",
                ],
                "related_docs": ["README.md", "docs/install/local.md", "docs/install/vps.md"],
            },
            {
                "id": "telegram-runtime",
                "summary": (
                    "Primary application entrypoint that sets environment, registers handlers, and starts polling."
                ),
                "paths": ["koda/__main__.py"],
                "related_tests": [
                    "tests/test_handlers/test_commands.py",
                    "tests/test_services/test_agent_loop.py",
                ],
                "related_docs": [
                    "README.md",
                    "AGENTS.md",
                    "docs/ai/architecture-overview.md",
                    "docs/ai/runtime-flows.md",
                ],
            },
            {
                "id": "compatibility-wrapper",
                "summary": "Legacy file entrypoint that delegates directly to the package bootstrap.",
                "paths": ["agent.py"],
                "related_tests": [],
                "related_docs": ["README.md", "docs/ai/architecture-overview.md"],
            },
            {
                "id": "multi-agent-launcher",
                "summary": "Process launcher for the configured multi-agent control-plane supervisor.",
                "paths": ["launcher.py", "koda/control_plane/__main__.py"],
                "related_tests": [],
                "related_docs": ["README.md", "docs/ai/architecture-overview.md"],
            },
            {
                "id": "container-runtime",
                "summary": (
                    "Container build and compose entrypoints for running the "
                    "web dashboard, control plane, Postgres, and object storage."
                ),
                "paths": ["Dockerfile", "docker-compose.yml", "docker-compose.prod.yml"],
                "related_tests": [],
                "related_docs": ["README.md", "docs/ai/architecture-overview.md"],
            },
        ],
        "module_areas": [
            {
                "id": "web-operations-ui",
                "summary": (
                    "Next.js operator experience for onboarding, control-plane workflows, "
                    "dashboard views, runtime attachments, and web relay plumbing."
                ),
                "paths": [
                    "apps/web/package.json",
                    "apps/web/next.config.ts",
                    "apps/web/server.mjs",
                    "apps/web/src/app",
                    "apps/web/src/components",
                    "apps/web/src/hooks",
                    "apps/web/src/lib",
                ],
                "related_tests": [
                    "apps/web/src/app/sessions/page.test.tsx",
                    "apps/web/src/components/control-plane/catalog/agent-catalog.test.tsx",
                    "apps/web/src/components/memory/memory-dashboard-api.test.ts",
                    "apps/web/src/hooks/use-agent-editor.test.tsx",
                    "apps/web/src/lib/runtime-api.test.ts",
                ],
                "related_docs": [
                    "README.md",
                    "CONTRIBUTING.md",
                    "docs/install/local.md",
                    "docs/install/vps.md",
                ],
                "related_skills": [],
                "risk": "high",
            },
            {
                "id": "application-bootstrap",
                "summary": "Startup, environment initialization, path namespacing, and top-level persistence wiring.",
                "paths": [
                    "koda/__main__.py",
                    "koda/control_plane/__main__.py",
                    "koda/config.py",
                    "koda/state/history_store.py",
                    "agent.py",
                    "launcher.py",
                    "pyproject.toml",
                ],
                "related_tests": [
                    "tests/test_auth.py",
                    "tests/test_services/test_health.py",
                    "tests/test_services/runtime/test_smoke.py",
                    "tests/test_services/test_queue_helpers.py",
                ],
                "related_docs": [
                    "README.md",
                    "AGENTS.md",
                    "docs/ai/architecture-overview.md",
                    "docs/ai/configuration-and-prompts.md",
                ],
                "related_skills": ["docs/ai/skills/repo-orientation/SKILL.md"],
                "risk": "high",
            },
            {
                "id": "telegram-handlers",
                "summary": "Telegram-facing adapters for commands, messages, media, callbacks, and provider shortcuts.",
                "paths": handlers,
                "related_tests": handler_tests,
                "related_docs": [
                    "koda/AGENTS.md",
                    "docs/ai/runtime-flows.md",
                    "docs/ai/change-playbook.md",
                ],
                "related_skills": [
                    "docs/ai/skills/repo-orientation/SKILL.md",
                    "docs/ai/skills/runtime-flow-changes/SKILL.md",
                    "docs/ai/skills/integration-and-safety-changes/SKILL.md",
                ],
                "risk": "high",
            },
            {
                "id": "runtime-services",
                "summary": (
                    "Orchestration, provider-neutral LLM execution, tool dispatch, "
                    "integrations, scheduling, and runtime state management."
                ),
                "paths": services,
                "related_tests": service_tests,
                "related_docs": [
                    "koda/services/AGENTS.md",
                    "docs/ai/architecture-overview.md",
                    "docs/ai/runtime-flows.md",
                    "docs/ai/change-playbook.md",
                ],
                "related_skills": [
                    "docs/ai/skills/repo-orientation/SKILL.md",
                    "docs/ai/skills/runtime-flow-changes/SKILL.md",
                    "docs/ai/skills/integration-and-safety-changes/SKILL.md",
                ],
                "risk": "high",
            },
            {
                "id": "memory-subsystem",
                "summary": "Recall, extraction, storage, maintenance, digests, and best-effort context enrichment.",
                "paths": memory,
                "related_tests": memory_tests,
                "related_docs": [
                    "koda/memory/AGENTS.md",
                    "docs/ai/runtime-flows.md",
                    "docs/ai/configuration-and-prompts.md",
                ],
                "related_skills": [
                    "docs/ai/skills/repo-orientation/SKILL.md",
                    "docs/ai/skills/memory-pipeline-changes/SKILL.md",
                ],
                "risk": "high",
            },
            {
                "id": "runtime-skills-and-prompt-contracts",
                "summary": (
                    "Runtime /skill templates plus prompt-contract guidance. "
                    "Operational agent prompts are DB-driven compiled documents from the control plane."
                ),
                "paths": [
                    "koda/control_plane/agent_spec.py",
                    "koda/control_plane/manager.py",
                    "koda/services/prompt_budget.py",
                ]
                + runtime_skills,
                "related_tests": [
                    "tests/test_handlers/test_commands_extended.py",
                    "tests/test_services/test_templates.py",
                    "tests/test_services/test_tool_prompt.py",
                ],
                "related_docs": [
                    "docs/ai/configuration-and-prompts.md",
                    "docs/ai/change-playbook.md",
                ],
                "related_skills": ["docs/ai/skills/repo-orientation/SKILL.md"],
                "risk": "high",
            },
            {
                "id": "shared-utilities",
                "summary": "Reusable helpers for messaging, files, media handling, approval, formatting, and parsing.",
                "paths": utils,
                "related_tests": util_tests,
                "related_docs": [
                    "koda/AGENTS.md",
                    "tests/AGENTS.md",
                    "docs/ai/change-playbook.md",
                ],
                "related_skills": ["docs/ai/skills/repo-orientation/SKILL.md"],
                "risk": "medium",
            },
            {
                "id": "developer-ai-guidance",
                "summary": (
                    "Repository guidance, provider entrypoints, repo-local skills, repo-map generation, "
                    "and documentation contract tests for modern LLM tooling."
                ),
                "paths": ROOT_DOCS
                + SUBTREE_GUIDES
                + REFERENCE_DOCS
                + REPO_SKILL_FILES
                + REPO_SKILL_METADATA
                + ["scripts/generate_repo_map.py", "docs/ai/repo-map.yaml"],
                "related_tests": ai_doc_tests,
                "related_docs": ROOT_DOCS + REFERENCE_DOCS + ["docs/ai/repo-map.yaml"],
                "related_skills": REPO_SKILL_FILES,
                "risk": "medium",
            },
        ],
        "runtime_flows": [
            {
                "id": "message-to-response",
                "summary": (
                    "Telegram message or command intake through queue orchestration "
                    "to provider execution, fallback handling, and final Telegram delivery."
                ),
                "steps": [
                    {
                        "name": "Register handlers and bootstrap the agent application.",
                        "path": "koda/__main__.py",
                    },
                    {
                        "name": "Normalize text, command, media, or callback input in handler modules.",
                        "path": "koda/handlers/messages.py",
                    },
                    {
                        "name": "Queue work, build the effective compiled system prompt, and manage task state.",
                        "path": "koda/services/queue_manager.py",
                    },
                    {
                        "name": (
                            "Dispatch through the provider-neutral runner, choose the active provider session, "
                            "and invoke the matching provider adapter."
                        ),
                        "path": "koda/services/llm_runner.py",
                    },
                    {
                        "name": "Persist history, sessions, and task results via the primary state stores.",
                        "path": "koda/state/history_store.py",
                    },
                    {
                        "name": "Format and send the final Telegram response, artifacts, and optional voice output.",
                        "path": "koda/services/queue_manager.py",
                    },
                ],
                "related_tests": [
                    "tests/test_handlers/test_messages.py",
                    "tests/test_services/test_agent_loop.py",
                    "tests/test_services/test_claude_runner.py",
                    "tests/test_services/test_codex_runner.py",
                ],
                "related_docs": [
                    "docs/ai/runtime-flows.md",
                    "docs/ai/architecture-overview.md",
                ],
            },
            {
                "id": "agent-tool-loop",
                "summary": (
                    "The active provider emits <agent_cmd> tags, runtime tools execute, "
                    "and the queue manager resumes the same provider or boots a fallback provider."
                ),
                "steps": [
                    {
                        "name": "Expose available runtime agent tools in the system prompt.",
                        "path": "koda/services/tool_prompt.py",
                    },
                    {
                        "name": "Parse agent command tags and classify read or write behavior.",
                        "path": "koda/services/tool_dispatcher.py",
                    },
                    {
                        "name": "Execute runtime tools and collect results.",
                        "path": "koda/services/tool_dispatcher.py",
                    },
                    {
                        "name": "Resume provider execution with formatted tool results and loop until completion.",
                        "path": "koda/services/queue_manager.py",
                    },
                ],
                "related_tests": [
                    "tests/test_services/test_agent_loop.py",
                    "tests/test_services/test_tool_dispatcher.py",
                    "tests/test_services/test_tool_prompt.py",
                ],
                "related_docs": [
                    "docs/ai/runtime-flows.md",
                    "docs/ai/change-playbook.md",
                ],
            },
            {
                "id": "media-inputs",
                "summary": (
                    "Images, documents, audio, and voice notes are downloaded, "
                    "converted into prompts, and routed through the same queue."
                ),
                "steps": [
                    {
                        "name": "Receive Telegram media and dispatch to the matching handler.",
                        "path": "koda/handlers/messages.py",
                    },
                    {
                        "name": "Download or transcode input payloads using media utilities.",
                        "path": "koda/utils/audio.py",
                    },
                    {
                        "name": "Generate a text prompt from image, document, or audio content.",
                        "path": "koda/utils/documents.py",
                    },
                    {
                        "name": "Enqueue the resulting query and reuse the standard request flow.",
                        "path": "koda/services/queue_manager.py",
                    },
                ],
                "related_tests": [
                    "tests/test_handlers/test_messages.py",
                    "tests/test_utils/test_audio.py",
                    "tests/test_utils/test_documents.py",
                    "tests/test_utils/test_images.py",
                ],
                "related_docs": ["docs/ai/runtime-flows.md"],
            },
            {
                "id": "memory-lifecycle",
                "summary": (
                    "Recall runs before a provider call, extraction runs after "
                    "completion, and maintenance tasks stay out of the hot path."
                ),
                "steps": [
                    {
                        "name": "Start memory recall during query-context preparation.",
                        "path": "koda/services/queue_manager.py",
                    },
                    {
                        "name": "Coordinate pre-query and post-query memory operations.",
                        "path": "koda/memory/manager.py",
                    },
                    {
                        "name": "Build ranked recall context and proactive context.",
                        "path": "koda/memory/recall.py",
                    },
                    {
                        "name": "Extract candidate memories from completed interactions.",
                        "path": "koda/memory/extractor.py",
                    },
                    {
                        "name": "Persist and maintain memory state.",
                        "path": "koda/memory/store.py",
                    },
                ],
                "related_tests": [
                    "tests/test_memory/test_recall.py",
                    "tests/test_memory/test_extractor.py",
                    "tests/test_memory/test_maintenance_scheduler.py",
                    "tests/test_memory/test_types.py",
                ],
                "related_docs": [
                    "docs/ai/runtime-flows.md",
                    "docs/ai/configuration-and-prompts.md",
                ],
            },
            {
                "id": "scheduled-automation",
                "summary": (
                    "Cron jobs, maintenance, and digest loops schedule agent work without bypassing runtime guardrails."
                ),
                "steps": [
                    {
                        "name": "Persist cron jobs and runtime schedule metadata.",
                        "path": "koda/services/cron_store.py",
                    },
                    {
                        "name": "Schedule recurring tasks that route back through the agent runtime.",
                        "path": "koda/services/scheduler.py",
                    },
                    {
                        "name": "Run memory digest scheduling and dispatch.",
                        "path": "koda/memory/digest_scheduler.py",
                    },
                    {
                        "name": "Run memory maintenance scheduling and dispatch.",
                        "path": "koda/memory/maintenance_scheduler.py",
                    },
                ],
                "related_tests": [
                    "tests/test_services/test_scheduler.py",
                    "tests/test_services/test_tool_dispatcher.py",
                    "tests/test_memory/test_maintenance_scheduler.py",
                ],
                "related_docs": ["docs/ai/runtime-flows.md"],
            },
        ],
        "config_surfaces": [
            {
                "id": "multi-agent-and-identity",
                "summary": (
                    "Owner identity, agent naming, AGENT_ID namespacing, work "
                    "directories, and shared authorization settings."
                ),
                "source_paths": ["koda/config.py", ".env.example", "launcher.py"],
                "env_keys": [
                    "AGENT_ID",
                    "OWNER_NAME",
                    "OWNER_EMAIL",
                    "OWNER_GITHUB",
                    "AGENT_TOKEN",
                    "AGENT_NAME",
                    "DEFAULT_WORK_DIR",
                    "PROJECT_DIRS",
                    "ALLOWED_USER_IDS",
                ],
                "related_docs": [
                    "README.md",
                    "AGENTS.md",
                    "docs/ai/configuration-and-prompts.md",
                ],
                "related_tests": [
                    "tests/test_auth.py",
                    "tests/test_handlers/test_commands.py",
                ],
            },
            {
                "id": "provider-execution",
                "summary": (
                    "Provider selection, per-provider model catalogs, fallback order, "
                    "timeouts, budgets, and resume behavior for request execution."
                ),
                "source_paths": [
                    "koda/config.py",
                    "koda/memory/config.py",
                    "koda/services/llm_runner.py",
                    "koda/services/claude_runner.py",
                    "koda/services/codex_runner.py",
                ],
                "env_keys": [
                    "DEFAULT_PROVIDER",
                    "PROVIDER_FALLBACK_ORDER",
                    "TRANSCRIPT_REPLAY_LIMIT",
                    "CLAUDE_ENABLED",
                    "CLAUDE_TIMEOUT",
                    "CLAUDE_AVAILABLE_MODELS",
                    "CLAUDE_DEFAULT_MODEL",
                    "CODEX_ENABLED",
                    "CODEX_BIN",
                    "CODEX_TIMEOUT",
                    "CODEX_FIRST_CHUNK_TIMEOUT",
                    "CODEX_SANDBOX",
                    "CODEX_APPROVAL_POLICY",
                    "CODEX_SKIP_GIT_REPO_CHECK",
                    "CODEX_AVAILABLE_MODELS",
                    "CODEX_DEFAULT_MODEL",
                    "DEFAULT_MODEL",
                    "MODEL_PRICING_USD",
                    "MAX_BUDGET_USD",
                    "MAX_TOTAL_BUDGET_USD",
                    "MAX_TURNS",
                    "FIRST_CHUNK_TIMEOUT",
                    "MEMORY_EXTRACTION_PROVIDER",
                    "MEMORY_EXTRACTION_MODEL",
                ],
                "related_docs": [
                    "docs/ai/configuration-and-prompts.md",
                    "docs/ai/runtime-flows.md",
                ],
                "related_tests": [
                    "tests/test_services/test_claude_runner.py",
                    "tests/test_services/test_codex_runner.py",
                    "tests/test_services/test_model_router.py",
                ],
            },
            {
                "id": "shell-and-provider-safety",
                "summary": (
                    "Shell, git-like, and provider-specific block patterns plus feature flags for external tools."
                ),
                "source_paths": [
                    "koda/config.py",
                    "koda/services/cli_runner.py",
                    "koda/services/shell_runner.py",
                    "koda/services/tool_dispatcher.py",
                ],
                "env_keys": [
                    "SHELL_ENABLED",
                    "SHELL_TIMEOUT",
                    "GH_ENABLED",
                    "GLAB_ENABLED",
                    "DOCKER_ENABLED",
                    "BLOCKED_GH_PATTERN",
                    "BLOCKED_GLAB_PATTERN",
                    "BLOCKED_DOCKER_PATTERN",
                ],
                "related_docs": ["docs/ai/configuration-and-prompts.md"],
                "related_tests": [
                    "tests/test_services/test_cli_runner.py",
                    "tests/test_services/test_security.py",
                    "tests/test_services/test_shell_runner.py",
                ],
            },
            {
                "id": "integrations",
                "summary": (
                    "Feature flags and connection settings for browser, Atlassian, "
                    "Google Workspace, PostgreSQL, and AWS integrations."
                ),
                "source_paths": [
                    "koda/config.py",
                    ".env.example",
                    "koda/services/browser_manager.py",
                    "koda/services/atlassian_client.py",
                    "koda/services/db_manager.py",
                ],
                "env_keys": [
                    "BROWSER_ENABLED",
                    "GWS_ENABLED",
                    "JIRA_ENABLED",
                    "CONFLUENCE_ENABLED",
                    "POSTGRES_ENABLED",
                    "AWS_ENABLED",
                ],
                "related_docs": [
                    "docs/ai/configuration-and-prompts.md",
                    "docs/ai/change-playbook.md",
                ],
                "related_tests": [
                    "tests/test_handlers/test_browser.py",
                    "tests/test_handlers/test_atlassian.py",
                    "tests/test_handlers/test_google_workspace.py",
                    "tests/test_services/test_db_manager.py",
                ],
            },
            {
                "id": "memory-and-digests",
                "summary": "Memory recall, extraction, thresholds, maintenance, and digest scheduling configuration.",
                "source_paths": [
                    "koda/config.py",
                    "koda/memory/config.py",
                    ".env.example",
                ],
                "env_keys": [
                    "MEMORY_ENABLED",
                    "MEMORY_EMBEDDING_MODEL",
                    "MEMORY_MAX_RECALL",
                    "MEMORY_RECALL_THRESHOLD",
                    "MEMORY_MAINTENANCE_ENABLED",
                    "MEMORY_DIGEST_ENABLED",
                    "MEMORY_PROACTIVE_ENABLED",
                ],
                "related_docs": [
                    "docs/ai/configuration-and-prompts.md",
                    "docs/ai/runtime-flows.md",
                ],
                "related_tests": memory_tests,
            },
            {
                "id": "audio-and-voice",
                "summary": "Speech-to-text, TTS, and voice-response configuration for audio workflows.",
                "source_paths": [
                    "koda/config.py",
                    ".env.example",
                    "koda/utils/audio.py",
                    "koda/utils/tts.py",
                ],
                "env_keys": [
                    "WHISPER_ENABLED",
                    "WHISPER_BIN",
                    "WHISPER_MODEL",
                    "AUDIO_PREPROCESS",
                    "TTS_ENABLED",
                    "TTS_DEFAULT_VOICE",
                    "ELEVENLABS_API_KEY",
                ],
                "related_docs": ["docs/ai/configuration-and-prompts.md"],
                "related_tests": [
                    "tests/test_utils/test_audio.py",
                    "tests/test_utils/test_tts.py",
                ],
            },
        ],
        "guardrails": [
            {
                "id": "authorized-user-access",
                "summary": "Only explicitly allowed Telegram users can interact with the agent.",
                "enforced_by": ["koda/auth.py", "koda/utils/command_helpers.py"],
                "related_tests": ["tests/test_auth.py"],
                "related_docs": ["AGENTS.md", "koda/AGENTS.md"],
            },
            {
                "id": "safe-working-directory",
                "summary": (
                    "Setdir and file operations are constrained to safe resolved "
                    "paths and reject sensitive system locations."
                ),
                "enforced_by": [
                    "koda/handlers/commands.py",
                    "koda/utils/files.py",
                    "koda/config.py",
                ],
                "related_tests": [
                    "tests/test_handlers/test_setdir_security.py",
                    "tests/test_handlers/test_commands_extended.py",
                ],
                "related_docs": ["AGENTS.md", "koda/AGENTS.md"],
            },
            {
                "id": "supervised-write-approval",
                "summary": "Write-capable runtime actions require explicit approval in supervised mode.",
                "enforced_by": [
                    "koda/utils/approval.py",
                    "koda/services/tool_dispatcher.py",
                    "koda/handlers/callbacks.py",
                ],
                "related_tests": [
                    "tests/test_handlers/test_approval_callbacks.py",
                    "tests/test_handlers/test_agent_mode.py",
                    "tests/test_services/test_tool_dispatcher.py",
                ],
                "related_docs": [
                    "AGENTS.md",
                    "koda/services/AGENTS.md",
                    "docs/ai/runtime-flows.md",
                ],
            },
            {
                "id": "blocked-shell-and-provider-patterns",
                "summary": (
                    "Dangerous shell syntax, metacharacters, and provider-specific "
                    "blocked operations are rejected before execution."
                ),
                "enforced_by": [
                    "koda/config.py",
                    "koda/services/cli_runner.py",
                    "koda/services/shell_runner.py",
                    "koda/services/tool_dispatcher.py",
                ],
                "related_tests": [
                    "tests/test_services/test_cli_runner.py",
                    "tests/test_services/test_security.py",
                    "tests/test_services/test_shell_runner.py",
                ],
                "related_docs": [
                    "AGENTS.md",
                    "docs/ai/configuration-and-prompts.md",
                ],
            },
            {
                "id": "postgres-read-only",
                "summary": (
                    "PostgreSQL access is limited to read-oriented statements with "
                    "comment, multi-statement, and mutation blocking."
                ),
                "enforced_by": ["koda/services/db_manager.py"],
                "related_tests": ["tests/test_services/test_db_manager.py"],
                "related_docs": [
                    "koda/services/AGENTS.md",
                    "docs/ai/change-playbook.md",
                ],
            },
            {
                "id": "memory-best-effort",
                "summary": "Memory recall and extraction can enrich requests but must never block the core agent flow.",
                "enforced_by": [
                    "koda/services/queue_manager.py",
                    "koda/memory/manager.py",
                    "koda/memory/config.py",
                ],
                "related_tests": [
                    "tests/test_memory/test_recall.py",
                    "tests/test_memory/test_extractor.py",
                    "tests/test_memory/test_types.py",
                ],
                "related_docs": [
                    "koda/memory/AGENTS.md",
                    "docs/ai/runtime-flows.md",
                ],
            },
            {
                "id": "runtime-and-dev-guide-separation",
                "summary": (
                    "Control-plane agent documents and runtime /skill templates remain separate "
                    "from repository guidance docs, provider entrypoints, and repo-local skills."
                ),
                "enforced_by": [
                    "AGENTS.md",
                    "CLAUDE.md",
                    "koda/AGENTS.md",
                    "koda/CLAUDE.md",
                    "docs/ai/configuration-and-prompts.md",
                    "docs/ai/llm-compatibility.md",
                ],
                "related_tests": ["tests/test_ai_docs.py", "tests/test_repo_map.py"],
                "related_docs": [
                    "README.md",
                    "AGENTS.md",
                    "CLAUDE.md",
                    "koda/AGENTS.md",
                    "koda/CLAUDE.md",
                ],
            },
        ],
        "change_recipes": [
            {
                "id": "add-telegram-command",
                "summary": (
                    "Add or change a Telegram command by updating handlers, "
                    "registering it, and covering it with handler tests."
                ),
                "primary_paths": [
                    "koda/handlers",
                    "koda/__main__.py",
                    "tests/test_handlers",
                ],
                "related_tests": [
                    "tests/test_handlers/test_commands.py",
                    "tests/test_handlers/test_commands_extended.py",
                ],
                "related_docs": [
                    "docs/ai/change-playbook.md",
                    "docs/ai/runtime-flows.md",
                ],
                "related_skills": [
                    "docs/ai/skills/repo-orientation/SKILL.md",
                    "docs/ai/skills/runtime-flow-changes/SKILL.md",
                ],
            },
            {
                "id": "change-runtime-agent-tool",
                "summary": "Keep prompt exposure and runtime execution aligned when adding or changing agent tools.",
                "primary_paths": [
                    "koda/services/tool_prompt.py",
                    "koda/services/tool_dispatcher.py",
                    "tests/test_services",
                ],
                "related_tests": [
                    "tests/test_services/test_tool_prompt.py",
                    "tests/test_services/test_tool_dispatcher.py",
                    "tests/test_services/test_agent_loop.py",
                ],
                "related_docs": [
                    "docs/ai/change-playbook.md",
                    "docs/ai/runtime-flows.md",
                ],
                "related_skills": [
                    "docs/ai/skills/runtime-flow-changes/SKILL.md",
                    "docs/ai/skills/integration-and-safety-changes/SKILL.md",
                ],
            },
            {
                "id": "add-external-integration",
                "summary": (
                    "Add config, service wiring, safe execution rules, and tests for new providers or capabilities."
                ),
                "primary_paths": [
                    "koda/config.py",
                    "koda/services",
                    ".env.example",
                    "tests/test_services",
                    "tests/test_handlers",
                ],
                "related_tests": [
                    "tests/test_services/test_security.py",
                    "tests/test_services/test_db_manager.py",
                    "tests/test_handlers/test_browser.py",
                    "tests/test_handlers/test_atlassian.py",
                    "tests/test_handlers/test_google_workspace.py",
                ],
                "related_docs": [
                    "docs/ai/change-playbook.md",
                    "docs/ai/configuration-and-prompts.md",
                ],
                "related_skills": ["docs/ai/skills/integration-and-safety-changes/SKILL.md"],
            },
            {
                "id": "change-queue-or-provider-flow",
                "summary": (
                    "Trace the request path end to end before modifying queueing, "
                    "prompt assembly, provider routing, fallback, streaming, retries, or response delivery."
                ),
                "primary_paths": [
                    "koda/services/queue_manager.py",
                    "koda/services/llm_runner.py",
                    "koda/services/claude_runner.py",
                    "koda/services/codex_runner.py",
                    "tests/test_services",
                ],
                "related_tests": [
                    "tests/test_services/test_agent_loop.py",
                    "tests/test_services/test_claude_runner.py",
                    "tests/test_services/test_codex_runner.py",
                    "tests/test_handlers/test_messages.py",
                ],
                "related_docs": [
                    "docs/ai/runtime-flows.md",
                    "docs/ai/change-playbook.md",
                ],
                "related_skills": ["docs/ai/skills/runtime-flow-changes/SKILL.md"],
            },
            {
                "id": "change-memory-pipeline",
                "summary": "Keep memory best-effort while updating recall, extraction, storage, or scheduler behavior.",
                "primary_paths": [
                    "koda/memory",
                    "koda/services/queue_manager.py",
                    ".env.example",
                    "tests/test_memory",
                ],
                "related_tests": memory_tests,
                "related_docs": [
                    "docs/ai/runtime-flows.md",
                    "docs/ai/configuration-and-prompts.md",
                    "docs/ai/change-playbook.md",
                ],
                "related_skills": ["docs/ai/skills/memory-pipeline-changes/SKILL.md"],
            },
            {
                "id": "change-ai-guidance-layer",
                "summary": (
                    "Update the human docs, repo-local skills, and deterministic "
                    "repo map together so the AI layer stays coherent."
                ),
                "primary_paths": [
                    "README.md",
                    "AGENTS.md",
                    "CLAUDE.md",
                    "docs/ai",
                    "scripts/generate_repo_map.py",
                    "tests/test_ai_docs.py",
                    "tests/test_repo_map.py",
                ],
                "related_tests": ["tests/test_ai_docs.py", "tests/test_repo_map.py"],
                "related_docs": ROOT_DOCS + REFERENCE_DOCS + ["docs/ai/repo-map.yaml"],
                "related_skills": REPO_SKILL_FILES,
            },
        ],
        "test_targets": [
            {
                "id": "authentication-and-bootstrap",
                "summary": "Authorization, database, and top-level runtime state checks.",
                "source_paths": [
                    "koda/auth.py",
                    "koda/config.py",
                    "koda/state/history_store.py",
                ],
                "test_paths": [
                    "tests/test_auth.py",
                    "tests/test_services/test_health.py",
                    "tests/test_services/runtime/test_smoke.py",
                ],
                "related_docs": ["tests/AGENTS.md", "docs/ai/architecture-overview.md"],
            },
            {
                "id": "handlers",
                "summary": "Telegram command, callback, and message behavior coverage.",
                "source_paths": handlers,
                "test_paths": handler_tests,
                "related_docs": ["tests/AGENTS.md", "docs/ai/change-playbook.md"],
            },
            {
                "id": "services",
                "summary": "Queue orchestration, provider integrations, runtime tools, and safety-rule coverage.",
                "source_paths": services,
                "test_paths": service_tests,
                "related_docs": ["tests/AGENTS.md", "docs/ai/runtime-flows.md"],
            },
            {
                "id": "memory",
                "summary": "Recall, extraction, storage, maintenance, and digest behavior coverage.",
                "source_paths": memory,
                "test_paths": memory_tests,
                "related_docs": ["tests/AGENTS.md", "koda/memory/AGENTS.md"],
            },
            {
                "id": "utilities",
                "summary": "Low-level helper coverage for media, files, formatting, parsing, and messaging.",
                "source_paths": utils,
                "test_paths": util_tests,
                "related_docs": ["tests/AGENTS.md", "koda/AGENTS.md"],
            },
            {
                "id": "ai-docs-and-repo-map",
                "summary": (
                    "Repository guidance drift checks for provider-neutral docs, "
                    "provider entrypoints, skills, and the canonical repo map."
                ),
                "source_paths": ROOT_DOCS
                + SUBTREE_GUIDES
                + REFERENCE_DOCS
                + REPO_SKILL_FILES
                + REPO_SKILL_METADATA
                + ["scripts/generate_repo_map.py", "docs/ai/repo-map.yaml"],
                "test_paths": ai_doc_tests,
                "related_docs": ["tests/AGENTS.md", "docs/ai/repo-map.yaml"],
            },
        ],
        "ai_guides": {
            "summary": (
                "Provider-neutral docs and provider-specific entrypoints that explain "
                "how to navigate and change the repository."
            ),
            "canonical_map": "docs/ai/repo-map.yaml",
            "generator_script": "scripts/generate_repo_map.py",
            "provider_neutral_docs": ["README.md", "docs/ai/repo-map.yaml"] + REFERENCE_DOCS + REPO_SKILL_FILES,
            "codex_entrypoints": ["AGENTS.md"] + AGENT_SUBTREE_GUIDES + REPO_SKILL_METADATA,
            "claude_code_entrypoints": ["CLAUDE.md"] + CLAUDE_SUBTREE_GUIDES,
            "root_docs": ROOT_DOCS,
            "subtree_guides": SUBTREE_GUIDES,
            "reference_docs": REFERENCE_DOCS,
            "repo_skill_files": REPO_SKILL_FILES,
            "repo_skill_metadata": REPO_SKILL_METADATA,
        },
    }


def render_yaml(value: Any, indent: int = 0) -> str:
    """Render a Python value into a small deterministic YAML subset."""
    lines = _render_yaml_lines(value, indent=indent)
    return "\n".join(lines) + "\n"


def _render_yaml_lines(value: Any, indent: int) -> list[str]:
    prefix = " " * indent

    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if _is_scalar(item):
                lines.append(f"{prefix}{key}: {_format_scalar(item)}")
            elif isinstance(item, list) and not item:
                lines.append(f"{prefix}{key}: []")
            elif isinstance(item, dict) and not item:
                lines.append(f"{prefix}{key}: {{}}")
            else:
                lines.append(f"{prefix}{key}:")
                lines.extend(_render_yaml_lines(item, indent + 2))
        return lines

    if isinstance(value, list):
        lines = []
        for item in value:
            if _is_scalar(item):
                lines.append(f"{prefix}- {_format_scalar(item)}")
            elif isinstance(item, list) and not item:
                lines.append(f"{prefix}- []")
            elif isinstance(item, dict) and not item:
                lines.append(f"{prefix}- {{}}")
            else:
                lines.append(f"{prefix}-")
                lines.extend(_render_yaml_lines(item, indent + 2))
        return lines

    return [f"{prefix}{_format_scalar(value)}"]


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def write_repo_map(output_path: Path = OUTPUT_PATH) -> None:
    """Write the canonical repo map file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_yaml(build_repo_map()), encoding="utf-8")


def check_repo_map(output_path: Path = OUTPUT_PATH) -> int:
    """Return an exit code indicating whether the committed repo map is current."""
    expected = render_yaml(build_repo_map())
    if not output_path.exists():
        print(
            f"Missing repo map: {rel(output_path)}. Run `python3 scripts/generate_repo_map.py --write`.",
            file=sys.stderr,
        )
        return 1

    current = output_path.read_text(encoding="utf-8")
    if current != expected:
        print(
            f"Repo map drift detected in {rel(output_path)}. Run `python3 scripts/generate_repo_map.py --write`.",
            file=sys.stderr,
        )
        return 1

    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the canonical YAML file to docs/ai/repo-map.yaml.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if docs/ai/repo-map.yaml does not match generated output.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)

    if args.write and args.check:
        print("Use either --write or --check, not both.", file=sys.stderr)
        return 2

    if args.write:
        write_repo_map()
        return 0

    if args.check:
        return check_repo_map()

    sys.stdout.write(render_yaml(build_repo_map()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
