"""Approval-first self-improvement proposal lifecycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from koda.knowledge.repository import KnowledgeRepository
from koda.memory.safety import assert_memory_text_safe
from koda.services.runtime.redaction import redact_value

SCHEMA_VERSION = "improvement_proposal.v1"

PROPOSAL_STATUSES = frozenset(
    {
        "draft",
        "pending_review",
        "approved",
        "rejected",
        "validating",
        "applied",
        "rolled_back",
        "failed",
    }
)
PROPOSAL_TYPES = frozenset(
    {
        "memory",
        "skill",
        "prompt",
        "routing_profile",
        "tool_policy",
        "eval_case",
        "docs",
    }
)
SOURCE_KINDS = frozenset(
    {
        "run",
        "eval",
        "user_correction",
        "timeout",
        "dead_letter",
        "tool_failure",
        "manual",
    }
)
RISK_CLASSES = frozenset({"low", "medium", "high", "critical"})
LEDGER_ONLY_EFFECT_KIND = "ledger_only"
WORKFLOW_PATTERN_SCHEMA_VERSION = "workflow_pattern.v1"

_CREATION_STATUSES = frozenset({"draft", "pending_review"})
_REVIEWABLE_STATUSES = frozenset({"draft", "pending_review", "approved"})
_LEGACY_SOURCE_KIND_ALIASES = {
    "eval_failure": "eval",
    "eval_run": "eval",
}
_EVIDENCE_SOURCE_KIND_ALIASES = frozenset({"memory_quality", "knowledge_candidate"})
_WORKFLOW_OBSERVATION_KINDS = frozenset({"eval_failure", "tool_failure", "dead_letter", "user_correction", "manual"})


class ImprovementProposalError(ValueError):
    """Base class for proposal contract and lifecycle failures."""


class ImprovementProposalNotFound(KeyError):
    """Raised when a proposal does not exist in the agent queue."""


class InvalidImprovementProposalTransition(ImprovementProposalError):
    """Raised when a lifecycle action is not allowed from the current state."""


def detect_repeated_workflow_patterns(
    observations: list[dict[str, Any]],
    *,
    min_observations: int = 2,
) -> list[dict[str, Any]]:
    """Group repeated workflow/failure observations into ``workflow_pattern.v1`` evidence."""

    grouped: dict[str, dict[str, Any]] = {}
    for raw in observations:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or raw.get("source_kind") or "manual").strip()
        if kind not in _WORKFLOW_OBSERVATION_KINDS:
            continue
        workflow_name = str(raw.get("workflow_name") or raw.get("skill_id") or raw.get("task_category") or "").strip()
        category = str(raw.get("failure_category") or raw.get("category") or kind).strip()
        required_tools = sorted(str(item) for item in _json_list(raw.get("required_tools")))
        required_skills = sorted(str(item) for item in _json_list(raw.get("required_skills")))
        signature_payload = {
            "workflow_name": workflow_name.lower(),
            "category": category.lower(),
            "required_tools": required_tools,
            "required_skills": required_skills,
        }
        signature = hashlib.sha256(
            json.dumps(signature_payload, ensure_ascii=True, sort_keys=True).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:20]
        item = grouped.setdefault(
            signature,
            {
                "schema_version": WORKFLOW_PATTERN_SCHEMA_VERSION,
                "workflow_id": f"workflow:{signature}",
                "workflow_name": workflow_name or category or "workflow",
                "failure_category": category,
                "required_tools": required_tools,
                "required_skills": required_skills,
                "observed_count": 0,
                "sources": [],
                "source_fingerprints": [],
                "evidence_refs": [],
                "run_graph_node_ids": [],
            },
        )
        item["observed_count"] += 1
        source_ref = str(
            raw.get("source_ref") or raw.get("run_id") or raw.get("task_id") or raw.get("id") or ""
        ).strip()
        if source_ref and source_ref not in item["sources"]:
            item["sources"].append(source_ref)
        fingerprint = str(raw.get("fingerprint") or source_ref or kind).strip()
        if fingerprint and fingerprint not in item["source_fingerprints"]:
            item["source_fingerprints"].append(fingerprint)
        evidence_ref = raw.get("evidence_ref")
        if isinstance(evidence_ref, dict):
            item["evidence_refs"].append(evidence_ref)
        for node_id in _json_list(raw.get("run_graph_node_ids")):
            node_text = str(node_id or "").strip()
            if node_text and node_text not in item["run_graph_node_ids"]:
                item["run_graph_node_ids"].append(node_text)
    sorted_patterns = sorted(
        grouped.values(),
        key=lambda value: (str(value["workflow_name"]), str(value["failure_category"])),
    )
    return [item for item in sorted_patterns if int(item.get("observed_count") or 0) >= max(2, int(min_observations))]


@dataclass(slots=True)
class ImprovementProposalService:
    """Validate, dedupe, and transition ``improvement_proposal.v1`` records."""

    repository: KnowledgeRepository

    def create(self, payload: dict[str, Any], *, requested_by: str = "control-plane") -> dict[str, Any]:
        proposal = self._normalize_create_payload(payload, requested_by=requested_by)
        existing = self.repository.get_improvement_proposal_by_idempotency_hash(
            proposal["idempotency_hash"],
        )
        if existing is not None:
            return existing
        return self.repository.create_improvement_proposal(proposal)

    def create_skill_proposal_from_evidence(
        self,
        evidence: dict[str, Any],
        *,
        requested_by: str = "skill-proposal",
    ) -> dict[str, Any]:
        """Create a draft skill proposal from workflow/eval/manual evidence only."""

        if not isinstance(evidence, dict):
            raise ImprovementProposalError("skill proposal evidence must be an object")
        evidence_kind = str(evidence.get("source_kind") or evidence.get("kind") or "manual").strip()
        if evidence_kind not in {"run", "eval", "manual"}:
            raise ImprovementProposalError("skill proposals require run, eval, or manual evidence")
        source_ref = str(evidence.get("source_ref") or evidence.get("workflow_id") or evidence.get("case_key") or "")
        if not source_ref:
            raise ImprovementProposalError("source_ref is required")
        skill_id = str(evidence.get("skill_id") or evidence.get("workflow_id") or source_ref).strip()
        observed_count = int(evidence.get("observed_count") or evidence.get("repeat_count") or 1)
        summary = str(evidence.get("summary") or f"Draft skill proposal from repeated evidence for {skill_id}.").strip()
        return self.create(
            {
                "source_kind": evidence_kind,
                "source_ref": f"skill:{source_ref}",
                "proposal_type": "skill",
                "summary": summary,
                "evidence_refs": [
                    {
                        "kind": evidence_kind,
                        "source_ref": source_ref,
                        "observed_count": observed_count,
                    },
                    *self._normalize_json_list(evidence.get("evidence_refs"), field="evidence_refs"),
                ],
                "diff_preview": {
                    "proposed_change": (
                        "Create a draft skill package for operator review; no install or apply is automatic."
                    ),
                    "skill_id": skill_id,
                    "title": evidence.get("title") or skill_id,
                    "instruction_preview": evidence.get("instruction_preview") or evidence.get("instruction") or "",
                    "observed_count": observed_count,
                },
                "risk_class": str(evidence.get("risk_class") or "medium").lower(),
                "validation_plan": {
                    "strategy": "skill_eval.v1",
                    "required": ["scanner_allow_or_review", "offline_eval_pass"],
                    **self._normalize_json_object(evidence.get("validation_plan"), field="validation_plan"),
                },
                "rollback_plan": {
                    "strategy": "ledger_only",
                    "effects": [
                        {
                            "effect_kind": LEDGER_ONLY_EFFECT_KIND,
                            "target_ref": f"skill_proposal:{source_ref}",
                            "before_ref": {"status": "absent"},
                            "after_ref": {"status": "draft_proposal_created", "auto_install": False},
                        }
                    ],
                },
                "status": "draft",
                "reviewer": requested_by,
                "run_graph_node_ids": self._normalize_json_list(
                    evidence.get("run_graph_node_ids"),
                    field="run_graph_node_ids",
                ),
            },
            requested_by=requested_by,
        )

    def create_skill_proposal_from_workflow_pattern(
        self,
        pattern: dict[str, Any],
        *,
        requested_by: str = "workflow-pattern",
    ) -> dict[str, Any]:
        """Create a deduped draft skill proposal from repeated workflow evidence."""

        if not isinstance(pattern, dict):
            raise ImprovementProposalError("workflow pattern evidence must be an object")
        observed_count = int(pattern.get("observed_count") or pattern.get("repeat_count") or 0)
        if observed_count < 2:
            raise ImprovementProposalError("workflow pattern skill proposals require at least two observations")
        source_kind = str(pattern.get("source_kind") or "manual").strip()
        if source_kind not in SOURCE_KINDS:
            raise ImprovementProposalError(f"invalid workflow pattern source_kind: {source_kind}")
        workflow_signature = self._workflow_signature(pattern)
        source_ref = f"workflow_pattern:{workflow_signature}"
        return self.create_skill_proposal_from_evidence(
            {
                "source_kind": source_kind,
                "source_ref": source_ref,
                "workflow_id": workflow_signature,
                "skill_id": pattern.get("skill_id") or pattern.get("workflow_name") or workflow_signature,
                "observed_count": observed_count,
                "summary": pattern.get("summary")
                or f"Draft skill proposal for repeated workflow pattern {workflow_signature}.",
                "instruction_preview": pattern.get("instruction_preview") or "",
                "evidence_refs": [
                    {
                        "kind": WORKFLOW_PATTERN_SCHEMA_VERSION,
                        "id": workflow_signature,
                        "observed_count": observed_count,
                        "sources": self._normalize_json_list(pattern.get("sources"), field="sources")[:20],
                    },
                    *self._normalize_json_list(pattern.get("evidence_refs"), field="evidence_refs"),
                ],
                "validation_plan": {
                    "strategy": "skill_eval.v1",
                    "required": ["scanner_allow_or_review", "offline_eval_pass", "operator_review"],
                    **self._normalize_json_object(pattern.get("validation_plan"), field="validation_plan"),
                },
                "run_graph_node_ids": self._normalize_json_list(
                    pattern.get("run_graph_node_ids"),
                    field="run_graph_node_ids",
                ),
            },
            requested_by=requested_by,
        )

    def list_proposals(
        self,
        *,
        status: str | None = None,
        proposal_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if status is not None and status not in PROPOSAL_STATUSES:
            raise ImprovementProposalError(f"invalid proposal status: {status}")
        if proposal_type is not None and proposal_type not in PROPOSAL_TYPES:
            raise ImprovementProposalError(f"invalid proposal type: {proposal_type}")
        return self.repository.list_improvement_proposals(
            status=status,
            proposal_type=proposal_type,
            limit=max(1, min(int(limit), 500)),
        )

    def get(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.repository.get_improvement_proposal(proposal_id)
        if proposal is None:
            raise ImprovementProposalNotFound(proposal_id)
        return self._normalize_loaded_proposal(proposal)

    def approve(self, proposal_id: str, *, reviewer: str = "control-plane", note: str = "") -> dict[str, Any]:
        proposal = self.get(proposal_id)
        self._require_status(proposal, {"draft", "pending_review"}, action="approve")
        self._require_review_ready(proposal)
        return self._transition(proposal, "approved", reviewer=reviewer, note=note)

    def reject(self, proposal_id: str, *, reviewer: str = "control-plane", note: str = "") -> dict[str, Any]:
        proposal = self.get(proposal_id)
        self._require_status(proposal, _REVIEWABLE_STATUSES, action="reject")
        return self._transition(proposal, "rejected", reviewer=reviewer, note=note)

    def validate(
        self,
        proposal_id: str,
        *,
        validation_result: dict[str, Any] | None = None,
        reviewer: str = "control-plane",
        note: str = "",
    ) -> dict[str, Any]:
        proposal = self.get(proposal_id)
        self._require_status(proposal, {"approved", "validating"}, action="validate")
        started = (
            proposal
            if proposal.get("status") == "validating"
            else self._transition(
                proposal,
                "validating",
                reviewer=reviewer,
                note=note,
            )
        )
        if validation_result is None:
            return started
        normalized_result = self._normalize_json_object(validation_result, field="validation_result")
        if self._validation_passed(normalized_result):
            return self._transition(
                started,
                "approved",
                reviewer=reviewer,
                note=note or "validation passed",
                validation_result=normalized_result,
                timestamp_field="validated_at",
            )
        return self._transition(
            started,
            "failed",
            reviewer=reviewer,
            note=note or "validation failed",
            validation_result=normalized_result,
            timestamp_field="validated_at",
        )

    def apply(self, proposal_id: str, *, reviewer: str = "control-plane", note: str = "") -> dict[str, Any]:
        proposal = self.get(proposal_id)
        self._require_status(proposal, {"approved"}, action="apply")
        if not str(proposal.get("validated_at") or "").strip():
            raise InvalidImprovementProposalTransition("proposal must be validated after approval before apply")
        validation_result = self._normalize_json_object(
            proposal.get("validation_result"),
            field="validation_result",
        )
        if not self._validation_passed(validation_result):
            raise InvalidImprovementProposalTransition("proposal validation must pass before apply")
        rollback_plan = self._normalize_json_object(proposal.get("rollback_plan"), field="rollback_plan")
        if not rollback_plan:
            raise InvalidImprovementProposalTransition("structured rollback_plan is required before apply")
        if not proposal.get("run_graph_node_ids"):
            raise InvalidImprovementProposalTransition("RunGraph lifecycle evidence is required before apply")
        self._apply_effect_ledger(proposal, rollback_plan)
        return self._transition(proposal, "applied", reviewer=reviewer, note=note, timestamp_field="applied_at")

    def rollback(self, proposal_id: str, *, reviewer: str = "control-plane", note: str = "") -> dict[str, Any]:
        proposal = self.get(proposal_id)
        self._require_status(proposal, {"applied"}, action="rollback")
        self._rollback_effect_ledger(proposal)
        return self._transition(
            proposal,
            "rolled_back",
            reviewer=reviewer,
            note=note,
            timestamp_field="rolled_back_at",
        )

    def _normalize_create_payload(self, payload: dict[str, Any], *, requested_by: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ImprovementProposalError("proposal payload must be an object")
        agent_id = str(payload.get("agent_id") or self.repository.agent_id or "").strip().upper()
        source_kind, evidence_kind = self._normalize_source_kind(payload.get("source_kind"))
        source_ref = self._required_text(payload, "source_ref")
        proposal_type = self._required_choice(payload, "proposal_type", PROPOSAL_TYPES)
        summary = self._required_text(payload, "summary")
        status = str(payload.get("status") or "pending_review").strip()
        if status not in _CREATION_STATUSES:
            raise ImprovementProposalError("new proposals may only be draft or pending_review")
        risk_class = str(payload.get("risk_class") or "medium").strip().lower()
        if risk_class not in RISK_CLASSES:
            raise ImprovementProposalError(f"invalid risk_class: {risk_class}")
        if self._has_json_value(payload.get("validation_result")):
            raise ImprovementProposalError("validation_result is recorded only by the validation lifecycle")
        assert_memory_text_safe(
            {
                "summary": summary,
                "diff_preview": payload.get("diff_preview"),
                "evidence_refs": payload.get("evidence_refs"),
                "validation_plan": payload.get("validation_plan"),
                "rollback_plan": payload.get("rollback_plan"),
            },
            surface="improvement_proposal",
        )
        diff_preview = redact_value(payload.get("diff_preview") or {}, key_hint="diff_preview")
        evidence_refs = self._normalize_json_list(payload.get("evidence_refs"), field="evidence_refs")
        if evidence_kind:
            evidence_refs = [{"kind": evidence_kind, "source_ref": source_ref}, *evidence_refs]
        validation_plan = self._normalize_json_object(payload.get("validation_plan"), field="validation_plan")
        rollback_plan = self._normalize_json_object(payload.get("rollback_plan"), field="rollback_plan")
        proposal_id = str(payload.get("proposal_id") or f"imp_{uuid4().hex}")
        now = _now_iso()
        input_node_ids = self._normalize_json_list(
            payload.get("run_graph_node_ids"),
            field="run_graph_node_ids",
        )
        lifecycle_node_id = self._lifecycle_node_id(
            proposal_id=proposal_id,
            status=status,
            at=now,
        )
        normalized = {
            "proposal_id": proposal_id,
            "schema_version": SCHEMA_VERSION,
            "agent_id": agent_id,
            "source_kind": source_kind,
            "source_ref": source_ref,
            "proposal_type": proposal_type,
            "summary": summary,
            "evidence_refs": evidence_refs,
            "diff_preview": diff_preview,
            "risk_class": risk_class,
            "validation_plan": validation_plan,
            "validation_result": {},
            "rollback_plan": rollback_plan,
            "status": status,
            "reviewer": str(payload.get("reviewer") or requested_by or "").strip(),
            "run_graph_node_ids": self._append_unique(input_node_ids, lifecycle_node_id),
        }
        normalized["idempotency_hash"] = self._idempotency_hash(normalized)
        supplied_hash = str(payload.get("idempotency_hash") or "").strip()
        if supplied_hash and supplied_hash != normalized["idempotency_hash"]:
            raise ImprovementProposalError("idempotency_hash does not match canonical proposal payload")
        normalized["created_at"] = now
        normalized["updated_at"] = now
        normalized["reviewed_at"] = ""
        normalized["validated_at"] = ""
        normalized["applied_at"] = ""
        normalized["rolled_back_at"] = ""
        normalized["status_history"] = [
            {
                "status": status,
                "reviewer": normalized["reviewer"],
                "note": "created",
                "at": normalized["created_at"],
                "run_graph_node_id": lifecycle_node_id,
            }
        ]
        if status == "pending_review":
            self._require_review_ready(normalized)
        return normalized

    def _transition(
        self,
        proposal: dict[str, Any],
        status: str,
        *,
        reviewer: str,
        note: str = "",
        validation_result: dict[str, Any] | None = None,
        timestamp_field: str | None = None,
    ) -> dict[str, Any]:
        now = _now_iso()
        node_id = self._lifecycle_node_id(
            proposal_id=str(proposal.get("proposal_id") or ""),
            status=status,
            at=now,
        )
        history = list(proposal.get("status_history") or [])
        history.append({"status": status, "reviewer": reviewer, "note": note, "at": now, "run_graph_node_id": node_id})
        update: dict[str, Any] = {
            "status": status,
            "reviewer": reviewer,
            "updated_at": now,
            "status_history": history,
            "run_graph_node_ids": self._append_unique(list(proposal.get("run_graph_node_ids") or []), node_id),
        }
        if status in {"approved", "rejected"} and not str(proposal.get("reviewed_at") or "").strip():
            update["reviewed_at"] = now
        if validation_result is not None:
            update["validation_result"] = validation_result
        if timestamp_field:
            update[timestamp_field] = now
        updated = self.repository.update_improvement_proposal(str(proposal["proposal_id"]), **update)
        if updated is None:
            raise ImprovementProposalNotFound(str(proposal["proposal_id"]))
        return updated

    def _apply_effect_ledger(self, proposal: dict[str, Any], rollback_plan: dict[str, Any]) -> None:
        proposal_id = str(proposal.get("proposal_id") or "")
        effects = self.repository.list_improvement_proposal_effects(proposal_id)
        if not effects:
            for spec in self._effect_specs_from_rollback_plan(rollback_plan):
                self.repository.create_improvement_proposal_effect(
                    {
                        "effect_id": str(spec.get("effect_id") or f"ipe_{uuid4().hex}"),
                        "proposal_id": proposal_id,
                        "agent_id": str(proposal.get("agent_id") or self.repository.agent_id or "").upper(),
                        "effect_kind": LEDGER_ONLY_EFFECT_KIND,
                        "target_ref": str(spec["target_ref"]),
                        "before_ref": spec.get("before_ref"),
                        "after_ref": spec.get("after_ref"),
                        "status": "pending",
                        "apply_idempotency_key": str(
                            spec.get("apply_idempotency_key")
                            or self._effect_idempotency_key(proposal_id, spec, action="apply")
                        ),
                        "rollback_idempotency_key": str(
                            spec.get("rollback_idempotency_key")
                            or self._effect_idempotency_key(proposal_id, spec, action="rollback")
                        ),
                        "metadata": self._normalize_json_object(spec.get("metadata"), field="effect.metadata"),
                    }
                )
            effects = self.repository.list_improvement_proposal_effects(proposal_id)
        if not effects:
            raise InvalidImprovementProposalTransition("effect ledger is required before apply")
        for effect in effects:
            if str(effect.get("effect_kind") or "") != LEDGER_ONLY_EFFECT_KIND:
                raise InvalidImprovementProposalTransition(
                    f"no safe executor registered for effect kind {effect.get('effect_kind')!r}"
                )
            status = str(effect.get("status") or "")
            if status == "applied":
                continue
            if status != "pending":
                raise InvalidImprovementProposalTransition(
                    f"cannot apply effect {effect.get('effect_id')} from status {status or '<empty>'}"
                )
            updated = self.repository.update_improvement_proposal_effect(
                str(effect["effect_id"]),
                status="applied",
                applied_at=_now_iso(),
            )
            if updated is None:
                raise InvalidImprovementProposalTransition("failed to persist applied proposal effect")

    def _rollback_effect_ledger(self, proposal: dict[str, Any]) -> None:
        proposal_id = str(proposal.get("proposal_id") or "")
        effects = self.repository.list_improvement_proposal_effects(proposal_id)
        applied = [effect for effect in effects if str(effect.get("status") or "") == "applied"]
        if not applied:
            raise InvalidImprovementProposalTransition("applied effect ledger is required before rollback")
        for effect in reversed(applied):
            updated = self.repository.update_improvement_proposal_effect(
                str(effect["effect_id"]),
                status="rolled_back",
                rolled_back_at=_now_iso(),
            )
            if updated is None:
                raise InvalidImprovementProposalTransition("failed to persist rolled back proposal effect")

    def _effect_specs_from_rollback_plan(self, rollback_plan: dict[str, Any]) -> list[dict[str, Any]]:
        raw_effects = rollback_plan.get("effects")
        if not isinstance(raw_effects, list) or not raw_effects:
            raise InvalidImprovementProposalTransition("rollback_plan.effects is required before apply")
        specs: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_effects):
            if not isinstance(raw, dict):
                raise InvalidImprovementProposalTransition(f"rollback_plan.effects[{index}] must be an object")
            effect_kind = str(raw.get("effect_kind") or LEDGER_ONLY_EFFECT_KIND).strip()
            if effect_kind != LEDGER_ONLY_EFFECT_KIND:
                raise InvalidImprovementProposalTransition(
                    f"no safe executor registered for effect kind {effect_kind!r}"
                )
            target_ref = str(raw.get("target_ref") or "").strip()
            if not target_ref:
                raise InvalidImprovementProposalTransition(f"rollback_plan.effects[{index}].target_ref is required")
            specs.append({**raw, "effect_kind": effect_kind, "target_ref": target_ref})
        return specs

    @staticmethod
    def _required_text(payload: dict[str, Any], field: str) -> str:
        value = str(payload.get(field) or "").strip()
        if not value:
            raise ImprovementProposalError(f"{field} is required")
        return value

    @staticmethod
    def _required_choice(payload: dict[str, Any], field: str, allowed: frozenset[str]) -> str:
        value = str(payload.get(field) or "").strip()
        if value not in allowed:
            raise ImprovementProposalError(f"invalid {field}: {value or '<empty>'}")
        return value

    @staticmethod
    def _normalize_source_kind(value: Any) -> tuple[str, str | None]:
        raw = str(value or "").strip()
        if raw in SOURCE_KINDS:
            return raw, None
        if raw in _LEGACY_SOURCE_KIND_ALIASES:
            return _LEGACY_SOURCE_KIND_ALIASES[raw], None
        if raw in _EVIDENCE_SOURCE_KIND_ALIASES:
            return "manual", raw
        raise ImprovementProposalError(f"invalid source_kind: {raw or '<empty>'}")

    @classmethod
    def _normalize_loaded_proposal(cls, proposal: dict[str, Any]) -> dict[str, Any]:
        source_kind, evidence_kind = cls._normalize_source_kind(proposal.get("source_kind"))
        normalized = dict(proposal)
        normalized["source_kind"] = source_kind
        if evidence_kind:
            evidence_refs = list(normalized.get("evidence_refs") or [])
            evidence_refs.insert(
                0,
                {
                    "kind": evidence_kind,
                    "source_ref": normalized.get("source_ref") or "",
                },
            )
            normalized["evidence_refs"] = evidence_refs
        return normalized

    @classmethod
    def _require_review_ready(cls, proposal: dict[str, Any]) -> None:
        if not cls._has_json_value(proposal.get("evidence_refs")):
            raise ImprovementProposalError("evidence_refs is required before review")
        if not cls._has_json_value(proposal.get("diff_preview")):
            raise ImprovementProposalError("diff_preview is required before review")
        if not cls._has_json_value(proposal.get("validation_plan")):
            raise ImprovementProposalError("validation_plan is required before review")
        rollback_plan = cls._normalize_json_object(proposal.get("rollback_plan"), field="rollback_plan")
        if not rollback_plan:
            raise ImprovementProposalError("rollback_plan is required before review")

    @staticmethod
    def _normalize_json_list(value: Any, *, field: str) -> list[Any]:
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise ImprovementProposalError(f"{field} must be an array")
        return list(value)

    @staticmethod
    def _normalize_json_object(value: Any, *, field: str) -> dict[str, Any]:
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise ImprovementProposalError(f"{field} must be an object")
        return dict(value)

    @staticmethod
    def _validation_passed(result: dict[str, Any]) -> bool:
        status = str(result.get("status") or "").strip().lower()
        return (
            status in {"passed", "pass", "success", "succeeded"}
            or result.get("passed") is True
            or result.get("ok") is True
        )

    @staticmethod
    def _has_json_value(value: Any) -> bool:
        if value in (None, ""):
            return False
        if isinstance(value, dict):
            return any(ImprovementProposalService._has_json_value(item) for item in value.values())
        if isinstance(value, list):
            return any(ImprovementProposalService._has_json_value(item) for item in value)
        if isinstance(value, bool):
            return value
        return bool(str(value).strip())

    @staticmethod
    def _append_unique(values: list[Any], value: str) -> list[str]:
        output: list[str] = []
        for item in [*values, value]:
            text = str(item or "").strip()
            if text and text not in output:
                output.append(text)
        return output

    @staticmethod
    def _require_status(proposal: dict[str, Any], allowed: frozenset[str] | set[str], *, action: str) -> None:
        current = str(proposal.get("status") or "")
        if current not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise InvalidImprovementProposalTransition(
                f"cannot {action} proposal from status {current or '<empty>'}; expected one of: {allowed_text}"
            )

    @staticmethod
    def _idempotency_hash(proposal: dict[str, Any]) -> str:
        stable = {
            "agent_id": proposal["agent_id"],
            "source_kind": proposal["source_kind"],
            "source_ref": proposal["source_ref"],
            "proposal_type": proposal["proposal_type"],
        }
        if not str(proposal.get("source_ref") or "").startswith("skill:workflow_pattern:"):
            stable.update(
                {
                    "summary": proposal["summary"],
                    "diff_preview": proposal["diff_preview"],
                }
            )
        encoded = json.dumps(stable, ensure_ascii=True, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def _workflow_signature(cls, pattern: dict[str, Any]) -> str:
        stable_payload = {
            "schema_version": WORKFLOW_PATTERN_SCHEMA_VERSION,
            "workflow_name": str(pattern.get("workflow_name") or pattern.get("skill_id") or "").strip().lower(),
            "failure_category": str(pattern.get("failure_category") or pattern.get("category") or "").strip().lower(),
            "required_tools": sorted(
                str(item) for item in cls._normalize_json_list(pattern.get("required_tools"), field="required_tools")
            ),
            "required_skills": sorted(
                str(item) for item in cls._normalize_json_list(pattern.get("required_skills"), field="required_skills")
            ),
            "source_fingerprints": sorted(
                str(item)
                for item in cls._normalize_json_list(
                    pattern.get("source_fingerprints") or pattern.get("sources"),
                    field="source_fingerprints",
                )
            ),
        }
        encoded = json.dumps(stable_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
        return f"workflow:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _lifecycle_node_id(*, proposal_id: str, status: str, at: str) -> str:
        seed = json.dumps(
            {"proposal_id": proposal_id, "status": status, "at": at},
            ensure_ascii=True,
            sort_keys=True,
        )
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"runtime_event:improvement_proposal:{status}:{digest}"

    @staticmethod
    def _effect_idempotency_key(proposal_id: str, spec: dict[str, Any], *, action: str) -> str:
        seed = json.dumps(
            {
                "action": action,
                "proposal_id": proposal_id,
                "target_ref": spec.get("target_ref"),
                "before_ref": spec.get("before_ref"),
                "after_ref": spec.get("after_ref"),
            },
            ensure_ascii=True,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list | tuple | set) else []
