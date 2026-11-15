"""One redactor, one vector set, every path (TD-056, M5-E3-T8).

Each vector is an input payload and the literal output every redacting path must give for
it: the shared redactor itself, the runtime store, the audit trail, the eval trajectory
export and, for the top-level key vectors, the structured-log processor. The paths are
resolved lazily so a path that still runs its own patterns fails on the vector it handles
differently instead of on an import. Field names come in English and PT-BR. The labelled
corpus also runs each text through the runtime API terminal preview, both memory previews
and the workspace-import excerpt.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

R = "[REDACTED]"

# Flat payloads whose sensitive keys come from the union of the old key lists: audit
# (credentials, access_key), the Rust core (session), evals and the run graph (auth,
# private_key) and the control-plane logging list (recovery_code, bootstrap_code, code).
KEY_VECTORS: list[tuple[dict[str, Any], dict[str, Any]]] = [
    ({"password": "hunter2", "user": "admin"}, {"password": R, "user": "admin"}),
    ({"Authorization": "abc", "status": "ok"}, {"Authorization": R, "status": "ok"}),
    ({"SESSION_TOKEN": "kodas_abc"}, {"SESSION_TOKEN": R}),
    ({"session": "cookie-value"}, {"session": R}),
    ({"credentials": "admin:123"}, {"credentials": R}),
    ({"access_key": "AKIA1"}, {"access_key": R}),
    ({"private_key": "-----BEGIN"}, {"private_key": R}),
    ({"auth_header": "x"}, {"auth_header": R}),
    ({"auth": "u:p", "basic_auth": "u:p", "x-auth": "k"}, {"auth": R, "basic_auth": R, "x-auth": R}),
    ({"recovery_code": "aaaa-bbbb"}, {"recovery_code": R}),
    ({"bootstrap_code": "ABCD-EFGH"}, {"bootstrap_code": R}),
    ({"code": "123456"}, {"code": R}),
    ({"api_key": ""}, {"api_key": R}),
    (
        {"exit_code": 0, "status_code": 200, "code_source": "generated", "phase": "executing"},
        {"exit_code": 0, "status_code": 200, "code_source": "generated", "phase": "executing"},
    ),
    # Identifiers that hold no secret: a session id and keys that only contain "auth".
    (
        {"session_id": "s-1", "provider_session_id": "p-1", "author": "Ana", "auth_mode": "oauth"},
        {"session_id": "s-1", "provider_session_id": "p-1", "author": "Ana", "auth_mode": "oauth"},
    ),
    (
        {"authoritative": True, "authority_scope": "full", "full_authority": False},
        {"authoritative": True, "authority_scope": "full", "full_authority": False},
    ),
    # PT-BR field names.
    (
        {"senha": "hunter2", "nova_senha": "x", "chave_api": "k", "segredo": "s", "credenciais": "c"},
        {"senha": R, "nova_senha": R, "chave_api": R, "segredo": R, "credenciais": R},
    ),
    (
        {"token_de_acesso": "t", "usuario": "ana", "descricao": "ok", "desenhar": "x"},
        {"token_de_acesso": R, "usuario": "ana", "descricao": "ok", "desenhar": "x"},
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
    # Credential shapes from the memory-safety fallback.
    ("key AKIAIOSFODNN7EXAMPLE here", f"key {R} here"),
    ("sk-abcdefghijklmnopqrst", R),
    ("ghp_abcdefghijklmnopqrstuvwxyz0123", R),
    ("api key: hunter2hunter2", f"api key: {R}"),
    ("access token = abc", f"access token = {R}"),
    # PT-BR inline secrets.
    ("senha=hunter2 e mais", f"senha={R} e mais"),
    ("segredo: abc", f"segredo: {R}"),
    ("chave_api=k1", f"chave_api={R}"),
    # Long identifiers that are not secrets: tool names, directories, UUID and file names.
    ("mcp__github__pull_request_review_write", "mcp__github__pull_request_review_write"),
    ("/home/user/projects/my_very_long_project_directory", "/home/user/projects/my_very_long_project_directory"),
    (
        "/srv/koda/artifacts/1b4e28ba-2fa1-11d2-883f-0016d3cca427/quarterly_financial_report_2026.pdf",
        "/srv/koda/artifacts/1b4e28ba-2fa1-11d2-883f-0016d3cca427/quarterly_financial_report_2026.pdf",
    ),
    (
        {"a": [{"api_key": "k", "name": "alice"}, "Bearer xyz"]},
        {"a": [{"api_key": R, "name": "alice"}, f"Bearer {R}"]},
    ),
    (("Bearer xyz", 1), [f"Bearer {R}", 1]),
    ({"n": 1, "f": 1.5, "b": True, "z": None}, {"n": 1, "f": 1.5, "b": True, "z": None}),
]

# The labelled corpus (M5-E3-T8 follow-up). Each text runs through every path that redacts
# text and each key payload through every path that redacts keys. Cases marked "guard"
# already passed before the fix; they pin what the new rules must keep doing.
_UUID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
_UUID_HEX = "7c9e6679742540de944be07fc1f90ae7"

# (label, text, expected): secrets in free text.
MASKED_TEXT: list[tuple[str, str, str]] = [
    ("bearer keeps + / = in the token", "Authorization: Bearer abc+def/ghi==", f"Authorization: Bearer {R}"),
    ("bearer in free text with + / =", "use bearer abc+def/ghi== now", f"use bearer {R} now"),
    ("basic auth header", "Authorization: Basic dXNlcjpwYXNz", f"Authorization: Basic {R}"),
    ("basic auth in free text", "send Basic YWRtaW46aHVudGVyMg== upstream", f"send Basic {R} upstream"),
    ("curl header", 'curl -H "Authorization: Basic dXNlcjpwYXNz" x', f'curl -H "Authorization: Basic {R}" x'),
    ("base64url secret with - and _", "secret Xk9_aB-3vQ7_pL2-mN8_rT5-wZ1_yH4 here", f"secret {R} here"),
    ("base64url secret, mixed case", "id 3q2-K8x_Vb7nR4t-Y9wE1uI6_oP0aS5dF ok", f"id {R} ok"),
    ("guard: hex secret that is not a UUID", "dd 0123456789abcdef0123456789abcdef", f"dd {R}"),
    ("env line, API key holding a UUID", "HEROKU_API_KEY=3f1c2b5e-0d4a-4c7e-9b8a-6e5d4c3b2a10", f"HEROKU_API_KEY={R}"),
    (
        "env line, AWS secret",
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLE",
        f"AWS_SECRET_ACCESS_KEY={R}",
    ),
    ("export line", "export DB_PASSWORD=hunter2", f"export DB_PASSWORD={R}"),
    ("JSON key and quoted value", '{"OPENAI_API_KEY": "x"}', f'{{"OPENAI_API_KEY": "{R}"}}'),
    ("quoted assignment", "token = 'sk-test-secret-value'", f"token = '{R}'"),
    ("camelCase auth key in text", "basicAuth: admin:hunter2", f"basicAuth: {R}"),
    ("camelCase auth key, = form", "authKey=k-1", f"authKey={R}"),
    ("PT-BR camelCase key", "minhaSenha=abc", f"minhaSenha={R}"),
    ("PT-BR spaced key", "token de acesso: abc123", f"token de acesso: {R}"),
    ("PT-BR chave de api", "chave de api = xyz", f"chave de api = {R}"),
    ("PT-BR chave in JSON", '{"chave": "valor-secreto"}', f'{{"chave": "{R}"}}'),
    ("DSN credentials", "postgresql://koda:s3cret@db:5432/koda", f"postgresql://{R}:{R}@db:5432/koda"),
    ("URL with empty user", "redis://:p4ss@cache:6379", f"redis://{R}:{R}@cache:6379"),
    ("OAuth code in query", "https://x.test/cb?code=4/0Aabc&state=xyz", f"https://x.test/cb?code={R}&state=xyz"),
    ("guard: cookie header, every cookie", "Cookie: sid=abc123; theme=dark", f"Cookie: {R}"),
    ("set-cookie header", "Set-Cookie: sid=abc; Path=/; HttpOnly", f"Set-Cookie: {R}"),
    ("Google key with short segments", "key AIzaSyB-4kd8_Qw2-x9Zt_Lm3q-Rv7_Np0Yc5 end", f"key {R} end"),
    ("Slack token with short segments", "xoxp-1234-5678-9abc-def0-AbCd-EfGh", R),
    ("GitHub fine-grained PAT", "github_pat_11AB_cd34_EF56_gh78_IJ90_kl12_MN34", R),
    ("guard: OpenAI project key", "use sk-proj-AbC1_dEf2-GhI3_jKl4-MnO5_pQr6", f"use {R}"),
    ("guard: old Rust core vector", "token abcdefghijklmnopqrstuvwxyz123456", f"token {R}"),
    # Secrets passed as command-line flags.
    ("flag --password=", "mysql -u root --password=hunter2 db", f"mysql -u root --password={R} db"),
    ("flag --token=", "deploy --token=abc123def", f"deploy --token={R}"),
    (
        "kebab flags and a one-dash flag",
        "run --api-key=k1 --db-password=p2 --auth-token=t3 -token=t4",
        f"run --api-key={R} --db-password={R} --auth-token={R} -token={R}",
    ),
    # An unquoted value is masked whole, up to whitespace or a comma.
    ("value with &", "password=Tr0ub4dor&3", f"password={R}"),
    ("value with ;", "password=abc;def", f"password={R}"),
    ("value with parentheses", "secret: p@ss(w0rd)", f"secret: {R}"),
    ("value in brackets", "password=[hunter2]", f"password={R}"),
    ("value in braces", "password={hunter2}", f"password={R}"),
    ("guard: secret after a non-secret value", "user=admin;password=hunter2 ok", f"user=admin;password={R} ok"),
    ("guard: key-<base36> secret", "key-k3j5h2m9q8w7e6r5t4y3u2i1o0p9a8", R),
]

# (label, text): identifiers and plain text that hold no secret, unchanged.
KEPT_TEXT: list[tuple[str, str]] = [
    ("operator-shell session id", "task-42-operator-shell-a1b2c3d4e5f6"),
    ("runtime API default session", "session-9f1c2b5e0d4a4c7e9b8a6e5d4c3b2a10"),
    ("squad delegation session", "squad-3f9a1c7e5b2d8f0a6c4e1b9d"),
    ("bare uuid4 hex", _UUID_HEX),
    ("prefixed uuid4 hex", f"imp_{_UUID_HEX}"),
    ("guard: queue worker id", "worker_12345_a1b2c3d4e5f6"),
    ("kebab name with risk-", "risk-assessment-checklist-final"),
    ("kebab name with desk-", "desk-booking-service-production"),
    ("tool name with task- and -sk-", "mcp__linear__task-sk-compat-layer-2026"),
    ("camelCase MCP tool name", "mcp__atlassian__getConfluencePageDescendants"),
    ("snake name with a long word and digits", "internationalization_settings_2026"),
    ("file path with risk-desk", "/srv/koda/reports/risk-desk-summary-2026-q3.md"),
    ("UUID artifact path", f"/srv/koda/artifacts/{_UUID}/internationalization_report_2026.pdf"),
    ("guard: model name", "claude-sonnet-4-5-20250929"),
    ("guard: the word basic", "a basic example of basic usage"),
    ("guard: exit and status codes", "exit code: 1, status code: 200"),
    ("guard: non-secret auth keys in text", "author: Ana, auth_mode: oauth"),
    # Names with short mixed segments (k8s, i18n, e2e, b2b, a11y, 2026q3).
    ("tool name with k8s", "mcp__kubernetes__list_k8s_namespaces"),
    ("kebab name with k8s", "deploy-k8s-production-cluster"),
    ("kebab name with i18n", "i18n-translations-pt-br-update"),
    ("kebab name with e2e", "e2e-tests-for-runtime-kernel"),
    ("snake name with b2b", "koda_b2b_onboarding_flow_2026"),
    ("file name with e2e", "test_streaming_e2e_regression.py"),
    ("kebab name with a11y and v2", "a11y-audit-for-dashboard-v2"),
    ("kebab name with 2026q3", "report-2026q3-final-version"),
    ("artifact collision suffix", "screenshot-final-a1b2c3d4.png"),
    # camelCase names with a digit.
    ("class name in exception text", "KnowledgeV2PostgresBackend failed"),
    ("camelCase MCP tool name with a digit", "mcp__aws__describeEc2Instances"),
    # Token usage counts.
    ("token counts in text", "prompt_tokens: 1200, completion_tokens: 300"),
    ("max_tokens in text", "max_tokens=4096"),
    ("token count in JSON text", '{"prompt_tokens": 1200}'),
]

# (label, payload, expected): keys whose whole value is masked, or kept.
KEY_CORPUS: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
    (
        "camelCase and snake auth keys",
        {"basicAuth": "admin:hunter2", "proxyAuth": "u:p", "auth_key": "k-1", "authKey": "k", "httpAuth": "x"},
        {"basicAuth": R, "proxyAuth": R, "auth_key": R, "authKey": R, "httpAuth": R},
    ),
    (
        "more auth keys",
        {"auth_pass": "y", "HTTPAuth": "z", "x-auth-key": "w"},
        {"auth_pass": R, "HTTPAuth": R, "x-auth-key": R},
    ),
    (
        "PT-BR keys",
        {"chave": "x", "chave_de_acesso": "y", "novaSenha": "z", "segredos": "w", "senhaAtual": "v"},
        {"chave": R, "chave_de_acesso": R, "novaSenha": R, "segredos": R, "senhaAtual": R},
    ),
    (
        "guard: PT-BR keys that are not secrets",
        {"palavra_chave": "busca", "chave_primaria": "id", "desenho": "x"},
        {"palavra_chave": "busca", "chave_primaria": "id", "desenho": "x"},
    ),
    (
        "Koda session ids",
        {"session_id": "squad-3f9a1c7e5b2d8f0a6c4e1b9d", "provider_session_id": f"session-{_UUID_HEX}"},
        {"session_id": "squad-3f9a1c7e5b2d8f0a6c4e1b9d", "provider_session_id": f"session-{_UUID_HEX}"},
    ),
    (
        "guard: auth-like keys that are not secrets",
        {"auth_mode": "oauth", "auth_provider": "github", "authority": "x", "author": "Ana"},
        {"auth_mode": "oauth", "auth_provider": "github", "authority": "x", "author": "Ana"},
    ),
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


def _run_graph(value: dict[str, Any]) -> Any:
    run_graph = importlib.import_module("koda.services.run_graph")
    node = run_graph.RunGraphNode(
        node_id="n1",
        graph_id="g1",
        agent_id="KODA",
        task_id=1,
        attempt=1,
        node_type="tool_result",
        status="completed",
        ordinal=0,
        summary="",
        payload=value,
    )
    edge = run_graph.RunGraphEdge(
        edge_id="e1", graph_id="g1", from_node_id="n1", to_node_id="n1", edge_type="emits", ordinal=0, payload=value
    )
    assert edge.payload == node.payload
    return node.payload


def _structured_log(value: dict[str, Any]) -> Any:
    logging_config = importlib.import_module("koda.logging_config")
    return dict(logging_config._redact_sensitive(object(), "info", dict(value)))


VALUE_PATHS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "shared": _shared,
    "runtime_store": _runtime_store,
    "audit": _audit,
    "evals_export": _evals_export,
    "run_graph": _run_graph,
}
# The log processor only masks top-level keys: it never rewrites event names or ids.
KEY_PATHS: dict[str, Callable[[dict[str, Any]], Any]] = {**VALUE_PATHS, "structured_log": _structured_log}


def _runtime_api(text: str) -> str:
    # The terminal list route: the preview is the tail of the terminal log, redacted.
    api = importlib.import_module("koda.services.runtime.api")
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "terminal.log"
        log.write_text(text, encoding="utf-8")
        store = SimpleNamespace(list_terminals=lambda task_id: [{"id": 1, "path": str(log)}])
        request = SimpleNamespace(match_info={"task_id": "1"}, headers={}, query={})
        with (
            patch.object(api, "_authorize_runtime_access", return_value=None),
            patch.object(api, "get_runtime_controller", return_value=SimpleNamespace(store=store)),
        ):
            response = asyncio.run(api._runtime_task_terminals(request))
    return str(json.loads(response.text)["items"][0]["preview"])


def _memory_safety(text: str) -> str:
    return str(importlib.import_module("koda.memory.safety")._redacted_preview(text, limit=1000))


def _memory_recall(text: str) -> str:
    return str(importlib.import_module("koda.memory.recall")._redacted_memory_preview(text, limit=1000))


def _workspace_import(text: str) -> str:
    workspace_import = importlib.import_module("koda.control_plane.workspace_import")
    root = Path("/srv/workspace")
    source = workspace_import._source(root, root / "AGENTS.md", kind="instructions", tool="codex", text=text)
    return str(source.content_excerpt)


def _in_payload(path: Callable[[dict[str, Any]], Any]) -> Callable[[str], Any]:
    return lambda text: path({"payload": text})["payload"]


TEXT_PATHS: dict[str, Callable[[str], Any]] = {
    **{name: _in_payload(path) for name, path in VALUE_PATHS.items()},
    "runtime_api": _runtime_api,
    "memory_safety": _memory_safety,
    "memory_recall": _memory_recall,
    "workspace_import": _workspace_import,
}


@pytest.mark.parametrize("path", sorted(TEXT_PATHS))
@pytest.mark.parametrize(("text", "expected"), [v[1:] for v in MASKED_TEXT], ids=[v[0] for v in MASKED_TEXT])
def test_corpus_secrets_are_masked_on_every_path(path: str, text: str, expected: str) -> None:
    assert TEXT_PATHS[path](text) == expected


@pytest.mark.parametrize("path", sorted(TEXT_PATHS))
@pytest.mark.parametrize("text", [v[1] for v in KEPT_TEXT], ids=[v[0] for v in KEPT_TEXT])
def test_corpus_identifiers_survive_every_path(path: str, text: str) -> None:
    assert TEXT_PATHS[path](text) == text


@pytest.mark.parametrize("path", sorted(KEY_PATHS))
@pytest.mark.parametrize(("payload", "expected"), [v[1:] for v in KEY_CORPUS], ids=[v[0] for v in KEY_CORPUS])
def test_corpus_keys_on_every_path(path: str, payload: dict[str, Any], expected: dict[str, Any]) -> None:
    assert KEY_PATHS[path](payload) == expected


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
        "koda.services.run_graph": ("_SENSITIVE_KEY_PARTS", "_fallback_redact_value"),
        "koda.services.provider_env": ("redact_runtime_value",),
        "koda.logging_config": ("_REDACTED_KEYS",),
        "koda.control_plane.workspace_import": ("SECRET_RE", "_redact_text"),
    }
    for module_name, names in owned_elsewhere.items():
        module = importlib.import_module(module_name)
        assert [name for name in names if hasattr(module, name)] == [], module_name
    client = importlib.import_module("koda.internal_rpc.security_guard").SecurityGuardClient
    assert not hasattr(client, "redact_value")


def test_security_sidecar_no_longer_serves_redaction() -> None:
    root = Path(__file__).resolve().parents[2]
    assert "Redact" not in (root / "proto/security/v1/security.proto").read_text(encoding="utf-8")
    assert "redact" not in (root / "rust/koda-security-service/src/main.rs").read_text(encoding="utf-8")
    assert "redact_value" not in (root / "rust/koda-security-core/src/lib.rs").read_text(encoding="utf-8")
    generated = root / "koda/internal_rpc/generated/security/v1"
    for name in ("security_pb2.py", "security_pb2_grpc.py"):
        assert "RedactValue" not in (generated / name).read_text(encoding="utf-8"), name
