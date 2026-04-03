"""
api/models.py — Pydantic request/response models for the Sovereign AI SaaS API.

Session open flow:
 1. Client calls /session/challenge with their context_token_id
 2. Client's wallet signs the returned challenge bytes
 3. Client calls /session/open with token_id + wallet_signature_hex
 Server derives key: HKDF(token_id || wallet_sig)
 Server fetches + decrypts HFS context → auth succeeds if AES-GCM tag is valid
 4. Client receives session_id + context sections (system prompt material)
 5. Client calls /session/close when session ends → SESSION_ENDED logged to HCS
"""

from pydantic import BaseModel, Field


class ChallengeRequest(BaseModel):
 token_id: str = Field(
 description="Context token ID (e.g. '0.0.10376966'). Must have a registered vault index."
 )


class ChallengeResponse(BaseModel):
 token_id: str
 challenge_hex: str = Field(
 description="Hex-encoded bytes for the wallet to sign (Ed25519 or secp256k1)."
 )


class SessionOpenRequest(BaseModel):
 token_id: str = Field(
 description="Context token ID. Must match the token used for /session/challenge."
 )
 wallet_signature_hex: str = Field(
 description=(
 "Hex-encoded wallet signature over the challenge bytes. "
 "Ed25519: 64 bytes. secp256k1: 65 bytes (recoverable). "
 "Auth succeeds if AES-GCM decryption succeeds with the derived key."
 )
 )
 serial: int = Field(
 default=1,
 description="NFT serial number (default 1 — most tokens use serial 1).",
 )


class SessionOpenResponse(BaseModel):
 session_id: str = Field(description="UUID — pass to /session/close when session ends.")
 token_id: str
 context_sections: dict[str, str] = Field(
 description=(
 "Identity section content (soul, user, symbiote, session_state) as UTF-8 strings. "
 "Inject into your AI model's system prompt before the user turn."
 )
 )
 sections_loaded: list[str]
 created_at: str
 expires_at: str


class SessionCloseRequest(BaseModel):
 session_id: str = Field(description="Session UUID returned by /session/open.")
 updated_sections: dict[str, str] = Field(
 default_factory=dict,
 description=(
 "Updated vault section content to write back to Hedera. "
 "Keys are section names (e.g. 'soul', 'memory'). Values are UTF-8 strings. "
 "Only sections whose content differs from session-open hashes will be pushed. "
 "Omit a section to leave it unchanged. Empty dict = read-only session."
 ),
 )


class SessionCloseResponse(BaseModel):
 session_id: str
 closed_at: str
 changed_sections: list[str] = Field(
 description="Sections whose content changed and were pushed back to Hedera."
 )
 hcs_logged: bool = Field(description="True if SESSION_ENDED was logged to HCS.")
 vault_updated: bool = Field(
 description="True if any sections were re-encrypted and pushed to Hedera."
 )


class ErrorResponse(BaseModel):
 error: str
 detail: str = ""


# ---------------------------------------------------------------------------
# User provisioning models
# ---------------------------------------------------------------------------

class ProvisionStartRequest(BaseModel):
 account_id: str = Field(
 description="User's Hedera account ID (e.g. '0.0.12345'). "
 "Context token will be minted under the operator treasury and associated to this account."
 )
 companion_name: str = Field(
 default="Assistant",
 description="Name for the AI companion (used in context token metadata and default vault content).",
 )


class ProvisionStartResponse(BaseModel):
 token_id: str = Field(description="Newly minted context token ID. Use this in /provision/complete.")
 challenge_hex: str = Field(
 description=(
 "Hex-encoded challenge bytes for the wallet to sign. "
 "This is the same challenge used by /session/open — "
 "once you complete provisioning, the same signature opens your first session."
 )
 )
 expires_at: str = Field(description="ISO timestamp — provisioning must be completed before this time.")


class ProvisionCompleteRequest(BaseModel):
 token_id: str = Field(description="Context token ID returned by /provision/start.")
 wallet_signature_hex: str = Field(
 description=(
 "Hex-encoded wallet signature over the challenge from /provision/start. "
 "Used to derive the vault encryption key — keep the sig, you'll need it for /session/open."
 )
 )


class ProvisionCompleteResponse(BaseModel):
 token_id: str
 sections_pushed: list[str]
 index_file_id: str
 vault_registered: bool
 message: str


class UserStatusResponse(BaseModel):
 token_id: str
 registered: bool
 index_file_id: str | None = None
 message: str


# ---------------------------------------------------------------------------
# Dir bundle models
# ---------------------------------------------------------------------------

class BundlePushRequest(BaseModel):
 session_id: str = Field(description="Active session UUID from /session/open.")
 bundle_name: str = Field(
 description=(
 "Bundle name — alphanumeric, hyphens, underscores, max 64 chars. "
 "Stored on HFS as 'dir:{bundle_name}'. "
 "Examples: 'sessions', 'projects', 'research-notes'."
 )
 )
 files: dict[str, str] = Field(
 description=(
 "Files to bundle: {relative_path: utf-8 content}. "
 "Example: {'2026-03-17-session.md': '# Session\\n...'}"
 )
 )


class BundlePushResponse(BaseModel):
 bundle_name: str = Field(description="Bundle name as stored (without 'dir:' prefix).")
 file_id: str = Field(description="HFS file ID where the bundle is stored.")
 files_stored: int = Field(description="Number of files in the bundle.")
 hcs_logged: bool = Field(description="True if BUNDLE_PUSHED was logged to HCS.")


class BundleListResponse(BaseModel):
 bundles: list[str] = Field(
 description="Names of dir bundles available in this vault (without 'dir:' prefix)."
 )


class BundlePullResponse(BaseModel):
 bundle_name: str
 files: dict[str, str] = Field(
 description="Bundle contents: {relative_path: utf-8 content string}."
 )
