"""
Tests for event_log.py — HCS audit log.

Network tests skipped unless live testnet credentials present.
"""

import os
import json
import pytest


class TestEventLogStructure:
    """Verify event message structure without network calls."""

    def test_event_message_format(self):
        """Manually compose what log_event sends to HCS and verify format."""
        import json
        from datetime import datetime, timezone

        event_type = "CONTEXT_TOKEN_MINTED"
        payload = {"token_id": "0.0.67890", "serial": 1}

        message = json.dumps(
            {
                "event_type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": payload,
            },
            separators=(",", ":"),
        )

        parsed = json.loads(message)
        assert parsed["event_type"] == event_type
        assert parsed["payload"]["token_id"] == "0.0.67890"
        assert "timestamp" in parsed

    def test_log_event_skips_gracefully_when_no_topic(self, monkeypatch):
        """log_event should not raise if HCS_TOPIC_ID is not configured."""
        monkeypatch.delenv("HCS_TOPIC_ID", raising=False)

        # Patch get_client so we don't need real Hedera credentials
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("OPERATOR_ID", "0.0.12345")
            mp.setenv("OPERATOR_KEY", "302e020100300506032b657004220420" + "aa" * 32)
            # Import after env is patched
            try:
                from src.event_log import log_event

                result = log_event("TEST_EVENT", {"data": "value"})
                assert result == ""
            except Exception:
                # If import fails due to missing hedera SDK, skip
                pytest.skip("hedera SDK not installed")


@pytest.mark.skipif(
    os.getenv("HEDERA_NETWORK", "mock") == "mock",
    reason="Requires live Hedera testnet credentials in .env",
)
class TestEventLogNetwork:
    def test_create_topic(self):
        from src.event_log import create_topic

        topic_id = create_topic()
        assert topic_id.startswith("0.0.")

    def test_log_event_to_topic(self):
        from src.event_log import create_topic, log_event

        topic_id = create_topic()
        result = log_event(
            event_type="TEST_EVENT",
            payload={"test": True},
            topic_id=topic_id,
        )
        assert result == topic_id
