"""Configuration keys that nothing read are gone, and no code or doc names them (M4-E1-T2).

TD-003 and D-194: these keys were defined in ``koda/config.py``, ``koda/memory/config.py`` or
``koda/knowledge/config.py``, or offered as control-plane runtime settings, but no Python, Rust
or web code read them. ``PLUGIN_SANDBOX_ENABLED`` stays until M1-E4-T4.
"""

from __future__ import annotations

import re
from pathlib import Path

import koda.config as config_module
import koda.knowledge.config as knowledge_config
import koda.memory.config as memory_config
from koda.control_plane import manager as manager_module

ROOT = Path(__file__).resolve().parents[1]

REMOVED_KEYS: tuple[str, ...] = (
    "INTER_AGENT_MESSAGE_TIMEOUT",
    "WORKFLOW_MAX_PARALLEL",
    "RUNTIME_PTY_ENABLED",
    "RUNTIME_BUNDLE_RETENTION_DAYS",
    "RUNTIME_LOCAL_UI_BIND",
    "RUNTIME_ATTACH_IDLE_TIMEOUT_SECONDS",
    "RUNTIME_BROWSER_DISPLAY_BASE",
    "RUNTIME_PTY_CHUNK_BYTES",
    "RUNTIME_PTY_BACKPRESSURE_KB",
    "RUNTIME_LOOP_MAX_CYCLES",
    "RUNTIME_LOOP_MAX_RETRIES_PER_PHASE",
    "RUNTIME_LOOP_NO_CHANGE_LIMIT",
    "RUNTIME_CHECKPOINT_MAX_UNTRACKED_BYTES",
    "SNAPSHOT_MAX_SIZE_MB",
    "PLUGIN_DIRS",
    "PLUGIN_MAX_EXECUTION_TIMEOUT",
    "MEMORY_LEXICAL_CANDIDATES",
    "KNOWLEDGE_V2_NEO4J_URI",
    "KNOWLEDGE_V2_NEO4J_USER",
    "KNOWLEDGE_V2_NEO4J_PASSWORD",
)

# Everything that could read a key by name: Python, Rust, the dashboard, the CLI, scripts,
# compose files, and the two documents that list configuration.
_SCANNED_DIRS = ("koda", "rust", "apps/web/src", "apps/web/server.mjs", "packages/cli", "scripts")
_SCANNED_FILES = (".env.example", "docs/config/reference.md")
_SUFFIXES = {".py", ".rs", ".ts", ".tsx", ".mjs", ".js", ".sh", ".yml", ".yaml", ".toml", ".env", ".md"}


def _scanned_paths() -> list[Path]:
    paths: list[Path] = [ROOT / name for name in _SCANNED_FILES]
    paths.extend(ROOT.glob("docker-compose*.yml"))
    for entry in _SCANNED_DIRS:
        base = ROOT / entry
        if base.is_file():
            paths.append(base)
            continue
        for path in base.rglob("*"):
            if "target" in path.parts or "node_modules" in path.parts:
                continue
            if path.is_file() and (path.suffix in _SUFFIXES or path.name.startswith(".env")):
                paths.append(path)
    return paths


def test_removed_keys_are_not_module_attributes() -> None:
    for module in (config_module, memory_config, knowledge_config):
        present = [key for key in REMOVED_KEYS if hasattr(module, key)]
        assert present == [], f"{module.__name__} still defines {present}"


def test_no_code_or_config_doc_names_a_removed_key() -> None:
    pattern = re.compile(r"\b(" + "|".join(REMOVED_KEYS) + r")\b")
    hits: list[str] = []
    for path in _scanned_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                hits.append(f"{path.relative_to(ROOT)}:{lineno}: {match.group(1)}")
    assert hits == []


def test_runtime_settings_section_offers_only_keys_something_reads() -> None:
    runtime_fields = manager_module._SYSTEM_SETTINGS_FIELD_SPECS["runtime"]
    env_keys = {env_key for env_key, _kind in runtime_fields.values()}
    assert env_keys.isdisjoint(REMOVED_KEYS)
    for removed_field in (
        "runtime_pty_enabled",
        "runtime_local_ui_bind",
        "runtime_attach_idle_timeout_seconds",
        "runtime_browser_display_base",
    ):
        assert removed_field not in runtime_fields


def test_plugin_sandbox_flag_stays_until_m1_e4_t4() -> None:
    assert hasattr(config_module, "PLUGIN_SANDBOX_ENABLED")
