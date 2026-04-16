"""
api/services/vault_migration.py — Vault schema versioning and auto-migration.

Every vault index stores a _schema_version field. On session open, the backend
checks this version against CURRENT_SCHEMA_VERSION and runs any pending
migrations — non-destructively — before the session proceeds.

This ensures that every companion, regardless of when it was minted, always
uses the latest vault structure. Users never have to think about upgrades.

Migration contract:
  - Migrations are idempotent: running them twice has the same effect as once
  - Migrations never delete or overwrite existing user content
  - Missing sections are added with default content; existing sections are untouched
  - Each migration bumps the schema version in the vault index
  - The session proceeds with the post-migration index

Schema version history:
  1.0  — Initial: soul, user, config, session_state
  1.1  — Added: knowledge section (context import)
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.session_store import Session

logger = logging.getLogger(__name__)

# Bump this when a new migration is added.
CURRENT_SCHEMA_VERSION = "1.1"

# Default content for sections added by migrations.
# Keep these minimal — they guide the AI without prescribing the user's content.
_MIGRATION_DEFAULTS: dict[str, str] = {
    "knowledge": (
        "# Knowledge Base\n\n"
        "This section contains documents, notes, and reference material "
        "you have imported into your companion's context.\n\n"
        "Import files via the Knowledge tab in the dashboard.\n"
    ),
}


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def _version_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def needs_migration(schema_version: str) -> bool:
    return _version_tuple(schema_version) < _version_tuple(CURRENT_SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# Individual migrations
# ---------------------------------------------------------------------------


def _migrate_1_0_to_1_1(session: "Session") -> list[str]:
    """
    1.0 → 1.1: Add the knowledge section if missing.

    Returns list of section names that were added.
    """
    added = []
    if "knowledge" not in session.full_section_ids:
        try:
            from src.vault import push_section as _push_section
            from src.crypto import derive_key

            # Derive the section key the same way session open does
            section_key = derive_key(
                session.token_id,
                session.wallet_sig,
                info=b"sovereign-ai-section-v1",
            )
            default_content = _MIGRATION_DEFAULTS["knowledge"].encode("utf-8")
            file_id = _push_section(
                "knowledge",
                default_content,
                section_key,
                session.token_id,
                existing_file_id=None,
            )
            session.full_section_ids["knowledge"] = file_id
            session.context_sections["knowledge"] = _MIGRATION_DEFAULTS["knowledge"]
            added.append("knowledge")
            logger.info(
                "vault_migration: added knowledge section for token %s -> %s",
                session.token_id,
                file_id,
            )
        except Exception as e:
            # Non-fatal: log and continue. The session proceeds without the section.
            logger.warning(
                "vault_migration: failed to add knowledge section for %s: %s",
                session.token_id,
                e,
            )
    return added


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------

# Ordered list of (from_version, to_version, migration_fn)
_MIGRATIONS: list[tuple[str, str, callable]] = [
    ("1.0", "1.1", _migrate_1_0_to_1_1),
]


def run_migrations(session: "Session") -> bool:
    """
    Check and apply any pending vault migrations for this session.

    Mutates session.full_section_ids, session.context_sections, and
    session.schema_version in place. The caller (session open) is responsible
    for flushing the updated index back to Hedera.

    Returns True if any migrations were applied (caller should update index).
    """
    current = getattr(session, "schema_version", "1.0")
    if not needs_migration(current):
        return False

    applied = False
    for from_ver, to_ver, migrate_fn in _MIGRATIONS:
        if _version_tuple(current) < _version_tuple(to_ver):
            logger.info(
                "vault_migration: applying %s -> %s for token %s",
                from_ver,
                to_ver,
                session.token_id,
            )
            added = migrate_fn(session)
            if added or True:  # always bump version even if section already existed
                current = to_ver
                applied = True

    session.schema_version = current
    return applied
