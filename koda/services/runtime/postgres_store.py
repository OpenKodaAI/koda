"""Postgres-backed runtime persistence for primary mode."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast

from koda.config import AGENT_ID
from koda.services.provider_env import validate_runtime_path
from koda.services.runtime.redaction import redact_json_dumps, redact_value
from koda.state_primary import (
    primary_execute,
    primary_fetch_all,
    primary_fetch_one,
    primary_fetch_val,
    run_coro_sync,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _agent_scope() -> str:
    normalized = (AGENT_ID or "default").strip().lower()
    return normalized or "default"


def _redacted_json(value: Any) -> Any:
    return json.loads(redact_json_dumps(value))


def _validated_path(value: str | None, *, allow_empty: bool = False) -> str | None:
    if value is None:
        return None
    return validate_runtime_path(value, allow_empty=allow_empty)


def _redacted_text(value: str | None) -> str | None:
    if value is None:
        return None
    return str(redact_value(value))


class PostgresRuntimeStore:
    """Data access layer for runtime state backed by the primary Postgres store."""

    def __init__(self) -> None:
        self._agent_scope = _agent_scope()

    def _execute(self, query: str, params: Iterable[Any] = ()) -> int:
        return int(run_coro_sync(primary_execute(query, tuple(params), agent_id=self._agent_scope)) or 0)

    def _fetch_one(self, query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        return cast(
            dict[str, Any] | None,
            run_coro_sync(primary_fetch_one(query, tuple(params), agent_id=self._agent_scope)),
        )

    def _fetch_all(self, query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return list(run_coro_sync(primary_fetch_all(query, tuple(params), agent_id=self._agent_scope)) or [])

    def _fetch_val(self, query: str, params: Iterable[Any] = ()) -> Any:
        return run_coro_sync(primary_fetch_val(query, tuple(params), agent_id=self._agent_scope))

    def upsert_runtime_queue_item(
        self,
        *,
        task_id: int,
        user_id: int,
        chat_id: int,
        query_text: str,
        queue_name: str = "user",
        status: str = "queued",
    ) -> None:
        now = _now()
        self._execute(
            """
            INSERT INTO runtime_queue_items (
                agent_id, task_id, user_id, chat_id, queue_name, status, query_text, queued_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, task_id) DO UPDATE SET
                status = EXCLUDED.status,
                query_text = EXCLUDED.query_text,
                updated_at = EXCLUDED.updated_at
            """,
            (self._agent_scope, task_id, user_id, chat_id, queue_name, status, query_text, now, now),
        )

    def update_runtime_queue_item(self, task_id: int, *, status: str, queue_position: int | None = None) -> None:
        sets = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, _now()]
        if queue_position is not None:
            sets.append("queue_position = ?")
            values.append(queue_position)
        values.extend([self._agent_scope, task_id])
        self._execute(f"UPDATE runtime_queue_items SET {', '.join(sets)} WHERE agent_id = ? AND task_id = ?", values)

    def create_environment(
        self,
        *,
        task_id: int,
        user_id: int,
        chat_id: int,
        classification: str,
        environment_kind: str,
        isolation: str,
        duration: str,
        workspace_path: str,
        runtime_dir: str,
        base_work_dir: str,
        branch_name: str | None,
        created_worktree: bool,
        worktree_mode: str,
        current_phase: str,
        parent_env_id: int | None = None,
        lineage_root_env_id: int | None = None,
        source_checkpoint_id: int | None = None,
        recovery_state: str = "",
        revision: int = 1,
        browser_transport: str | None = None,
        display_id: int | None = None,
        vnc_port: int | None = None,
        novnc_port: int | None = None,
    ) -> int:
        now = _now()
        env_id = self._fetch_val(
            """
            INSERT INTO runtime_environments (
                agent_id, task_id, user_id, chat_id, classification, environment_kind, isolation, duration,
                status, current_phase, workspace_path, runtime_dir, base_work_dir, branch_name,
                created_worktree, worktree_mode, parent_env_id, lineage_root_env_id, source_checkpoint_id,
                recovery_state, revision, browser_transport, display_id, vnc_port, novnc_port,
                created_at, updated_at, last_heartbeat_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                user_id,
                chat_id,
                classification,
                environment_kind,
                isolation,
                duration,
                "active",
                current_phase,
                _validated_path(workspace_path),
                _validated_path(runtime_dir),
                _validated_path(base_work_dir),
                branch_name,
                created_worktree,
                worktree_mode,
                parent_env_id,
                lineage_root_env_id,
                source_checkpoint_id,
                recovery_state,
                revision,
                browser_transport or "",
                display_id,
                vnc_port,
                novnc_port,
                now,
                now,
                now,
            ),
        )
        self._execute(
            """
            UPDATE tasks
            SET env_id = ?, classification = ?, environment_kind = ?, current_phase = ?, last_heartbeat_at = ?
            WHERE agent_id = ? AND id = ?
            """,
            (env_id, classification, environment_kind, current_phase, now, self._agent_scope, task_id),
        )
        return int(env_id)

    def update_environment(
        self,
        env_id: int,
        *,
        status: str | None = None,
        current_phase: str | None = None,
        retention_expires_at: str | None = None,
        pinned: bool | None = None,
        checkpoint_status: str | None = None,
        checkpoint_path: str | None = None,
        branch_name: str | None = None,
        workspace_path: str | None = None,
        runtime_dir: str | None = None,
        base_work_dir: str | None = None,
        created_worktree: bool | None = None,
        worktree_mode: str | None = None,
        parent_env_id: int | None = None,
        lineage_root_env_id: int | None = None,
        source_checkpoint_id: int | None = None,
        recovery_state: str | None = None,
        revision: int | None = None,
        browser_transport: str | None = None,
        display_id: int | None = None,
        vnc_port: int | None = None,
        novnc_port: int | None = None,
        pause_state: str | None = None,
        pause_reason: str | None = None,
        save_verified_at: str | None = None,
        process_pid: int | None = None,
        process_pgid: int | None = None,
        browser_scope_id: int | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?", "last_heartbeat_at = ?"]
        values: list[Any] = [_now(), _now()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if current_phase is not None:
            fields.append("current_phase = ?")
            values.append(current_phase)
        if retention_expires_at is not None:
            fields.append("retention_expires_at = ?")
            values.append(retention_expires_at)
        if pinned is not None:
            fields.append("is_pinned = ?")
            values.append(pinned)
        if checkpoint_status is not None:
            fields.append("checkpoint_status = ?")
            values.append(checkpoint_status)
        if checkpoint_path is not None:
            fields.append("checkpoint_path = ?")
            values.append(_validated_path(checkpoint_path))
        if branch_name is not None:
            fields.append("branch_name = ?")
            values.append(branch_name)
        if workspace_path is not None:
            fields.append("workspace_path = ?")
            values.append(_validated_path(workspace_path))
        if runtime_dir is not None:
            fields.append("runtime_dir = ?")
            values.append(_validated_path(runtime_dir))
        if base_work_dir is not None:
            fields.append("base_work_dir = ?")
            values.append(_validated_path(base_work_dir))
        if created_worktree is not None:
            fields.append("created_worktree = ?")
            values.append(created_worktree)
        if worktree_mode is not None:
            fields.append("worktree_mode = ?")
            values.append(worktree_mode)
        if parent_env_id is not None:
            fields.append("parent_env_id = ?")
            values.append(parent_env_id)
        if lineage_root_env_id is not None:
            fields.append("lineage_root_env_id = ?")
            values.append(lineage_root_env_id)
        if source_checkpoint_id is not None:
            fields.append("source_checkpoint_id = ?")
            values.append(source_checkpoint_id)
        if recovery_state is not None:
            fields.append("recovery_state = ?")
            values.append(recovery_state)
        if revision is not None:
            fields.append("revision = ?")
            values.append(revision)
        if browser_transport is not None:
            fields.append("browser_transport = ?")
            values.append(browser_transport)
        if display_id is not None:
            fields.append("display_id = ?")
            values.append(display_id)
        if vnc_port is not None:
            fields.append("vnc_port = ?")
            values.append(vnc_port)
        if novnc_port is not None:
            fields.append("novnc_port = ?")
            values.append(novnc_port)
        if pause_state is not None:
            fields.append("pause_state = ?")
            values.append(pause_state)
        if pause_reason is not None:
            fields.append("pause_reason = ?")
            values.append(pause_reason)
        if save_verified_at is not None:
            fields.append("save_verified_at = ?")
            values.append(save_verified_at)
        if process_pid is not None:
            fields.append("process_pid = ?")
            values.append(process_pid)
        if process_pgid is not None:
            fields.append("process_pgid = ?")
            values.append(process_pgid)
        if browser_scope_id is not None:
            fields.append("browser_scope_id = ?")
            values.append(browser_scope_id)
        values.extend([self._agent_scope, env_id])
        self._execute(f"UPDATE runtime_environments SET {', '.join(fields)} WHERE agent_id = ? AND id = ?", values)

    def update_task_runtime(
        self,
        task_id: int,
        *,
        status: str | None = None,
        phase: str | None = None,
        retention_expires_at: str | None = None,
        env_id: int | None = None,
        classification: str | None = None,
        environment_kind: str | None = None,
        error_message: str | None = None,
        source_task_id: int | None = None,
        source_action: str | None = None,
    ) -> None:
        fields = ["last_heartbeat_at = ?"]
        values: list[Any] = [_now()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if phase is not None:
            fields.append("current_phase = ?")
            values.append(phase)
        if retention_expires_at is not None:
            fields.append("retention_expires_at = ?")
            values.append(retention_expires_at)
        if env_id is not None:
            fields.append("env_id = ?")
            values.append(env_id)
        if classification is not None:
            fields.append("classification = ?")
            values.append(classification)
        if environment_kind is not None:
            fields.append("environment_kind = ?")
            values.append(environment_kind)
        if error_message is not None:
            fields.append("error_message = ?")
            values.append(_redacted_text(error_message))
        if source_task_id is not None:
            fields.append("source_task_id = ?")
            values.append(source_task_id)
        if source_action is not None:
            fields.append("source_action = ?")
            values.append(source_action)
        values.extend([self._agent_scope, task_id])
        self._execute(f"UPDATE tasks SET {', '.join(fields)} WHERE agent_id = ? AND id = ?", values)

    def heartbeat(self, task_id: int, env_id: int | None, *, phase: str | None = None) -> None:
        now = _now()
        self._execute(
            "UPDATE tasks SET last_heartbeat_at = ?, current_phase = COALESCE(?, current_phase) "
            "WHERE agent_id = ? AND id = ?",
            (now, phase, self._agent_scope, task_id),
        )
        if env_id is not None:
            self._execute(
                "UPDATE runtime_environments SET last_heartbeat_at = ?, "
                "current_phase = COALESCE(?, current_phase), updated_at = ? "
                "WHERE agent_id = ? AND id = ?",
                (now, phase, now, self._agent_scope, env_id),
            )

    def add_event(
        self,
        *,
        task_id: int | None,
        env_id: int | None,
        attempt: int | None,
        phase: str | None,
        event_type: str,
        severity: str,
        payload: dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        resource_snapshot_ref: str | None = None,
    ) -> dict[str, Any]:
        payload_data = _redacted_json(payload or {})
        artifact_refs_data = list(artifact_refs or [])
        created_at = _now()
        seq = self._fetch_val(
            """
            INSERT INTO runtime_events (
                agent_id, task_id, env_id, attempt, phase, event_type, severity, payload_json,
                artifact_refs_json, resource_snapshot_ref, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                attempt,
                phase,
                event_type,
                severity,
                payload_data,
                artifact_refs_data,
                resource_snapshot_ref,
                created_at,
            ),
        )
        return {
            "seq": int(seq),
            "ts": created_at,
            "task_id": task_id,
            "env_id": env_id,
            "attempt": attempt,
            "phase": phase,
            "type": event_type,
            "severity": severity,
            "payload": payload_data,
            "artifact_refs": artifact_refs_data,
            "resource_snapshot_ref": resource_snapshot_ref,
        }

    def add_artifact(
        self,
        *,
        task_id: int,
        env_id: int | None,
        artifact_kind: str,
        label: str,
        path: str,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> int:
        artifact_id = self._fetch_val(
            """
            INSERT INTO runtime_artifacts (
                agent_id, task_id, env_id, artifact_kind, label, path, metadata_json, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                artifact_kind,
                label,
                _validated_path(path),
                _redacted_json(metadata or {}),
                _now(),
                expires_at,
            ),
        )
        return int(artifact_id)

    def add_checkpoint(
        self,
        *,
        task_id: int,
        env_id: int,
        status: str,
        checkpoint_dir: str,
        manifest_path: str,
        patch_path: str,
        commit_sha: str | None,
        expires_at: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        checkpoint_id = self._fetch_val(
            """
            INSERT INTO runtime_checkpoints (
                agent_id, task_id, env_id, status, checkpoint_dir, manifest_path, patch_path, commit_sha,
                metadata_json, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                status,
                _validated_path(checkpoint_dir),
                _validated_path(manifest_path),
                _validated_path(patch_path),
                commit_sha,
                _redacted_json(metadata or {}),
                _now(),
                expires_at,
            ),
        )
        return int(checkpoint_id)

    def add_warning(
        self,
        *,
        task_id: int,
        env_id: int | None,
        warning_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> int:
        warning_id = self._fetch_val(
            """
            INSERT INTO runtime_warnings (
                agent_id, task_id, env_id, warning_type, message, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                warning_type,
                _redacted_text(message),
                _redacted_json(details or {}),
                _now(),
            ),
        )
        return int(warning_id)

    def add_resource_sample(
        self,
        *,
        task_id: int,
        env_id: int | None,
        cpu_percent: float | None,
        rss_kb: float | None,
        process_count: int | None,
        workspace_disk_bytes: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        sample_id = self._fetch_val(
            """
            INSERT INTO runtime_resource_samples (
                agent_id, task_id, env_id, cpu_percent, rss_kb, process_count, workspace_disk_bytes,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                cpu_percent,
                rss_kb,
                process_count,
                workspace_disk_bytes,
                _redacted_json(metadata or {}),
                _now(),
            ),
        )
        return int(sample_id)

    def upsert_process(
        self,
        *,
        task_id: int,
        env_id: int | None,
        pid: int,
        pgid: int | None,
        parent_pid: int | None = None,
        role: str,
        command: str,
        process_kind: str = "service",
        status: str = "running",
    ) -> int:
        existing = self._fetch_one(
            """
            SELECT id FROM runtime_processes
            WHERE agent_id = ? AND task_id = ? AND COALESCE(env_id, 0) = COALESCE(?, 0)
              AND pid = ? AND role = ? AND process_kind = ?
            ORDER BY id DESC LIMIT 1
            """,
            (self._agent_scope, task_id, env_id, pid, role, process_kind),
        )
        now = _now()
        if existing is not None:
            process_id = int(existing["id"])
            self._execute(
                """
                UPDATE runtime_processes
                SET pgid = ?, parent_pid = ?, command = ?, status = ?, updated_at = ?
                WHERE agent_id = ? AND id = ?
                """,
                (pgid, parent_pid, _redacted_text(command), status, now, self._agent_scope, process_id),
            )
            return process_id
        process_id = self._fetch_val(
            """
            INSERT INTO runtime_processes (
                agent_id, task_id, env_id, pid, pgid, parent_pid, role, process_kind, command, status,
                started_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                pid,
                pgid,
                parent_pid,
                role,
                process_kind,
                _redacted_text(command),
                status,
                now,
                now,
            ),
        )
        return int(process_id)

    def update_process(
        self,
        process_id: int,
        *,
        status: str | None = None,
        exit_code: int | None = None,
        parent_pid: int | None = None,
        pgid: int | None = None,
        pid: int | None = None,
        exited: bool = False,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [_now()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if exit_code is not None:
            fields.append("exit_code = ?")
            values.append(exit_code)
        if parent_pid is not None:
            fields.append("parent_pid = ?")
            values.append(parent_pid)
        if pgid is not None:
            fields.append("pgid = ?")
            values.append(pgid)
        if pid is not None:
            fields.append("pid = ?")
            values.append(pid)
        if exited:
            fields.append("exited_at = ?")
            values.append(_now())
        values.extend([self._agent_scope, process_id])
        self._execute(f"UPDATE runtime_processes SET {', '.join(fields)} WHERE agent_id = ? AND id = ?", values)

    def list_processes(self, task_id: int, *, env_id: int | None = None) -> list[dict[str, Any]]:
        query = (
            "SELECT id, task_id, env_id, pid, pgid, parent_pid, role, process_kind, command, status, "
            "exit_code, started_at, updated_at, exited_at FROM runtime_processes WHERE agent_id = ? AND task_id = ?"
        )
        params: list[Any] = [self._agent_scope, task_id]
        if env_id is not None:
            query += " AND env_id = ?"
            params.append(env_id)
        query += " ORDER BY id ASC"
        return self._fetch_all(query, params)

    def get_process_by_pid(self, pid: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT id, task_id, env_id, pid, pgid, parent_pid, role, process_kind, command, status,
                   exit_code, started_at, updated_at, exited_at
            FROM runtime_processes WHERE agent_id = ? AND pid = ? ORDER BY id DESC LIMIT 1
            """,
            (self._agent_scope, pid),
        )

    def get_process(self, process_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT id, task_id, env_id, pid, pgid, parent_pid, role, process_kind, command, status,
                   exit_code, started_at, updated_at, exited_at
            FROM runtime_processes WHERE agent_id = ? AND id = ? ORDER BY id DESC LIMIT 1
            """,
            (self._agent_scope, process_id),
        )

    def upsert_terminal(
        self,
        *,
        task_id: int,
        env_id: int | None,
        terminal_kind: str,
        label: str,
        path: str,
        stream_path: str | None = None,
        interactive: bool = False,
        cursor_offset: int = 0,
        last_offset: int = 0,
    ) -> int:
        now = _now()
        terminal_id = self._fetch_val(
            """
            INSERT INTO runtime_terminals (
                agent_id, task_id, env_id, terminal_kind, label, path, stream_path, interactive, cursor_offset,
                last_offset, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                terminal_kind,
                label,
                _validated_path(path),
                _validated_path(stream_path, allow_empty=True),
                interactive,
                cursor_offset,
                last_offset,
                now,
                now,
            ),
        )
        return int(terminal_id)

    def update_terminal(
        self,
        terminal_id: int,
        *,
        cursor_offset: int | None = None,
        last_offset: int | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [_now()]
        if cursor_offset is not None:
            fields.append("cursor_offset = ?")
            values.append(cursor_offset)
        if last_offset is not None:
            fields.append("last_offset = ?")
            values.append(last_offset)
        values.extend([self._agent_scope, terminal_id])
        self._execute(f"UPDATE runtime_terminals SET {', '.join(fields)} WHERE agent_id = ? AND id = ?", values)

    def add_recovery_action(
        self,
        *,
        task_id: int,
        env_id: int | None,
        action: str,
        status: str,
        checkpoint_id: int | None = None,
        new_task_id: int | None = None,
        new_env_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> int:
        action_id = self._fetch_val(
            """
            INSERT INTO runtime_recovery_actions (
                agent_id, task_id, env_id, action, status, checkpoint_id, new_task_id, new_env_id, details_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                action,
                status,
                checkpoint_id,
                new_task_id,
                new_env_id,
                _redacted_json(details or {}),
                _now(),
            ),
        )
        return int(action_id)

    def add_browser_session(
        self,
        *,
        task_id: int,
        env_id: int | None,
        scope_id: int,
        transport: str,
        status: str,
        display_id: int | None,
        vnc_port: int | None,
        novnc_port: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = _now()
        session_id = self._fetch_val(
            """
            INSERT INTO runtime_browser_sessions (
                agent_id, task_id, env_id, scope_id, transport, status, display_id, vnc_port, novnc_port,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                scope_id,
                transport,
                status,
                display_id,
                vnc_port,
                novnc_port,
                _redacted_json(metadata or {}),
                now,
                now,
            ),
        )
        return int(session_id)

    def update_browser_session(
        self,
        session_id: int,
        *,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        ended: bool = False,
    ) -> None:
        fields = ["updated_at = ?"]
        values: list[Any] = [_now()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if metadata is not None:
            fields.append("metadata_json = ?")
            values.append(_redacted_json(metadata))
        if ended:
            fields.append("ended_at = ?")
            values.append(_now())
        values.extend([self._agent_scope, session_id])
        self._execute(f"UPDATE runtime_browser_sessions SET {', '.join(fields)} WHERE agent_id = ? AND id = ?", values)

    def list_browser_sessions(self, task_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, scope_id, transport, status, display_id, vnc_port, novnc_port,
                   metadata_json, created_at, updated_at, ended_at
            FROM runtime_browser_sessions WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )
        return [{**row, "metadata": dict(row.pop("metadata_json") or {})} for row in rows]

    def add_service_endpoint(
        self,
        *,
        task_id: int,
        env_id: int | None,
        process_id: int | None,
        service_kind: str,
        label: str,
        host: str,
        port: int,
        protocol: str = "tcp",
        status: str = "active",
        url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = _now()
        endpoint_id = self._fetch_val(
            """
            INSERT INTO runtime_service_endpoints (
                agent_id, task_id, env_id, process_id, service_kind, label, host, port, protocol, status, url,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                process_id,
                service_kind,
                label,
                host,
                port,
                protocol,
                status,
                url or "",
                _redacted_json(metadata or {}),
                now,
                now,
            ),
        )
        return int(endpoint_id)

    def update_service_endpoint(
        self,
        endpoint_id: int,
        *,
        process_id: int | None = None,
        status: str | None = None,
        url: str | None = None,
        metadata: dict[str, Any] | None = None,
        ended: bool = False,
    ) -> None:
        fields = ["updated_at = ?"]
        values: list[Any] = [_now()]
        if process_id is not None:
            fields.append("process_id = ?")
            values.append(process_id)
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if url is not None:
            fields.append("url = ?")
            values.append(url)
        if metadata is not None:
            fields.append("metadata_json = ?")
            values.append(_redacted_json(metadata))
        if ended:
            fields.append("ended_at = ?")
            values.append(_now())
        values.extend([self._agent_scope, endpoint_id])
        self._execute(f"UPDATE runtime_service_endpoints SET {', '.join(fields)} WHERE agent_id = ? AND id = ?", values)

    def list_service_endpoints(self, task_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, process_id, service_kind, label, host, port, protocol, status, url,
                   metadata_json, created_at, updated_at, ended_at
            FROM runtime_service_endpoints WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )
        return [{**row, "metadata": dict(row.pop("metadata_json") or {})} for row in rows]

    def add_port_allocation(
        self,
        *,
        task_id: int,
        env_id: int | None,
        purpose: str,
        host: str,
        port: int,
        status: str = "allocated",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = _now()
        allocation_id = self._fetch_val(
            """
            INSERT INTO runtime_port_allocations (
                agent_id, task_id, env_id, purpose, host, port, status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (self._agent_scope, task_id, env_id, purpose, host, port, status, _redacted_json(metadata or {}), now, now),
        )
        return int(allocation_id)

    def update_port_allocation(
        self,
        allocation_id: int,
        *,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        released: bool = False,
    ) -> None:
        fields = ["updated_at = ?"]
        values: list[Any] = [_now()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if metadata is not None:
            fields.append("metadata_json = ?")
            values.append(_redacted_json(metadata))
        if released:
            fields.append("released_at = ?")
            values.append(_now())
        values.extend([self._agent_scope, allocation_id])
        self._execute(f"UPDATE runtime_port_allocations SET {', '.join(fields)} WHERE agent_id = ? AND id = ?", values)

    def list_port_allocations(self, task_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, purpose, host, port, status, metadata_json, created_at, updated_at,
                   released_at
            FROM runtime_port_allocations WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )
        return [{**row, "metadata": dict(row.pop("metadata_json") or {})} for row in rows]

    def is_port_allocated(self, host: str, port: int) -> bool:
        return bool(
            self._fetch_one(
                """
                SELECT 1 AS allocated FROM runtime_port_allocations
                WHERE agent_id = ? AND host = ? AND port = ? AND status IN ('allocated', 'active')
                ORDER BY id DESC LIMIT 1
                """,
                (self._agent_scope, host, port),
            )
        )

    def add_loop_cycle(
        self,
        *,
        task_id: int,
        env_id: int | None,
        cycle_index: int,
        phase: str,
        goal: str = "",
        plan: dict[str, Any] | None = None,
        hypothesis: str = "",
        command_fingerprint: str = "",
        diff_hash: str = "",
        failure_fingerprint: str = "",
        validations: list[dict[str, Any]] | None = None,
        outcome: dict[str, Any] | None = None,
    ) -> int:
        cycle_id = self._fetch_val(
            """
            INSERT INTO runtime_loop_cycles (
                agent_id, task_id, env_id, cycle_index, phase, goal, plan_json, hypothesis, command_fingerprint,
                diff_hash, failure_fingerprint, validations_json, outcome_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                cycle_index,
                phase,
                goal,
                _redacted_json(plan or {}),
                hypothesis,
                command_fingerprint,
                diff_hash,
                failure_fingerprint,
                _redacted_json(validations or []),
                _redacted_json(outcome or {}),
                _now(),
            ),
        )
        return int(cycle_id)

    def list_loop_cycles(self, task_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, cycle_index, phase, goal, plan_json, hypothesis, command_fingerprint,
                   diff_hash, failure_fingerprint, validations_json, outcome_json, created_at
            FROM runtime_loop_cycles WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )
        return [
            {
                **row,
                "plan": dict(row.pop("plan_json") or {}),
                "validations": list(row.pop("validations_json") or []),
                "outcome": dict(row.pop("outcome_json") or {}),
            }
            for row in rows
        ]

    def add_guardrail_hit(
        self,
        *,
        task_id: int,
        env_id: int | None,
        cycle_id: int | None,
        guardrail_type: str,
        details: dict[str, Any] | None = None,
    ) -> int:
        hit_id = self._fetch_val(
            """
            INSERT INTO runtime_guardrail_hits (
                agent_id, task_id, env_id, cycle_id, guardrail_type, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (self._agent_scope, task_id, env_id, cycle_id, guardrail_type, _redacted_json(details or {}), _now()),
        )
        return int(hit_id)

    def list_guardrail_hits(self, task_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, cycle_id, guardrail_type, details_json, created_at
            FROM runtime_guardrail_hits WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )
        return [{**row, "details": dict(row.pop("details_json") or {})} for row in rows]

    def create_attach_session(
        self,
        *,
        task_id: int,
        env_id: int | None,
        attach_kind: str,
        terminal_id: int | None,
        token: str,
        can_write: bool,
        actor: str,
        expires_at: str,
    ) -> int:
        now = _now()
        session_id = self._fetch_val(
            """
            INSERT INTO runtime_attach_sessions (
                agent_id, task_id, env_id, attach_kind, terminal_id, token, can_write, actor, status, expires_at,
                created_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                self._agent_scope,
                task_id,
                env_id,
                attach_kind,
                terminal_id,
                token,
                can_write,
                actor,
                "active",
                expires_at,
                now,
                now,
            ),
        )
        return int(session_id)

    def touch_attach_session(self, token: str) -> dict[str, Any] | None:
        now = _now()
        self._execute(
            "UPDATE runtime_attach_sessions SET last_seen_at = ? WHERE agent_id = ? AND token = ?",
            (now, self._agent_scope, token),
        )
        return self._fetch_one(
            """
            SELECT id, task_id, env_id, attach_kind, terminal_id, token, can_write, actor, status, expires_at,
                   created_at, last_seen_at, ended_at
            FROM runtime_attach_sessions WHERE agent_id = ? AND token = ?
            """,
            (self._agent_scope, token),
        )

    def close_attach_session(self, token: str) -> None:
        now = _now()
        self._execute(
            "UPDATE runtime_attach_sessions SET status = 'closed', ended_at = ?, last_seen_at = ? "
            "WHERE agent_id = ? AND token = ?",
            (now, now, self._agent_scope, token),
        )

    def list_attach_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT id, task_id, env_id, attach_kind, terminal_id, token, can_write, actor, status, expires_at,
                   created_at, last_seen_at, ended_at
            FROM runtime_attach_sessions WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )

    def list_runtime_queues(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT task_id, user_id, chat_id, queue_name, status, queue_position, query_text, queued_at, updated_at
            FROM runtime_queue_items
            WHERE agent_id = ?
            ORDER BY queued_at ASC
            """,
            (self._agent_scope,),
        )

    def list_environments(self) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT id, task_id, user_id, chat_id, classification, environment_kind, isolation, duration,
                   status, current_phase, workspace_path, runtime_dir, base_work_dir, branch_name,
                   created_worktree, worktree_mode, is_pinned, checkpoint_status, checkpoint_path, parent_env_id,
                   lineage_root_env_id, source_checkpoint_id, recovery_state, revision,
                   browser_transport, display_id, vnc_port, novnc_port,
                   pause_state, pause_reason, save_verified_at, process_pid, process_pgid, browser_scope_id,
                   created_at, updated_at, last_heartbeat_at, retention_expires_at
            FROM runtime_environments
            WHERE agent_id = ?
            ORDER BY id DESC
            """,
            (self._agent_scope,),
        )

    def get_environment(self, env_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT id, task_id, user_id, chat_id, classification, environment_kind, isolation, duration,
                   status, current_phase, workspace_path, runtime_dir, base_work_dir, branch_name,
                   created_worktree, worktree_mode, is_pinned, checkpoint_status, checkpoint_path, parent_env_id,
                   lineage_root_env_id, source_checkpoint_id, recovery_state, revision,
                   browser_transport, display_id, vnc_port, novnc_port,
                   pause_state, pause_reason, save_verified_at, process_pid, process_pgid, browser_scope_id,
                   created_at, updated_at, last_heartbeat_at, retention_expires_at
            FROM runtime_environments
            WHERE agent_id = ? AND id = ?
            """,
            (self._agent_scope, env_id),
        )

    def get_environment_by_task(self, task_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT id, task_id, user_id, chat_id, classification, environment_kind, isolation, duration,
                   status, current_phase, workspace_path, runtime_dir, base_work_dir, branch_name,
                   created_worktree, worktree_mode, is_pinned, checkpoint_status, checkpoint_path, parent_env_id,
                   lineage_root_env_id, source_checkpoint_id, recovery_state, revision,
                   browser_transport, display_id, vnc_port, novnc_port,
                   pause_state, pause_reason, save_verified_at, process_pid, process_pgid, browser_scope_id,
                   created_at, updated_at, last_heartbeat_at, retention_expires_at
            FROM runtime_environments
            WHERE agent_id = ? AND task_id = ?
            """,
            (self._agent_scope, task_id),
        )

    def get_task_runtime(self, task_id: int) -> dict[str, Any] | None:
        return self._fetch_one(
            """
            SELECT id, user_id, chat_id, status, query_text, provider, model, work_dir, attempt, max_attempts,
                   cost_usd, error_message, created_at, started_at, completed_at, session_id, provider_session_id,
                   source_task_id, source_action, env_id, classification, environment_kind, current_phase,
                   last_heartbeat_at, retention_expires_at
            FROM tasks WHERE agent_id = ? AND id = ?
            """,
            (self._agent_scope, task_id),
        )

    def list_events(
        self,
        *,
        task_id: int | None = None,
        env_id: int | None = None,
        after_seq: int = 0,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT id, task_id, env_id, attempt, phase, event_type, severity, payload_json,
                   artifact_refs_json, resource_snapshot_ref, created_at
            FROM runtime_events
            WHERE agent_id = ? AND id > ?
        """
        params: list[Any] = [self._agent_scope, after_seq]
        if task_id is not None:
            query += " AND task_id = ?"
            params.append(task_id)
        if env_id is not None:
            query += " AND env_id = ?"
            params.append(env_id)
        query += " ORDER BY id ASC"
        rows = self._fetch_all(query, params)
        return [
            {
                **{
                    k: v
                    for k, v in row.items()
                    if k not in {"id", "event_type", "created_at", "payload_json", "artifact_refs_json"}
                },
                "seq": row["id"],
                "type": row["event_type"],
                "ts": row["created_at"],
                "payload": dict(row.get("payload_json") or {}),
                "artifact_refs": list(row.get("artifact_refs_json") or []),
            }
            for row in rows
        ]

    def list_artifacts(self, task_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, artifact_kind, label, path, metadata_json, created_at, expires_at
            FROM runtime_artifacts WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )
        return [{**row, "metadata": dict(row.pop("metadata_json") or {})} for row in rows]

    def list_checkpoints(self, task_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, status, checkpoint_dir, manifest_path, patch_path, commit_sha,
                   metadata_json, created_at, expires_at
            FROM runtime_checkpoints WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )
        return [{**row, "metadata": dict(row.pop("metadata_json") or {})} for row in rows]

    def get_checkpoint(self, checkpoint_id: int) -> dict[str, Any] | None:
        row = self._fetch_one(
            """
            SELECT id, task_id, env_id, status, checkpoint_dir, manifest_path, patch_path, commit_sha,
                   metadata_json, created_at, expires_at
            FROM runtime_checkpoints WHERE agent_id = ? AND id = ? ORDER BY id DESC LIMIT 1
            """,
            (self._agent_scope, checkpoint_id),
        )
        if row is None:
            return None
        row["metadata"] = dict(row.pop("metadata_json") or {})
        return row

    def get_latest_checkpoint(self, task_id: int) -> dict[str, Any] | None:
        row = self._fetch_one(
            """
            SELECT id, task_id, env_id, status, checkpoint_dir, manifest_path, patch_path, commit_sha,
                   metadata_json, created_at, expires_at
            FROM runtime_checkpoints WHERE agent_id = ? AND task_id = ? ORDER BY id DESC LIMIT 1
            """,
            (self._agent_scope, task_id),
        )
        if row is None:
            return None
        row["metadata"] = dict(row.pop("metadata_json") or {})
        return row

    def list_terminals(self, task_id: int) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT id, task_id, env_id, terminal_kind, label, path, stream_path, interactive, cursor_offset,
                   last_offset, created_at, updated_at
            FROM runtime_terminals WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )

    def list_resource_samples(self, task_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, cpu_percent, rss_kb, process_count, workspace_disk_bytes, metadata_json,
                   created_at
            FROM runtime_resource_samples WHERE agent_id = ? AND task_id = ? ORDER BY id DESC LIMIT ?
            """,
            (self._agent_scope, task_id, limit),
        )
        payload = [{**row, "metadata": dict(row.pop("metadata_json") or {})} for row in rows]
        return list(reversed(payload))

    def list_warnings(self, task_id: int) -> list[dict[str, Any]]:
        rows = self._fetch_all(
            """
            SELECT id, task_id, env_id, warning_type, message, details_json, created_at
            FROM runtime_warnings WHERE agent_id = ? AND task_id = ? ORDER BY id ASC
            """,
            (self._agent_scope, task_id),
        )
        return [{**row, "details": dict(row.pop("details_json") or {})} for row in rows]

    def list_stale_environments(self, *, stale_before: str) -> list[dict[str, Any]]:
        return self._fetch_all(
            """
            SELECT id, task_id, user_id, chat_id, classification, environment_kind, current_phase,
                   status, workspace_path, runtime_dir, base_work_dir, branch_name, created_worktree,
                   checkpoint_status, checkpoint_path, parent_env_id, source_checkpoint_id, recovery_state,
                   revision, pause_state, process_pid, process_pgid, browser_scope_id, last_heartbeat_at
            FROM runtime_environments
            WHERE agent_id = ? AND status = 'active' AND (last_heartbeat_at IS NULL OR last_heartbeat_at < ?)
            ORDER BY id ASC
            """,
            (self._agent_scope, stale_before),
        )

    def count_envs_by_phase(self) -> dict[str, int]:
        rows = self._fetch_all(
            """
            SELECT current_phase, COUNT(*) AS count
            FROM runtime_environments
            WHERE agent_id = ?
            GROUP BY current_phase
            """,
            (self._agent_scope,),
        )
        return {str(row.get("current_phase") or ""): int(row.get("count") or 0) for row in rows}

    def list_expired_attach_sessions(self, *, before: str | None = None) -> list[dict[str, Any]]:
        cutoff = before or _now()
        return self._fetch_all(
            """
            SELECT id, task_id, env_id, attach_kind, terminal_id, token, can_write, actor, status, expires_at,
                   created_at, last_seen_at, ended_at
            FROM runtime_attach_sessions
            WHERE agent_id = ? AND status = 'active' AND expires_at <= ?
            ORDER BY id ASC
            """,
            (self._agent_scope, cutoff),
        )
