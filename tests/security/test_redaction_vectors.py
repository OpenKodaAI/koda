"""One redactor, one vector set, every path (TD-056, M5-E3-T8).

Each vector is an input payload and the literal output every redacting path must give for
it: the shared redactor itself, the runtime store, the audit trail, the eval trajectory
export and, for the top-level key vectors, the structured-log processor. The paths are
resolved lazily so a path that still runs its own patterns fails on the vector it handles
differently instead of on an import.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from collections.abc import Callable
from typing import Any

import pytest

R = "[REDACTED]"

# Flat payloads whose sensitive keys come from the union of the old key lists: audit
# (credentials, access_key), the Rust core (session), evals and the run graph (auth,
# private_key) and the control-plane logging list (recovery_code, bootstrap_code, code).
KEY_VECTORS: list[tuple[dict[str, Any], dict[str, Any]]] = [
    ({"password": "hunter2", "user": "admin"}, {"password": R, "user": "admin"}),
    ({"Authorization": "abc", "status": "ok"}, {"Authorization": R, "status": "ok"}),
    ({"SESSION_TOKEN": "kodas_abc"}, {"SESSION_TOKEN": R}),
    ({"session_id": "s-1"}, {"session_id": R}),
    ({"credentials": "admin:123"}, {"credentials": R}),
    ({"access_key": "AKIA1"}, {"access_key": R}),
    ({"private_key": "-----BEGIN"}, {"private_key": R}),
    ({"auth_header": "x"}, {"auth_header": R}),
    ({"recovery_code": "aaaa-bbbb"}, {"recovery_code": R}),
    ({"bootstrap_code": "ABCD-EFGH"}, {"bootstrap_code": R}),
    ({"code": "123456"}, {"code": R}),
    ({"api_key": ""}, {"api_key": R}),
    (
        {"exit_code": 0, "status_code": 200, "code_source": "generated", "phase": "executing"},
        {"exit_code": 0, "status_code": 200, "code_source": "generated", "phase": "executing"},
    ),
]

# Values: inline secrets inside strings, nested structures and JSON normalisation. Every
# text pattern comes from one of the old implementations (audit, the Rust core, evals).
VALUE_VECTORS: list[tuple[Any, Any]] = [
    ("hello world", "hello world"),
    ("Olá mundo, ção", "Olá mundo, ção"),
    ("def my_function(): return 42", "def my_function(): return 42"),
    ("https://example.com/page?id=123&format=json", "https://example.com/page?id=123&format=json"),
    ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456", f"Authorization: Bearer {R}"),
    ("bearer sk-abc123", f"bearer {R}"),
    ("https://user:pass@example.com/path", f"https://{R}:{R}@example.com/path"),
    ("cookie=session_abc123", f"cookie={R}"),
    ("password=hunter2 and more", f"password={R} and more"),
    ("https://example.com/api?token=mytoken123&x=1", f"https://example.com/api?token={R}&x=1"),
    ("deploy with token=sk-live", f"deploy with token={R}"),
    ("your token is abcdefghijklmnopqrstuvwxyz123456", f"your token is {R}"),
    (
        {"a": [{"api_key": "k", "name": "alice"}, "Bearer xyz"]},
        {"a": [{"api_key": R, "name": "alice"}, f"Bearer {R}"]},
    ),
    (("Bearer xyz", 1), [f"Bearer {R}", 1]),
    ({"n": 1, "f": 1.5, "b": True, "z": None}, {"n": 1, "f": 1.5, "b": True, "z": None}),
]


def _shared(value: dict[str, Any]) -> Any:
    return importlib.import_module("koda.security.redaction").redact_value(value)


def _runtime_store(value: dict[str, Any]) -> Any:
    store = importlib.import_module("koda.services.runtime.postgres_store")
    return json.loads(store._redacted_json(value))


def _audit(value: dict[str, Any]) -> Any:
    details = importlib.import_module("koda.services.audit")._prepare_details(value)
    return {key: item for key, item in details.items() if key != "redactions"}


def _evals_export(value: dict[str, Any]) -> Any:
    evals = importlib.import_module("koda.services.evals")
    export = evals.build_trajectory_export(
        agent_id="KODA",
        task_id=1,
        execution={"status": "completed"},
        run_graph={"nodes": [{"node_id": "n1", "node_type": "tool", "payload": value}]},
        replay={"steps": []},
    )
    (node,) = [
        record
        for record in (json.loads(line) for line in export["jsonl"].splitlines())
        if record["record_type"] == "run_graph_node"
    ]
    return node["payload"]


def _structured_log(value: dict[str, Any]) -> Any:
    logging_config = importlib.import_module("koda.logging_config")
    return dict(logging_config._redact_sensitive(object(), "info", dict(value)))


VALUE_PATHS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "shared": _shared,
    "runtime_store": _runtime_store,
    "audit": _audit,
    "evals_export": _evals_export,
}
# The log processor only masks top-level keys: it never rewrites event names or ids.
KEY_PATHS: dict[str, Callable[[dict[str, Any]], Any]] = {**VALUE_PATHS, "structured_log": _structured_log}


@pytest.mark.parametrize("path", sorted(KEY_PATHS))
@pytest.mark.parametrize(("payload", "expected"), KEY_VECTORS, ids=[str(sorted(v[0])) for v in KEY_VECTORS])
def test_key_vectors_give_the_same_output_on_every_path(
    path: str, payload: dict[str, Any], expected: dict[str, Any]
) -> None:
    assert KEY_PATHS[path](payload) == expected


@pytest.mark.parametrize("path", sorted(VALUE_PATHS))
@pytest.mark.parametrize(("value", "expected"), VALUE_VECTORS, ids=[repr(v[0])[:40] for v in VALUE_VECTORS])
def test_value_vectors_give_the_same_output_on_every_path(path: str, value: Any, expected: Any) -> None:
    assert VALUE_PATHS[path]({"payload": value}) == {"payload": expected}


def test_audit_reports_the_paths_it_redacted() -> None:
    audit = importlib.import_module("koda.services.audit")
    details = audit._prepare_details({"config": {"api_key": "k", "url": "https://u:p@h/x"}, "ok": "fine"})
    assert details["redactions"] == {"count": 2, "fields": ["config.api_key", "config.url"]}


def test_old_modules_no_longer_carry_a_redactor() -> None:
    assert importlib.util.find_spec("koda.services.runtime.redaction") is None
    owned_elsewhere = {
        "koda.services.audit": ("_SENSITIVE_KEY_RE", "_INLINE_SECRET_PATTERNS", "_redact_string", "_sanitize_payload"),
        "koda.services.evals": ("redacted", "_fallback_redact"),
        "koda.services.provider_env": ("redact_runtime_value",),
        "koda.logging_config": ("_REDACTED_KEYS",),
    }
    for module_name, names in owned_elsewhere.items():
        module = importlib.import_module(module_name)
        assert [name for name in names if hasattr(module, name)] == [], module_name
    client = importlib.import_module("koda.internal_rpc.security_guard").SecurityGuardClient
    assert not hasattr(client, "redact_value")
