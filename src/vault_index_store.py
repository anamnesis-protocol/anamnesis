"""
vault_index_store.py — Persistent vault file_id storage (Supabase-backed).

Replaces per-service local .json caches (.pass_index.json, .calendar_index.json,
.drive_index.json) which are wiped on Railway container restarts/redeploys.

Storage:
  Supabase `profiles` table, `vault_file_ids` JSONB column, keyed by service name:
    {
      "pass":     "0.0.xxx",
      "calendar": "0.0.yyy",
      "notes":    "0.0.aaa",
      "totp":     "0.0.bbb",
      "drive":    {"index_file_id": "0.0.zzz"}
    }
  Lookup uses companion_token_id column — vault stores know token_id, not user UUID.

Required Supabase migration (run once in SQL editor):
  ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS vault_file_ids JSONB DEFAULT '{}';

Fallback:
  If Supabase is unavailable or the column does not exist, falls back silently to a
  local file cache at .vault_index_cache.json.
  Local cache is always written on set — for fast dev reads.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

_LOCAL_CACHE_PATH = Path(__file__).parent.parent / ".vault_index_cache.json"
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------


def _supabase():
    """Return Supabase service-role client, or None if not configured."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception as exc:
        _logger.warning("vault_index_store: Supabase client init failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Local file cache (dev / fallback)
# ---------------------------------------------------------------------------


def _load_local() -> dict:
    if not _LOCAL_CACHE_PATH.exists():
        return {}
    try:
        with open(_LOCAL_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_local(data: dict) -> None:
    try:
        with open(_LOCAL_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        _logger.warning("vault_index_store: local cache write failed: %s", exc)


# ---------------------------------------------------------------------------
# Supabase read / write
# ---------------------------------------------------------------------------


def _sb_get_all(token_id: str) -> dict | None:
    """
    Fetch full vault_file_ids JSONB for this token from Supabase.
    Returns the dict on success, None if unavailable or column missing.
    """
    sb = _supabase()
    if not sb:
        return None
    try:
        result = (
            sb.table("profiles")
            .select("vault_file_ids")
            .eq("companion_token_id", token_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            # Profile row exists but no match for this token — return empty
            return {}
        return rows[0].get("vault_file_ids") or {}
    except Exception as exc:
        _logger.warning("vault_index_store: Supabase GET failed: %s", exc)
        return None


def _sb_update(token_id: str, vault_file_ids: dict) -> bool:
    """
    Overwrite vault_file_ids for this token in Supabase.
    Returns True on success.
    """
    sb = _supabase()
    if not sb:
        return False
    try:
        sb.table("profiles").update({"vault_file_ids": vault_file_ids}).eq(
            "companion_token_id", token_id
        ).execute()
        return True
    except Exception as exc:
        _logger.warning("vault_index_store: Supabase SET failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_service_data(token_id: str, service: str) -> Any:
    """
    Get stored file_id (or nested dict) for a service.

    Returns the stored value, or None if not found.
    Checks Supabase first; falls back to local cache if Supabase is unavailable.
    """
    sb_data = _sb_get_all(token_id)
    if sb_data is not None:
        value = sb_data.get(service)
        if value is not None:
            # Warm local cache while we have the data
            local = _load_local()
            if token_id not in local:
                local[token_id] = {}
            local[token_id][service] = value
            _save_local(local)
        return value

    # Supabase unavailable — fall back to local cache
    local = _load_local()
    return local.get(token_id, {}).get(service)


def set_service_data(token_id: str, service: str, value: Any) -> None:
    """
    Store file_id (or nested dict) for a service.

    Writes to local cache first (always), then pushes to Supabase.
    The local cache acts as a fast read path and fallback.
    """
    # Always write local cache
    local = _load_local()
    if token_id not in local:
        local[token_id] = {}
    local[token_id][service] = value
    _save_local(local)

    # Push to Supabase
    sb_data = _sb_get_all(token_id)
    if sb_data is None:
        return  # Supabase unavailable — local only, log already emitted
    sb_data[service] = value
    if not _sb_update(token_id, sb_data):
        _logger.warning(
            "vault_index_store: Supabase update failed for token=%s service=%s; "
            "local cache written, but vault_file_id will be lost on Railway restart.",
            token_id,
            service,
        )
