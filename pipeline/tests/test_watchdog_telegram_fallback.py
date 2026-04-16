"""Tests for Telegram send + log fallback."""

from unittest.mock import patch, MagicMock

import pytest

from pipeline.watchdog_alerts import send_or_log_digest


class TestSendOrLogDigest:
    def test_happy_path_calls_send_alert(self, tmp_path):
        digest = "🚨 test digest"
        fallback_log = tmp_path / "watchdog_alerts.log"
        mock_send = MagicMock(return_value=True)
        with patch("pipeline.watchdog_alerts._send_alert", mock_send):
            ok = send_or_log_digest(digest, fallback_log=fallback_log, dry_run=False)
        assert ok is True
        mock_send.assert_called_once()
        assert not fallback_log.exists()  # no fallback needed

    def test_telegram_failure_writes_fallback_log(self, tmp_path):
        digest = "🚨 test digest"
        fallback_log = tmp_path / "watchdog_alerts.log"
        mock_send = MagicMock(side_effect=RuntimeError("token revoked"))
        with patch("pipeline.watchdog_alerts._send_alert", mock_send):
            ok = send_or_log_digest(digest, fallback_log=fallback_log, dry_run=False)
        assert ok is False
        assert fallback_log.exists()
        content = fallback_log.read_text()
        assert "TELEGRAM_FAILED" in content
        assert "test digest" in content
        assert "token revoked" in content

    def test_dry_run_skips_telegram(self, tmp_path):
        digest = "🚨 test digest"
        fallback_log = tmp_path / "watchdog_alerts.log"
        mock_send = MagicMock()
        with patch("pipeline.watchdog_alerts._send_alert", mock_send):
            ok = send_or_log_digest(digest, fallback_log=fallback_log, dry_run=True)
        assert ok is True
        mock_send.assert_not_called()
        assert not fallback_log.exists()
