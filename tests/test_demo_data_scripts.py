from __future__ import annotations

import base64
import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def decode_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def test_seed_demo_agent_ids_are_stable_and_prefixed() -> None:
    seed_demo_data = load_script("seed_demo_data")

    assert seed_demo_data.managed_demo_agent_ids("DEMO_") == [
        "DEMO_ATLAS",
        "DEMO_HARBOR",
        "DEMO_SAGE",
        "DEMO_FORGE",
    ]


def test_clear_statements_scope_koda_to_demo_sessions() -> None:
    seed_demo_data = load_script("seed_demo_data")

    statements = seed_demo_data.build_clear_statements("knowledge_v2", prefix="DEMO_")
    sql = "\n".join(statement.sql for statement in statements)

    string_params = {param for statement in statements for param in statement.params if isinstance(param, str)}
    assert "koda-docs-demo:%" in string_params
    assert "agent_id = ANY($1::text[])" in sql
    assert "agent_id = $2 AND session_id LIKE $3" in sql
    assert "counter_key = 'active_docs_demo_memories'" in sql
    assert 'DELETE FROM "knowledge_v2"."cp_agent_definitions"' in sql


def test_web_operator_cookie_seal_matches_aes_gcm_contract() -> None:
    capture_docs_screenshots = load_script("capture_docs_screenshots")
    nonce = b"\x01" * 12

    sealed = capture_docs_screenshots.seal_web_operator_token("local-token", "session-secret", nonce=nonce)
    iv_part, ciphertext_part, tag_part = sealed.split(".")

    key = hashlib.sha256(b"session-secret").digest()
    plaintext = AESGCM(key).decrypt(
        decode_b64url(iv_part),
        decode_b64url(ciphertext_part) + decode_b64url(tag_part),
        None,
    )

    assert plaintext == b"local-token"
