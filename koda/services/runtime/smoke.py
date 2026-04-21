"""Operational smoke checks for the isolated runtime backend."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import koda.config as config_module
from koda.services.browser_manager import browser_manager
from koda.services.runtime.controller import RuntimeController
from koda.state.history_store import create_task
from koda.state.primary import require_primary_state_backend


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def detect_playwright_browser_ready() -> bool:
    """Return whether Playwright can launch Chromium on this machine."""
    if importlib.util.find_spec("playwright.sync_api") is None:
        return False
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from playwright.sync_api import sync_playwright\n"
                    "with sync_playwright() as playwright:\n"
                    "    browser = playwright.chromium.launch(headless=True)\n"
                    "    browser.close()\n"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result.returncode == 0
    except Exception:
        return False


def init_smoke_git_repo(path: Path) -> None:
    """Create a tiny git repository used to exercise worktree provisioning."""
    if (path / ".git").exists():
        existing_head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
        if existing_head.returncode == 0:
            return
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Runtime Smoke"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "runtime-smoke@example.com"],
        check=True,
        capture_output=True,
    )
    (path / "README.md").write_text("runtime smoke base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], check=True, capture_output=True)


def detect_runtime_smoke_prerequisites() -> dict[str, Any]:
    """Return the local prerequisites for real runtime smoke execution."""
    browser_transport = str(config_module.RUNTIME_BROWSER_TRANSPORT or "").strip().lower()
    playwright_python_available = importlib.util.find_spec("playwright") is not None
    playwright_browser_ready = playwright_python_available and detect_playwright_browser_ready()
    chromium_candidates = {
        name: shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
    }
    return {
        "platform": platform.system().lower(),
        "effective_browser_transport": browser_transport,
        "git": {"available": shutil.which("git") is not None, "path": shutil.which("git")},
        "playwright_python_available": playwright_python_available,
        "playwright_browser_ready": playwright_browser_ready,
        "chromium_binaries": chromium_candidates,
        "chromium_available": any(path is not None for path in chromium_candidates.values()),
    }


def runtime_smoke_suggested_actions(prerequisites: dict[str, Any]) -> list[str]:
    """Return actionable next steps for the current machine."""
    actions: list[str] = []
    if not prerequisites.get("playwright_python_available"):
        actions.append('Instale as dependências Python do projeto com `.venv/bin/pip install -e ".[dev]"`.')
    if prerequisites.get("playwright_python_available") and not prerequisites.get("playwright_browser_ready"):
        actions.append("Instale o navegador do Playwright com `.venv/bin/python -m playwright install chromium`.")
    effective_transport = str(prerequisites.get("effective_browser_transport") or "")
    if effective_transport == "local_headful":
        actions.append("Com `RUNTIME_BROWSER_TRANSPORT=local_headful`, o navegador visual roda localmente.")
    return actions


async def _wait_for_terminal_log(path: Path, *, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return True
        await asyncio.sleep(0.1)
    return path.exists() and path.stat().st_size > 0


async def run_runtime_smoke(
    *,
    runtime_root: Path,
    db_path: Path | None = None,
    include_browser_live: bool = False,
    require_browser_live: bool = False,
    shell: str | None = None,
) -> dict[str, Any]:
    """Exercise isolated runtime environments with real worktrees and processes."""
    runtime_root = runtime_root.resolve()
    workspace_root = runtime_root / "smoke-workspace"
    smoke_db_path = (db_path or (runtime_root / "runtime_smoke.db")).resolve()
    repo_root = config_module.SCRIPT_DIR.resolve()
    browser_requested = include_browser_live
    prerequisites = detect_runtime_smoke_prerequisites()
    suggested_actions = runtime_smoke_suggested_actions(prerequisites)
    browser_eligible = (
        browser_requested and prerequisites["playwright_python_available"] and prerequisites["playwright_browser_ready"]
    )
    try:
        require_primary_state_backend(error="runtime_smoke_primary_backend_unavailable")
    except RuntimeError as exc:
        return {
            "ok": False,
            "runtime_root": str(runtime_root),
            "database_path": str(smoke_db_path),
            "prerequisites": prerequisites,
            "suggested_actions": suggested_actions,
            "error": str(exc),
        }
    forbidden_paths = [
        str(candidate)
        for candidate in (runtime_root, workspace_root, smoke_db_path)
        if _is_within(candidate, repo_root)
    ]
    if forbidden_paths:
        return {
            "ok": False,
            "runtime_root": str(runtime_root),
            "database_path": str(smoke_db_path),
            "repo_root": str(repo_root),
            "forbidden_paths": forbidden_paths,
            "prerequisites": prerequisites,
            "suggested_actions": suggested_actions,
            "error": "runtime_smoke_repo_root_residue_forbidden",
        }
    if require_browser_live and not browser_eligible:
        return {
            "ok": False,
            "runtime_root": str(runtime_root),
            "database_path": str(smoke_db_path),
            "prerequisites": prerequisites,
            "suggested_actions": suggested_actions,
            "error": "browser live prerequisites are not satisfied on this machine",
        }

    runtime_root.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    init_smoke_git_repo(workspace_root)

    shell_path = shell or os.environ.get("SHELL") or "/bin/bash"
    with contextlib.nullcontext():
        controller = RuntimeController(runtime_root=runtime_root)
        try:
            await controller.start()

            task_specs: list[tuple[str, str, bool]] = [
                ("Implement and test runtime smoke alpha", "alpha", False),
                ("Implement and test runtime smoke beta", "beta", False),
            ]
            if browser_requested:
                task_specs.append(("Open a browser and validate runtime smoke gamma", "gamma", True))

            async def _run_task(query_text: str, marker: str, expect_browser: bool) -> dict[str, Any]:
                task_id = create_task(
                    user_id=111,
                    chat_id=222,
                    query_text=query_text,
                    provider="claude",
                    model="claude-sonnet",
                    work_dir=str(workspace_root),
                )
                await controller.register_queued_task(task_id=task_id, user_id=111, chat_id=222, query_text=query_text)
                classification = await controller.classify_task(task_id=task_id, query_text=query_text)
                env = await controller.provision_environment(
                    task_id=task_id,
                    user_id=111,
                    chat_id=222,
                    query_text=query_text,
                    base_work_dir=str(workspace_root),
                    classification=classification,
                )
                if env is None:
                    raise RuntimeError(f"runtime environment was not provisioned for task {task_id}")
                env_id = int(env["id"])
                workspace_path = Path(str(env["workspace_path"]))
                marker_path = workspace_path / f"{marker}.txt"
                marker_path.write_text(marker, encoding="utf-8")

                await controller.mark_phase(task_id=task_id, env_id=env_id, phase="executing")
                await controller.heartbeat(task_id=task_id, env_id=env_id, phase="executing")
                await controller.record_decision(
                    task_id=task_id,
                    decision={"action": "runtime_smoke_started", "marker": marker, "expect_browser": expect_browser},
                )
                await controller.record_loop_cycle(
                    task_id=task_id,
                    cycle_index=1,
                    phase="executing",
                    goal=f"verify isolated runtime for {marker}",
                    plan={"steps": ["write marker", "sample resources", "checkpoint"]},
                    hypothesis=f"marker={marker}",
                    outcome={"status": "running"},
                )

                proc = await asyncio.create_subprocess_exec("sleep", "2", start_new_session=True)
                await controller.record_process(
                    task_id=task_id,
                    command="sleep 2",
                    proc=proc,
                    role="smoke_service",
                    process_kind="service",
                    track_as_primary=False,
                )
                await controller.heartbeat(task_id=task_id, env_id=env_id, phase="executing")

                terminal = await controller.start_operator_terminal(
                    task_id=task_id,
                    actor="runtime_smoke",
                    shell=shell_path,
                )
                terminal_log_ready = False
                terminal_log_path = ""
                if terminal is not None:
                    terminal_id = int(terminal["id"])
                    terminal_log_path = str(terminal["path"])
                    await controller.write_terminal_input(
                        task_id=task_id,
                        terminal_id=terminal_id,
                        text=f"printf 'runtime-smoke-{marker}\\n'; pwd; exit\n",
                    )
                    terminal_log_ready = await _wait_for_terminal_log(Path(terminal_log_path))
                    await controller.close_terminal_session(task_id=task_id, terminal_id=terminal_id, force=True)

                browser_snapshot: dict[str, Any] = {}
                browser_verified = False
                screenshot_path = ""
                if expect_browser:
                    env = await controller.ensure_environment_live_resources(task_id=task_id, env_id=env_id) or env
                    browser_snapshot = controller.get_browser_snapshot(task_id)
                    if str(browser_snapshot.get("status") or "") == "running":
                        scope_id = int(browser_snapshot.get("scope_id") or task_id)
                        browser_test_url = (
                            f"data:text/html,<html><body><h1>{marker}</h1><p>runtime smoke</p></body></html>"
                        )
                        await browser_manager.navigate(
                            scope_id,
                            browser_test_url,
                        )
                        screenshot_result = await browser_manager.screenshot_to_file(scope_id, full_page=True)
                        browser_snapshot = controller.get_browser_snapshot(task_id)
                        if not screenshot_result.startswith("Error"):
                            screenshot_path = screenshot_result
                            await controller.add_artifact(
                                task_id=task_id,
                                artifact_kind="browser_screenshot",
                                label=f"{marker} browser screenshot",
                                path=screenshot_result,
                            )
                            browser_url = str(browser_snapshot.get("url") or "").strip().lower()
                            browser_verified = (
                                Path(screenshot_result).exists()
                                and browser_url not in {"", "about:blank"}
                                and marker.lower() in browser_url
                            )
                    elif require_browser_live:
                        raise RuntimeError(f"browser live could not be verified for task {task_id}")

                process_rows = controller.store.list_processes(task_id)
                smoke_process = next(
                    (
                        row
                        for row in process_rows
                        if int(row.get("pid") or 0) == int(proc.pid) and str(row.get("role") or "") == "smoke_service"
                    ),
                    None,
                )
                if smoke_process is not None:
                    await controller.terminate_process(process_id=int(smoke_process["id"]), force=True)
                else:
                    proc.terminate()
                    await proc.wait()

                await controller.record_loop_cycle(
                    task_id=task_id,
                    cycle_index=2,
                    phase="validating",
                    goal=f"finalize runtime smoke for {marker}",
                    validations=[
                        {"name": "marker_file", "ok": marker_path.exists()},
                        {"name": "terminal_log_ready", "ok": terminal_log_ready},
                    ],
                    outcome={"status": "validated"},
                )
                await controller.finalize_task(task_id=task_id, success=True, summary={"marker": marker, "smoke": True})

                events = controller.store.list_events(task_id=task_id)
                checkpoints = controller.store.list_checkpoints(task_id)
                artifacts = controller.store.list_artifacts(task_id)
                resources = controller.store.list_resource_samples(task_id)
                env_after = controller.store.get_environment_by_task(task_id)
                task_root = runtime_root / "tasks" / str(task_id)
                return {
                    "task_id": task_id,
                    "marker": marker,
                    "expect_browser": expect_browser,
                    "classification": classification.classification,
                    "environment_kind": classification.environment_kind,
                    "workspace_path": str(workspace_path),
                    "worktree_created": bool(env_after and env_after.get("created_worktree")),
                    "final_phase": str(env_after.get("current_phase") or "") if env_after else "",
                    "browser_verified": browser_verified,
                    "browser_snapshot": browser_snapshot,
                    "browser_screenshot_path": screenshot_path,
                    "terminal_log_path": terminal_log_path,
                    "terminal_log_ready": terminal_log_ready,
                    "events_count": len(events),
                    "event_types": [str(event.get("type") or "") for event in events],
                    "checkpoints_count": len(checkpoints),
                    "artifacts_count": len(artifacts),
                    "resource_samples_count": len(resources),
                    "task_root": str(task_root),
                    "events_log_exists": (task_root / "events.ndjson").exists(),
                    "loop_cycles_exists": (task_root / "loop_cycles.jsonl").exists(),
                    "marker_file_exists": marker_path.exists(),
                }

            task_results = await asyncio.gather(*(_run_task(*spec) for spec in task_specs))
            return {
                "ok": True,
                "runtime_root": str(runtime_root),
                "database_path": str(smoke_db_path),
                "prerequisites": prerequisites,
                "suggested_actions": suggested_actions,
                "browser_requested": browser_requested,
                "browser_eligible": browser_eligible,
                "browser_started": browser_eligible,
                "runtime_readiness": controller.get_runtime_readiness(),
                "runtime_snapshot": controller.get_runtime_snapshot(),
                "tasks": task_results,
            }
        finally:
            with contextlib.suppress(Exception):
                await browser_manager.stop()
            await controller.stop()
