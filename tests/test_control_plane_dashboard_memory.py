"""Focused tests for control-plane memory dashboard helpers and routes."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from aiohttp import web

from koda.control_plane import api as control_plane_api
from koda.control_plane.dashboard_memory import (
    apply_memory_curation_action,
    get_memory_curation_cluster_payload,
    get_memory_curation_detail_payload,
    get_memory_map_payload,
    list_memory_curation_payload,
)


class _Request:
    def __init__(
        self,
        *,
        match_info: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.match_info = match_info or {}
        self.query = query or {}
        self.headers: dict[str, str] = {}
        self.can_read_body = payload is not None
        self._payload = payload or {}

    async def json(self) -> dict[str, object]:
        return dict(self._payload)


def test_get_memory_map_payload_aggregates_primary_memory_tables():
    class _FakeMemoryEngineClient:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def get_memory_map(self, *, payload: dict[str, object]) -> dict[str, object]:
            assert payload["agent_id"] == "agent_a"
            assert payload["filters"]["days"] == 30
            assert "summary_row" not in payload
            assert "rows" not in payload
            return {
                "agent_id": "AGENT_A",
                "summary": {"total": 3, "active": 2, "superseded": 1, "stale": 0, "invalidated": 0},
                "embedding_jobs": {"ready": 2},
                "quality_counters": {"dedup.semantic": 4},
                "top_clusters": [
                    {"cluster_id": "cluster-1", "memory_count": 2, "latest_created_at": "2026-03-27T09:00:00+00:00"}
                ],
                "recent_recall": [
                    {
                        "id": 91,
                        "user_id": 42,
                        "task_id": 77,
                        "query_preview": "rollback billing",
                        "trust_score": 0.92,
                        "total_considered": 5,
                        "total_selected": 2,
                        "total_discarded": 3,
                        "conflict_group_count": 1,
                        "selected_layers_csv": "procedural",
                        "retrieval_sources_csv": "semantic",
                        "created_at": "2026-03-27T10:10:00+00:00",
                    }
                ],
            }

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "authoritative": True,
                "production_ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "memory_map"},
            }

    with (
        patch("koda.control_plane.dashboard_memory.require_primary_state_backend", return_value=object()),
        patch("koda.control_plane.dashboard_memory.emit"),
        patch(
            "koda.control_plane.dashboard_memory.build_memory_engine_client",
            return_value=_FakeMemoryEngineClient(),
        ),
    ):
        payload = get_memory_map_payload("AGENT_A")

    assert payload["summary"]["total"] == 3
    assert payload["embedding_jobs"]["ready"] == 2
    assert payload["quality_counters"]["dedup.semantic"] == 4
    assert payload["top_clusters"][0]["cluster_id"] == "cluster-1"
    assert payload["recent_recall"][0]["id"] == 91


def test_list_memory_curation_payload_returns_items_and_cluster_summaries():
    class _FakeMemoryEngineClient:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def list_curation_items(self, *, payload: dict[str, object]) -> dict[str, object]:
            assert payload["filters"]["query"] == "rollback"
            assert payload["agent_id"] == "agent_a"
            assert "rows" not in payload
            return {
                "agent_id": "AGENT_A",
                "overview": {
                    "pending_memories": 1,
                    "pending_clusters": 1,
                    "expiring_soon": 0,
                    "discarded_last_7d": 0,
                    "merged_last_7d": 0,
                    "approved_last_7d": 0,
                },
                "items": [
                    {
                        "agent_id": "AGENT_A",
                        "id": 101,
                        "memory_id": 101,
                        "memory_type": "procedure",
                        "title": "billing rollback",
                        "content": "Run billing rollback after confirming canary error rate.",
                        "source_query_id": 17,
                        "source_query_preview": "rollback billing",
                        "session_id": "sess-1",
                        "user_id": 42,
                        "importance": 0.9,
                        "access_count": 3,
                        "created_at": "2026-03-27T09:00:00+00:00",
                        "last_accessed": "2026-03-27T10:00:00+00:00",
                        "expires_at": None,
                        "review_status": "pending",
                        "review_reason": None,
                        "duplicate_of_memory_id": None,
                        "cluster_id": "cluster-1",
                        "semantic_strength": 0.85,
                        "memory_status": "active",
                        "metadata": {"source": "memory"},
                        "is_active": True,
                    }
                ],
                "clusters": [
                    {
                        "cluster_id": "cluster-1",
                        "summary": "cluster-1",
                        "memory_count": 1,
                        "latest_created_at": "2026-03-27T09:00:00+00:00",
                    }
                ],
                "filters": {"query": "rollback"},
                "page": {"limit": 25, "offset": 0, "total": 1, "has_more": False},
            }

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "authoritative": True,
                "production_ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "curation"},
            }

    with (
        patch("koda.control_plane.dashboard_memory.require_primary_state_backend", return_value=object()),
        patch("koda.control_plane.dashboard_memory.emit"),
        patch(
            "koda.control_plane.dashboard_memory.build_memory_engine_client",
            return_value=_FakeMemoryEngineClient(),
        ),
    ):
        payload = list_memory_curation_payload(
            "AGENT_A",
            limit=25,
            offset=0,
            query_text="rollback",
            memory_status="active",
        )

    assert payload["page"]["total"] == 1
    assert payload["items"][0]["id"] == 101
    assert payload["items"][0]["cluster_id"] == "cluster-1"
    assert payload["filters"]["query"] == "rollback"
    assert payload["clusters"][0]["cluster_id"] == "cluster-1"


def test_get_memory_curation_detail_payload_includes_cluster_and_audits():
    class _FakeMemoryEngineClient:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def get_curation_detail(self, *, subject_id: str, payload: dict[str, object]) -> dict[str, object]:
            assert subject_id == "101"
            assert payload["detail_kind"] == "memory"
            assert "row" not in payload
            return {
                "memory": {
                    "agent_id": "AGENT_A",
                    "id": 101,
                    "memory_id": 101,
                    "memory_type": "procedure",
                    "title": "billing rollback",
                    "content": "Run billing rollback after confirming canary error rate.",
                    "source_query_id": 17,
                    "source_query_preview": "rollback billing",
                    "session_id": "sess-1",
                    "user_id": 42,
                    "importance": 0.9,
                    "access_count": 3,
                    "created_at": "2026-03-27T09:00:00+00:00",
                    "last_accessed": "2026-03-27T10:00:00+00:00",
                    "expires_at": None,
                    "review_status": "pending",
                    "review_reason": None,
                    "duplicate_of_memory_id": None,
                    "cluster_id": "cluster-1",
                    "semantic_strength": 0.85,
                    "memory_status": "active",
                    "metadata": {"source": "memory"},
                    "is_active": True,
                },
                "cluster": {
                    "summary": {"cluster_id": "cluster-1", "memory_count": 2},
                    "members": [{"id": 101}, {"id": 102}],
                },
                "recent_audits": [{"id": 5}],
            }

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "authoritative": True,
                "production_ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "curation_detail"},
            }

    with (
        patch("koda.control_plane.dashboard_memory.require_primary_state_backend", return_value=object()),
        patch(
            "koda.control_plane.dashboard_memory.build_memory_engine_client",
            return_value=_FakeMemoryEngineClient(),
        ),
    ):
        payload = get_memory_curation_detail_payload("AGENT_A", 101)

    assert payload["memory"]["content"].startswith("Run billing rollback")
    assert payload["cluster"]["summary"]["memory_count"] == 2
    assert payload["recent_audits"][0]["id"] == 5


def test_get_memory_curation_cluster_payload_routes_through_memory_engine():
    class _FakeMemoryEngineClient:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def get_curation_detail(self, *, subject_id: str, payload: dict[str, object]) -> dict[str, object]:
            assert subject_id == "cluster-1"
            assert payload["detail_kind"] == "cluster"
            assert payload["cluster_id"] == "cluster-1"
            return {
                "cluster": {"cluster_id": "cluster-1", "member_count": 2},
                "members": [{"id": 101}, {"id": 102}],
                "overlaps": [{"session_id": "sess-1", "count": 2}],
                "history": [{"id": 1}],
            }

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "authoritative": True,
                "production_ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "curation_detail"},
            }

    with (
        patch("koda.control_plane.dashboard_memory.require_primary_state_backend", return_value=object()),
        patch(
            "koda.control_plane.dashboard_memory.build_memory_engine_client",
            return_value=_FakeMemoryEngineClient(),
        ),
    ):
        payload = get_memory_curation_cluster_payload("AGENT_A", "cluster-1")

    assert payload["cluster"]["cluster_id"] == "cluster-1"
    assert payload["members"][1]["id"] == 102


def test_get_memory_curation_cluster_payload_routes_without_local_projection():
    class _FakeMemoryEngineClient:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def get_curation_detail(self, *, subject_id: str, payload: dict[str, object]) -> dict[str, object]:
            assert subject_id == "missing"
            assert payload["detail_kind"] == "cluster"
            assert payload["cluster_id"] == "missing"
            assert "cluster_rows" not in payload
            return {"cluster": {"cluster_id": "missing", "member_count": 0}}

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "authoritative": True,
                "production_ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "curation_detail"},
            }

    with (
        patch("koda.control_plane.dashboard_memory.require_primary_state_backend", return_value=object()),
        patch(
            "koda.control_plane.dashboard_memory.build_memory_engine_client",
            return_value=_FakeMemoryEngineClient(),
        ),
    ):
        payload = get_memory_curation_cluster_payload("AGENT_A", "missing")

    assert payload["cluster"]["cluster_id"] == "missing"


def test_apply_memory_curation_action_deactivate_uses_engine_batch_plan():
    class _FakeMemoryEngineClient:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def apply_curation_action(
            self,
            *,
            subject_id: str,
            action: str,
            payload: dict[str, object],
        ) -> dict[str, object]:
            assert subject_id == "memory-batch"
            assert action == "deactivate"
            assert payload["memory_ids"] == [101, 102]
            assert "cluster_rows" not in payload
            return {
                "applied": True,
                "updated_count": 2,
                "memory_ids": [101, 102],
                "operations": [
                    {
                        "op": "batch_deactivate",
                        "memory_ids": [101, 102],
                    }
                ],
            }

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "authoritative": True,
                "production_ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "curation_action"},
            }

    with (
        patch("koda.control_plane.dashboard_memory.require_primary_state_backend", return_value=object()),
        patch(
            "koda.control_plane.dashboard_memory.build_memory_engine_client",
            return_value=_FakeMemoryEngineClient(),
        ),
    ):
        payload = apply_memory_curation_action("AGENT_A", {"action": "deactivate", "memory_ids": [101, 102]})

    assert payload["updated_count"] == 2


def test_apply_memory_curation_action_set_status_uses_engine_status_plan():
    class _FakeMemoryEngineClient:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def apply_curation_action(
            self,
            *,
            subject_id: str,
            action: str,
            payload: dict[str, object],
        ) -> dict[str, object]:
            assert subject_id == "101"
            assert action == "set_status"
            assert payload["memory_ids"] == [101]
            assert "cluster_rows" not in payload
            return {
                "applied": True,
                "updated_count": 1,
                "memory_ids": [101],
                "memory_status": "stale",
                "operations": [
                    {
                        "op": "set_status",
                        "memory_id": 101,
                        "memory_status": "stale",
                        "duplicate_of_memory_id": None,
                    }
                ],
            }

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "authoritative": True,
                "production_ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "curation_action"},
            }

    with (
        patch("koda.control_plane.dashboard_memory.require_primary_state_backend", return_value=object()),
        patch(
            "koda.control_plane.dashboard_memory.build_memory_engine_client",
            return_value=_FakeMemoryEngineClient(),
        ),
    ):
        payload = apply_memory_curation_action(
            "AGENT_A",
            {"action": "set_status", "memory_id": 101, "memory_status": "stale"},
        )

    assert payload["updated_count"] == 1
    assert payload["memory_ids"] == [101]


def test_apply_memory_curation_action_routes_merge_plan_through_memory_engine():
    class _FakeMemoryEngineClient:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def apply_curation_action(
            self,
            *,
            subject_id: str,
            action: str,
            payload: dict[str, object],
        ) -> dict[str, object]:
            assert subject_id == "cluster-1"
            assert action == "merge"
            assert payload["memory_ids"] == []
            assert payload["target_type"] == "cluster"
            assert payload["target_ids"] == ["cluster-1"]
            assert "cluster_rows" not in payload
            return {
                "applied": True,
                "updated_count": 1,
                "reason": "dedupe canonical",
                "duplicate_of_memory_id": 101,
                "memory_ids": [101, 102],
                "operations": [
                    {
                        "op": "review_state",
                        "memory_id": 102,
                        "review_status": "merged",
                        "memory_status": "superseded",
                        "is_active": False,
                        "reason": "dedupe canonical",
                        "duplicate_of_memory_id": 101,
                        "expires_now": False,
                    }
                ],
            }

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "authoritative": True,
                "production_ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "curation_action"},
            }

    with (
        patch("koda.control_plane.dashboard_memory.require_primary_state_backend", return_value=object()),
        patch("koda.control_plane.dashboard_memory.emit") as emit_mock,
        patch(
            "koda.control_plane.dashboard_memory.build_memory_engine_client",
            return_value=_FakeMemoryEngineClient(),
        ),
    ):
        payload = apply_memory_curation_action(
            "AGENT_A",
            {
                "action": "merge",
                "target_type": "cluster",
                "cluster_id": "cluster-1",
                "reason": "dedupe canonical",
            },
        )

    emit_mock.assert_called_once()
    assert payload["duplicate_of_memory_id"] == 101


@pytest.mark.asyncio
async def test_dashboard_memory_handlers_return_canonical_payloads():
    request = _Request(match_info={"agent_id": "AGENT_A"}, query={"limit": "25"})
    with patch(
        "koda.control_plane.api.list_memory_curation_payload",
        return_value={
            "agent_id": "AGENT_A",
            "items": [],
            "clusters": [],
            "page": {"limit": 25, "offset": 0, "total": 0, "has_more": False},
            "filters": {},
        },
    ):
        response = await control_plane_api.list_dashboard_memory_curation(request)

    payload = json.loads(response.text)
    assert payload["agent_id"] == "AGENT_A"
    assert payload["page"]["limit"] == 25


@pytest.mark.asyncio
async def test_dashboard_memory_action_handler_accepts_json_payload():
    request = _Request(match_info={"agent_id": "AGENT_A"}, payload={"action": "deactivate", "memory_id": 101})
    with patch(
        "koda.control_plane.api.apply_memory_curation_action",
        return_value={"ok": True, "updated_count": 1},
    ) as apply_action:
        response = await control_plane_api.post_dashboard_memory_curation_action(request)

    apply_action.assert_called_once_with("AGENT_A", {"action": "deactivate", "memory_id": 101})
    assert json.loads(response.text)["updated_count"] == 1


def test_setup_control_plane_routes_registers_memory_dashboard_endpoints():
    app = web.Application()
    control_plane_api.setup_control_plane_routes(app)
    canonicals = {route.resource.canonical for route in app.router.routes()}

    assert "/api/control-plane/dashboard/agents/{agent_id}/memory-map" in canonicals
    assert "/api/control-plane/dashboard/agents/{agent_id}/memory-curation" in canonicals
    assert "/api/control-plane/dashboard/agents/{agent_id}/memory-curation/{memory_id}" in canonicals
    assert "/api/control-plane/dashboard/agents/{agent_id}/memory-curation/clusters/{cluster_id}" in canonicals
    assert "/api/control-plane/dashboard/agents/{agent_id}/memory-curation/actions" in canonicals
