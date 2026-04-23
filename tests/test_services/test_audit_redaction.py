"""Tests for audit redaction logic in koda.services.audit."""

from koda.services.audit import _prepare_details, _redact_string, _sanitize_payload


class TestRedactStringBearerTokens:
    """Bearer tokens must be redacted from inline text."""

    def test_bearer_token_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc123"
        result, changed = _redact_string(text)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "[REDACTED]" in result
        assert changed is True

    def test_bearer_prefix_alone(self):
        text = "bearer sk-abc123def456"
        result, changed = _redact_string(text)
        assert "sk-abc123def456" not in result
        assert "[REDACTED]" in result
        assert changed is True

    def test_authorization_header_format(self):
        text = "authorization: bearer my-secret-token.value"
        result, changed = _redact_string(text)
        assert "my-secret-token.value" not in result
        assert changed is True


class TestRedactStringApiKeysInQueryStrings:
    """API keys in query strings must be redacted."""

    def test_api_key_in_url(self):
        text = "https://api.example.com/v1?api_key=sk-12345abcdef"
        result, changed = _redact_string(text)
        assert "sk-12345abcdef" not in result
        assert "[REDACTED]" in result
        assert changed is True

    def test_access_token_in_url(self):
        text = "https://example.com/api?access_token=ghp_abcdefghij123456"
        result, changed = _redact_string(text)
        assert "ghp_abcdefghij123456" not in result
        assert changed is True

    def test_token_in_url(self):
        text = "https://example.com/api?token=mytoken123"
        result, changed = _redact_string(text)
        assert "mytoken123" not in result
        assert changed is True

    def test_password_in_url(self):
        text = "https://example.com/api?password=hunter2"
        result, changed = _redact_string(text)
        assert "hunter2" not in result
        assert changed is True

    def test_secret_in_url(self):
        text = "https://example.com/webhook?secret=s3cr3t_value"
        result, changed = _redact_string(text)
        assert "s3cr3t_value" not in result
        assert changed is True

    def test_multiple_query_params(self):
        text = "https://example.com?api_key=key123&token=tok456&name=safe"
        result, changed = _redact_string(text)
        assert "key123" not in result
        assert "tok456" not in result
        assert changed is True


class TestRedactStringPasswordsInKeyValuePairs:
    """Passwords in key=value pairs must be redacted."""

    def test_password_equals(self):
        text = "password=supersecret123"
        result, changed = _redact_string(text)
        assert "supersecret123" not in result
        assert "[REDACTED]" in result
        assert changed is True

    def test_secret_equals(self):
        text = "secret=my_secret_value"
        result, changed = _redact_string(text)
        assert "my_secret_value" not in result
        assert changed is True

    def test_api_key_equals(self):
        text = "api_key=sk-abcdef1234567890"
        result, changed = _redact_string(text)
        assert "sk-abcdef1234567890" not in result
        assert changed is True

    def test_access_token_equals(self):
        text = "access_token=ghp_0123456789abcdef"
        result, changed = _redact_string(text)
        assert "ghp_0123456789abcdef" not in result
        assert changed is True

    def test_cookie_equals(self):
        text = "cookie=session_abc123"
        result, changed = _redact_string(text)
        assert "session_abc123" not in result
        assert changed is True


class TestRedactStringNormalTextUnchanged:
    """Normal text without secrets must NOT be altered."""

    def test_plain_text_unchanged(self):
        text = "Hello, this is a normal log message."
        result, changed = _redact_string(text)
        assert result == text
        assert changed is False

    def test_code_snippet_unchanged(self):
        text = "def my_function(): return 42"
        result, changed = _redact_string(text)
        assert result == text
        assert changed is False

    def test_url_without_secrets_unchanged(self):
        text = "https://example.com/page?id=123&format=json"
        result, changed = _redact_string(text)
        assert result == text
        assert changed is False

    def test_empty_string_unchanged(self):
        result, changed = _redact_string("")
        assert result == ""
        assert changed is False

    def test_numeric_text_unchanged(self):
        text = "Processing 42 items in batch 7"
        result, changed = _redact_string(text)
        assert result == text
        assert changed is False


class TestRedactStringCombinedPatterns:
    """Combined and nested patterns must all be redacted."""

    def test_multiple_secrets_in_one_string(self):
        text = "Authorization: Bearer tok123 with api_key=sk-456"
        result, changed = _redact_string(text)
        assert "tok123" not in result
        assert "sk-456" not in result
        assert changed is True

    def test_bearer_and_query_param(self):
        text = "bearer xyztoken123 calling https://api.com?secret=abc"
        result, changed = _redact_string(text)
        assert "xyztoken123" not in result
        assert "abc" not in result
        assert changed is True


class TestSanitizePayloadSensitiveKeys:
    """Dict keys matching sensitive patterns must be fully redacted."""

    def test_authorization_key_redacted(self):
        data = {"authorization": "Bearer tok123", "message": "hello"}
        result, fields = _sanitize_payload(data)
        assert result["authorization"] == "[REDACTED]"
        assert result["message"] == "hello"
        assert "authorization" in fields

    def test_token_key_redacted(self):
        data = {"token": "abc123", "status": "ok"}
        result, fields = _sanitize_payload(data)
        assert result["token"] == "[REDACTED]"
        assert result["status"] == "ok"

    def test_api_key_key_redacted(self):
        data = {"api_key": "sk-abc", "name": "test"}
        result, fields = _sanitize_payload(data)
        assert result["api_key"] == "[REDACTED]"
        assert result["name"] == "test"

    def test_password_key_redacted(self):
        data = {"password": "hunter2", "user": "admin"}
        result, fields = _sanitize_payload(data)
        assert result["password"] == "[REDACTED]"
        assert result["user"] == "admin"

    def test_secret_key_redacted(self):
        data = {"secret": "s3cr3t"}
        result, fields = _sanitize_payload(data)
        assert result["secret"] == "[REDACTED]"

    def test_credentials_key_redacted(self):
        data = {"credentials": {"user": "admin", "pass": "123"}}
        result, fields = _sanitize_payload(data)
        assert result["credentials"] == "[REDACTED]"

    def test_nested_sensitive_key_redacted(self):
        data = {"config": {"api_key": "sk-123", "endpoint": "https://api.com"}}
        result, fields = _sanitize_payload(data)
        assert result["config"]["api_key"] == "[REDACTED]"
        assert result["config"]["endpoint"] == "https://api.com"
        assert "config.api_key" in fields

    def test_list_with_sensitive_dicts(self):
        data = [{"token": "abc"}, {"name": "safe"}]
        result, fields = _sanitize_payload(data)
        assert result[0]["token"] == "[REDACTED]"
        assert result[1]["name"] == "safe"


class TestPrepareDetails:
    """_prepare_details adds redaction metadata when secrets are found."""

    def test_redactions_metadata_added(self):
        details = {"authorization": "Bearer tok", "message": "hi"}
        result = _prepare_details(details)
        assert "redactions" in result
        assert result["redactions"]["count"] >= 1
        assert "authorization" in result["redactions"]["fields"]

    def test_no_redactions_metadata_when_clean(self):
        details = {"message": "hello", "status": "ok"}
        result = _prepare_details(details)
        assert "redactions" not in result

    def test_inline_secret_redacted_in_values(self):
        details = {"log": "Authorization: Bearer mytoken123"}
        result = _prepare_details(details)
        assert "mytoken123" not in str(result)
        assert "redactions" in result
