"""Tests for SEC-2: token/key rotation support in the control plane."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken

# ---------------------------------------------------------------------------
# Multi-token auth tests
# ---------------------------------------------------------------------------


def _make_request(token: str | None) -> MagicMock:
    """Build a minimal mock request with an Authorization header."""
    request = MagicMock()
    if token is not None:
        request.headers = {"Authorization": f"Bearer {token}"}
    else:
        request.headers = {}
    return request


class TestMultiTokenAuth:
    """Verify that _authorize_request supports comma-separated tokens."""

    def test_accepts_first_token(self):
        from koda.control_plane import api as control_plane_api

        with (
            patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"),
            patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", ["new-token", "old-token"]),
            patch("koda.control_plane.operator_auth.fetch_one", return_value=None),
        ):
            _authorize_request = control_plane_api._authorize_request

            result = _authorize_request(_make_request("new-token"))
            assert result is None  # authorized

    def test_accepts_second_token(self):
        from koda.control_plane import api as control_plane_api

        with (
            patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"),
            patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", ["new-token", "old-token"]),
            patch("koda.control_plane.operator_auth.fetch_one", return_value=None),
        ):
            _authorize_request = control_plane_api._authorize_request

            result = _authorize_request(_make_request("old-token"))
            assert result is None

    def test_rejects_invalid_token(self):
        from koda.control_plane import api as control_plane_api

        with (
            patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"),
            patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", ["new-token", "old-token"]),
            patch("koda.control_plane.operator_auth.fetch_one", return_value=None),
        ):
            _authorize_request = control_plane_api._authorize_request

            result = _authorize_request(_make_request("bad-token"))
            assert result is not None
            assert result.status == 401

    def test_single_token_backward_compatible(self):
        from koda.control_plane import api as control_plane_api

        with (
            patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"),
            patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", ["only-token"]),
            patch("koda.control_plane.operator_auth.fetch_one", return_value=None),
        ):
            _authorize_request = control_plane_api._authorize_request

            result = _authorize_request(_make_request("only-token"))
            assert result is None

    def test_missing_header_returns_401(self):
        from koda.control_plane import api as control_plane_api

        with (
            patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"),
            patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", ["some-token"]),
            patch("koda.control_plane.operator_auth.fetch_one", return_value=None),
        ):
            _authorize_request = control_plane_api._authorize_request

            result = _authorize_request(_make_request(None))
            assert result is not None
            assert result.status == 401

    def test_empty_tokens_returns_500(self):
        from koda.control_plane import api as control_plane_api

        with (
            patch.object(control_plane_api, "CONTROL_PLANE_AUTH_MODE", "token"),
            patch("koda.control_plane.operator_auth.CONTROL_PLANE_API_TOKENS", []),
            patch("koda.control_plane.operator_auth.fetch_one", return_value=None),
        ):
            _authorize_request = control_plane_api._authorize_request

            result = _authorize_request(_make_request("anything"))
            assert result is not None
            assert result.status == 401


# ---------------------------------------------------------------------------
# Crypto rotation tests
# ---------------------------------------------------------------------------


class TestCryptoRotation:
    """Verify master-key rotation and fallback decryption."""

    @pytest.fixture(autouse=True)
    def _clear_caches(self):
        """Ensure Fernet caches are cleared between tests."""
        from koda.control_plane.crypto import clear_fernet_cache

        clear_fernet_cache()
        yield
        clear_fernet_cache()

    def test_decrypt_with_current_key(self):
        current_key = Fernet.generate_key()
        current_fernet = Fernet(current_key)

        plaintext = "my-secret-value"
        ciphertext = current_fernet.encrypt(plaintext.encode()).decode()

        with (
            patch("koda.control_plane.crypto._load_master_key", return_value=current_key),
            patch("koda.control_plane.crypto._load_previous_master_key", return_value=None),
        ):
            from koda.control_plane.crypto import clear_fernet_cache, decrypt_secret

            clear_fernet_cache()
            assert decrypt_secret(ciphertext) == plaintext

    def test_decrypt_falls_back_to_previous_key(self):
        old_key = Fernet.generate_key()
        new_key = Fernet.generate_key()
        old_fernet = Fernet(old_key)

        plaintext = "secret-encrypted-with-old-key"
        ciphertext = old_fernet.encrypt(plaintext.encode()).decode()

        with (
            patch("koda.control_plane.crypto._load_master_key", return_value=new_key),
            patch("koda.control_plane.crypto._load_previous_master_key", return_value=old_key),
        ):
            from koda.control_plane.crypto import clear_fernet_cache, decrypt_secret

            clear_fernet_cache()
            assert decrypt_secret(ciphertext) == plaintext

    def test_decrypt_raises_without_previous_key(self):
        old_key = Fernet.generate_key()
        new_key = Fernet.generate_key()
        old_fernet = Fernet(old_key)

        ciphertext = old_fernet.encrypt(b"something").decode()

        with (
            patch("koda.control_plane.crypto._load_master_key", return_value=new_key),
            patch("koda.control_plane.crypto._load_previous_master_key", return_value=None),
        ):
            from koda.control_plane.crypto import clear_fernet_cache, decrypt_secret

            clear_fernet_cache()
            with pytest.raises(InvalidToken):
                decrypt_secret(ciphertext)

    def test_encrypt_always_uses_current_key(self):
        current_key = Fernet.generate_key()
        current_fernet = Fernet(current_key)
        old_key = Fernet.generate_key()

        with (
            patch("koda.control_plane.crypto._load_master_key", return_value=current_key),
            patch("koda.control_plane.crypto._load_previous_master_key", return_value=old_key),
        ):
            from koda.control_plane.crypto import clear_fernet_cache, encrypt_secret

            clear_fernet_cache()
            ciphertext = encrypt_secret("hello")
            # Must be decryptable with the current key
            assert current_fernet.decrypt(ciphertext.encode()).decode() == "hello"
            # Must NOT be decryptable with the old key
            with pytest.raises(InvalidToken):
                Fernet(old_key).decrypt(ciphertext.encode())

    def test_rotate_master_key_reencrypts(self):
        old_key = Fernet.generate_key()
        new_key = Fernet.generate_key()
        old_fernet = Fernet(old_key)
        new_fernet = Fernet(new_key)

        secrets_plain = ["secret-a", "secret-b", "secret-c"]
        old_ciphertexts = [old_fernet.encrypt(s.encode()).decode() for s in secrets_plain]

        with (
            patch("koda.control_plane.crypto._load_master_key", return_value=new_key),
            patch("koda.control_plane.crypto._load_previous_master_key", return_value=old_key),
        ):
            from koda.control_plane.crypto import clear_fernet_cache, rotate_master_key

            clear_fernet_cache()
            new_ciphertexts = rotate_master_key(old_ciphertexts)

        assert len(new_ciphertexts) == len(secrets_plain)
        for ct, expected in zip(new_ciphertexts, secrets_plain, strict=True):
            assert new_fernet.decrypt(ct.encode()).decode() == expected

    def test_clear_fernet_cache_reloads_keys(self):
        key_a = Fernet.generate_key()
        key_b = Fernet.generate_key()

        with (
            patch("koda.control_plane.crypto._load_master_key", return_value=key_a),
            patch("koda.control_plane.crypto._load_previous_master_key", return_value=None),
        ):
            from koda.control_plane.crypto import clear_fernet_cache, get_fernet

            clear_fernet_cache()
            fernet_a = get_fernet()

        with (
            patch("koda.control_plane.crypto._load_master_key", return_value=key_b),
            patch("koda.control_plane.crypto._load_previous_master_key", return_value=None),
        ):
            from koda.control_plane.crypto import clear_fernet_cache, get_fernet

            clear_fernet_cache()
            fernet_b = get_fernet()

        # After cache clear, a different key should produce a different Fernet
        assert fernet_a._signing_key != fernet_b._signing_key  # type: ignore[attr-defined]
