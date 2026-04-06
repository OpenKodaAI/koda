"""Tests for audit retention cleanup in koda.services.audit."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.audit import cleanup_expired_audit_events


class TestCleanupExpiredAuditEvents:
    """cleanup_expired_audit_events should respect retention config and backend availability."""

    @pytest.mark.asyncio
    async def test_no_backend_returns_zero(self):
        with patch("koda.services.audit._primary_audit_backend", return_value=None):
            result = await cleanup_expired_audit_events()
        assert result == 0

    @pytest.mark.asyncio
    async def test_backend_without_delete_method_returns_zero(self):
        backend = MagicMock(spec=[])  # no delete_audit_events_before attribute
        with patch("koda.services.audit._primary_audit_backend", return_value=backend):
            result = await cleanup_expired_audit_events()
        assert result == 0

    @pytest.mark.asyncio
    async def test_successful_cleanup(self):
        backend = MagicMock()
        backend.delete_audit_events_before = AsyncMock(return_value=42)
        with (
            patch("koda.services.audit._primary_audit_backend", return_value=backend),
            patch("koda.services.audit.config_module") as cfg,
        ):
            cfg.AUDIT_RETENTION_DAYS = 90
            result = await cleanup_expired_audit_events()
        assert result == 42
        backend.delete_audit_events_before.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_exception_returns_zero(self):
        backend = MagicMock()
        backend.delete_audit_events_before = AsyncMock(side_effect=RuntimeError("db down"))
        with (
            patch("koda.services.audit._primary_audit_backend", return_value=backend),
            patch("koda.services.audit.config_module") as cfg,
        ):
            cfg.AUDIT_RETENTION_DAYS = 30
            result = await cleanup_expired_audit_events()
        assert result == 0

    @pytest.mark.asyncio
    async def test_respects_retention_days_config(self):
        backend = MagicMock()
        backend.delete_audit_events_before = AsyncMock(return_value=5)
        with (
            patch("koda.services.audit._primary_audit_backend", return_value=backend),
            patch("koda.services.audit.config_module") as cfg,
        ):
            cfg.AUDIT_RETENTION_DAYS = 7
            result = await cleanup_expired_audit_events()
        assert result == 5
        # Verify the cutoff was passed as a string (ISO format)
        cutoff_arg = backend.delete_audit_events_before.call_args[0][0]
        assert isinstance(cutoff_arg, str)
        assert "T" in cutoff_arg  # ISO format contains T separator
