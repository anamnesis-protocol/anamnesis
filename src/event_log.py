"""
event_log.py — HCS Audit Trail

All sovereign context operations are logged to a Hedera Consensus Service topic.

Usage:
 from src.event_log import create_topic, log_event

 topic_id = create_topic() # once, store in .env as HCS_TOPIC_ID
 log_event("CONTEXT_LOADED", {...}) # every significant operation
"""

import json
import os
from datetime import datetime, timezone

from hiero_sdk_python import (
 TopicCreateTransaction,
 TopicMessageSubmitTransaction,
 TopicId,
)
from src.config import get_client, get_treasury


def create_topic() -> str:
 """
 Create a new HCS topic for sovereign context event logging.

 Security: sets treasury public key as the submit key, restricting
 message submission to parties holding the treasury private key.
 This prevents audit log poisoning by unauthorized accounts.
 (Security audit fix H2 — see Research/2026-03-16_security-audit-sovereign-ai-context.md)

 Returns:
 topic_id as string (e.g. "0.0.11111"). Store in .env as HCS_TOPIC_ID.
 """
 client = get_client()
 _, treasury_key = get_treasury()

 tx = (
 TopicCreateTransaction()
 .set_memo("sovereign-ai-context audit log")
 .set_submit_key(treasury_key.public_key()) # Only treasury can submit events
 .freeze_with(client)
 .sign(treasury_key)
 )

 receipt = tx.execute(client)
 return str(receipt.topic_id)


def log_event(event_type: str, payload: dict, topic_id: str | None = None) -> str:
 """
 Submit a structured event to the HCS audit topic.

 Args:
    event_type: String label (CONTEXT_TOKEN_MINTED, CONTEXT_STORED, CONTEXT_LOADED, etc.)
    payload: Dict of event-specific fields
    topic_id: HCS topic ID. Falls back to HCS_TOPIC_ID env var.

 Returns:
 topic_id used (empty string if topic not configured)
 """
 if topic_id is None:
 topic_id = os.environ.get("HCS_TOPIC_ID")
 if not topic_id:
 return "" # Graceful degradation — topic not yet created

 client = get_client()
 _, treasury_key = get_treasury()

 message = json.dumps({
 "event_type": event_type,
 "timestamp": datetime.now(timezone.utc).isoformat(),
 "payload": payload,
 }, separators=(",", ":"))

 (
 TopicMessageSubmitTransaction()
 .set_topic_id(TopicId.from_string(topic_id))
 .set_message(message)
 .freeze_with(client)
 .sign(treasury_key) # Required for topics with a submit key (H2 fix)
 .execute(client)
 )

 return topic_id
