"""Tests for unified agent asset reuse ranking."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.agent_asset_registry import AgentAssetRegistry
from koda.services.script_manager import ScriptSearchResult


@pytest.mark.asyncio
async def test_asset_registry_merges_script_and_artifact_refs():
    storage = SimpleNamespace(
        list_artifact_evidence_rows_async=AsyncMock(
            return_value=[
                {
                    "evidence_key": "artifact-1",
                    "modality": "image_analysis",
                    "label": "rollback flow screenshot",
                    "extracted_text": "SIM-410 rollback confirmation for payments service",
                    "confidence": 0.91,
                    "trust_level": "high",
                    "source_path": "/tmp/services/payments.py",
                    "source_url": "",
                    "metadata": {"source_label": "policy:deploy"},
                    "artifact_id": "artifact-1",
                    "time_span": None,
                }
            ]
        )
    )
    script_manager = SimpleNamespace(
        _initialized=True,
        search=AsyncMock(
            return_value=[
                ScriptSearchResult(
                    script_id=7,
                    title="payments rollback helper",
                    description="Rollback script for SIM-410 incidents",
                    language="python",
                    content="def rollback_payment(): pass",
                    similarity=0.92,
                    quality_score=0.8,
                    use_count=6,
                )
            ]
        ),
    )

    with (
        patch("koda.services.agent_asset_registry.search_assets", return_value=[]),
        patch("koda.services.agent_asset_registry.upsert_asset"),
    ):
        registry = AgentAssetRegistry(agent_id="AGENT_A", storage=storage, script_manager=script_manager)
        refs = await registry.search(
            query="Use rollback helper for SIM-410 in payments",
            user_id=123,
            work_dir="/tmp/services/payments",
            project_key="billing",
            workspace_fingerprint="services/payments",
            source_scope=("policy:deploy",),
            limit=4,
        )

    assert [item["asset_kind"] for item in refs[:2]] == ["script", "artifact"]
    assert refs[0]["asset_key"] == "script:7"
    assert refs[1]["asset_key"] == "artifact:artifact-1"
    assert refs[1]["source_path"] == "services/payments.py"


@pytest.mark.asyncio
async def test_asset_registry_filters_artifacts_outside_source_scope():
    storage = SimpleNamespace(
        list_artifact_evidence_rows_async=AsyncMock(
            return_value=[
                {
                    "evidence_key": "artifact-2",
                    "modality": "ocr",
                    "label": "workspace screenshot",
                    "extracted_text": "deploy checklist",
                    "confidence": 0.95,
                    "trust_level": "high",
                    "source_path": "/tmp/docs/checklist.png",
                    "source_url": "",
                    "metadata": {"source_label": "workspace:private"},
                    "artifact_id": "artifact-2",
                    "time_span": None,
                }
            ]
        )
    )
    script_manager = SimpleNamespace(_initialized=False, search=AsyncMock(return_value=[]))

    with (
        patch("koda.services.agent_asset_registry.search_assets", return_value=[]),
        patch("koda.services.agent_asset_registry.upsert_asset"),
    ):
        registry = AgentAssetRegistry(agent_id="AGENT_A", storage=storage, script_manager=script_manager)
        refs = await registry.search(
            query="deploy checklist",
            user_id=123,
            source_scope=("policy:deploy",),
            limit=4,
        )

    assert refs == []


@pytest.mark.asyncio
async def test_asset_registry_surfaces_persisted_assets():
    storage = SimpleNamespace(list_artifact_evidence_rows_async=AsyncMock(return_value=[]))
    script_manager = SimpleNamespace(_initialized=False, search=AsyncMock(return_value=[]))

    with (
        patch(
            "koda.services.agent_asset_registry.search_assets",
            return_value=[
                {
                    "asset_key": "script:8",
                    "title": "payments rollback helper",
                    "kind": "script",
                    "content_text": "payments rollback helper python",
                    "body": {
                        "score": 0.81,
                        "reuse_reason": "semantic_match",
                        "source_path": "services/payments.py",
                    },
                }
            ],
        ),
        patch("koda.services.agent_asset_registry.upsert_asset"),
    ):
        registry = AgentAssetRegistry(agent_id="AGENT_A", storage=storage, script_manager=script_manager)
        refs = await registry.search(
            query="need rollback helper for payments",
            user_id=123,
            work_dir="/tmp/services/payments",
            limit=4,
        )

    assert refs
    assert refs[0]["asset_key"] == "script:8"
    assert refs[0]["asset_kind"] == "script"
