"""
Sovereign AI Context — configuration loader.
All credentials come from .env — never hardcoded.

Network selection:
 SOVEREIGN_ENV=testnet → loads .env.testnet (Hedera testnet / demo)
 SOVEREIGN_ENV unset → loads .env (Hedera mainnet / production)

Set SOVEREIGN_ENV before running any script or the API server.
"""
import os
from dotenv import load_dotenv

# Skip dotenv when running inside Railway — env vars are already injected.
# load_dotenv with override=True would clobber them with local .env values.
if not os.getenv("RAILWAY_ENVIRONMENT"):
    _env_file = ".env.testnet" if os.getenv("SOVEREIGN_ENV", "").strip().lower() == "testnet" else ".env"
    load_dotenv(_env_file, override=True)


def get_client():
    """Return a configured Hedera client for the target network."""
    from hiero_sdk_python import Client, AccountId, PrivateKey

    network = os.getenv("HEDERA_NETWORK", "testnet").lower()
    operator_id = AccountId.from_string(os.environ["OPERATOR_ID"])
    operator_key = PrivateKey.from_string(os.environ["OPERATOR_KEY"])

    if network == "mainnet":
        client = Client.for_mainnet()
    elif network == "previewnet":
        client = Client.for_previewnet()
    else:
        client = Client.for_testnet()

    client.set_operator(operator_id, operator_key)
    return client


def get_treasury():
    """Return (treasury_id, treasury_key) for token operations."""
    from hiero_sdk_python import AccountId, PrivateKey

    treasury_id = AccountId.from_string(
        os.environ.get("TREASURY_ID") or os.environ["OPERATOR_ID"]
    )
    treasury_key = PrivateKey.from_string(
        os.environ.get("TREASURY_KEY") or os.environ["OPERATOR_KEY"]
    )
    return treasury_id, treasury_key


def get_validator_contract_id():
    """Return the deployed EVM validation contract ID, or None if not yet deployed."""
    raw = os.getenv("VALIDATOR_CONTRACT_ID")
    if not raw:
        return None
    # ContractId not needed until contract deployment — return raw string for now
    return raw
