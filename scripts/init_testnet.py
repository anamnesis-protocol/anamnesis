"""
init_testnet.py — Testnet setup for Sovereign AI Context demo.

Runs one-time setup on Hedera testnet:
 1. Create HCS audit topic
 2. Deploy ContextValidator contract
 3. Write IDs to .env.testnet

Unlike init_mainnet.py, this script does NOT mint a context token or push vault
sections — the SaaS API (/user/provision/*) handles those per-user during the demo.

Prerequisites:
 .env.testnet must exist with:
 HEDERA_NETWORK=testnet
 OPERATOR_ID=0.0.XXXXX (testnet account — get from portal.hedera.com)
 OPERATOR_KEY=302e... (ED25519 private key for that account)
 TREASURY_ID=0.0.XXXXX (can be same as OPERATOR_ID)
 TREASURY_KEY=302e... (can be same as OPERATOR_KEY)

 HBAR funding: testnet accounts start with 10,000 HBAR from the faucet.
 Estimated cost: ~0.5 HBAR for this script (HCS + contract deploy).

Usage:
 cd D:\\code\\sovereign-ai-context
 python scripts/init_testnet.py
 python scripts/init_testnet.py --force # overwrite existing IDs
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

sys.path.insert(0, str(Path(__file__).parent.parent))

ENV_PATH = Path(__file__).parent.parent / ".env.testnet"


def reload_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=True)


def write_env(key: str, value: str) -> None:
    set_key(str(ENV_PATH), key, value)
    os.environ[key] = value
    print(f" .env.testnet -> {key}={value}")


# ---------------------------------------------------------------------------
# Prereq check
# ---------------------------------------------------------------------------


def check_prereqs(force: bool) -> None:
    if not ENV_PATH.exists():
        print(f"[ERROR] {ENV_PATH} not found.")
        print(" Copy .env.testnet.example to .env.testnet and fill in your testnet credentials.")
        sys.exit(1)

    reload_env()

    network = os.getenv("HEDERA_NETWORK", "").strip().lower()
    if network != "testnet":
        print(f"[ERROR] HEDERA_NETWORK={network!r} — must be 'testnet' in .env.testnet.")
        sys.exit(1)

    for required in ("OPERATOR_ID", "OPERATOR_KEY"):
        if not os.getenv(required, "").strip():
            print(f"[ERROR] {required} not set in .env.testnet")
            sys.exit(1)

    already_set = {}
    for k in ("HCS_TOPIC_ID", "VALIDATOR_CONTRACT_ID"):
        v = os.getenv(k, "").strip().strip("'\"")
        if v and not v.startswith("0.0.X"):
            already_set[k] = v

    if already_set and not force:
        print("[ERROR] Some IDs are already set in .env.testnet:")
        for k, v in already_set.items():
            print(f" {k}={v}")
        print(" Use --force to overwrite, or clear them manually.")
        sys.exit(1)

    op_id = os.getenv("OPERATOR_ID")
    print(f"\n[OK] Prereqs verified.")
    print(f" Network: testnet")
    print(f" Operator: {op_id}")
    print()


# ---------------------------------------------------------------------------
# Step 1: HCS Topic
# ---------------------------------------------------------------------------


def step1_create_topic() -> str:
    print("[1/2] Creating HCS audit topic on testnet...")
    from src.event_log import create_topic

    topic_id = create_topic()
    write_env("HCS_TOPIC_ID", topic_id)
    print(f" HCS topic: {topic_id}\n")
    return topic_id


# ---------------------------------------------------------------------------
# Step 2: Deploy ContextValidator contract
# ---------------------------------------------------------------------------


def step2_deploy_contract() -> str:
    print("[2/2] Deploying ContextValidator contract on testnet...")
    from src.contract import deploy_contract

    contract_id = deploy_contract()
    write_env("VALIDATOR_CONTRACT_ID", contract_id)
    print(f" Contract: {contract_id}\n")
    return contract_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Sovereign AI Context — testnet demo setup")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing IDs in .env.testnet"
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" Sovereign AI Context — Testnet Demo Setup")
    print("=" * 60)

    check_prereqs(args.force)

    topic_id = step1_create_topic()
    contract_id = step2_deploy_contract()

    print("=" * 60)
    print(" TESTNET SETUP COMPLETE")
    print("=" * 60)
    print(f" HCS topic: {topic_id}")
    print(f" Contract: {contract_id}")
    print()
    print(" Start the demo server:")
    print(" demo_testnet.bat")
    print(" or:")
    print(" set SOVEREIGN_ENV=testnet && python -m uvicorn api.main:app --reload --port 8000")
    print()
    print(" Then open: http://localhost:8000/demo")
    print("=" * 60)


if __name__ == "__main__":
    main()
