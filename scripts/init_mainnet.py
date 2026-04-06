"""
init_mainnet.py — Full Mainnet Initialization for Sovereign AI Context

Runs the complete mainnet deployment sequence end-to-end. All generated IDs
are written back to .env automatically. Safe to run once — will abort if
IDs are already set (prevents accidental re-init).

Sequence:
1. Verify prereqs (mainnet creds set, IDs empty)
2. Create HCS audit topic (secured with treasury submit key)
3. Create genesis HFS file (anchor for context token memo)
4. Mint SOUL NFT (immutable, serial 1, no admin/supply key)
5. Push vault sections to HFS (subprocess — fresh env read)
6. Push memory packages to HFS (subprocess — fresh env read)
7. Deploy ContextValidator v2 contract
8. Register vault index in contract + verify

Usage:
cd D:\\code\\sovereign-ai-context
python scripts/init_mainnet.py
python scripts/init_mainnet.py --skip-packages # skip heavy package push
python scripts/init_mainnet.py --force # allow re-init (clears existing IDs)

Requirements:
.env must contain: HEDERA_NETWORK=mainnet, OPERATOR_ID, OPERATOR_KEY
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv, set_key

# Make src/ importable
sys.path.insert(0, str(Path(__file__).parent.parent))

ENV_PATH = Path(__file__).parent.parent / ".env"
VAULT_INDEX_CACHE = Path(__file__).parent.parent / ".vault_index.json"


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


def reload_env() -> None:
    """Reload .env into os.environ (override=True so updates are visible)."""
    load_dotenv(dotenv_path=ENV_PATH, override=True)

    def write_env(key: str, value: str) -> None:
        """Write key=value to .env and update current process env."""
        set_key(str(ENV_PATH), key, value)
        os.environ[key] = value
        print(f" .env -> {key}={value}")

        # ---------------------------------------------------------------------------
        # Step 0: Prereq check
        # ---------------------------------------------------------------------------

        def check_prereqs(force: bool) -> None:
            reload_env()

            network = os.getenv("HEDERA_NETWORK", "").strip().lower()
            if network != "mainnet":
                print(
                    f"[ERROR] HEDERA_NETWORK={network!r} — must be 'mainnet'. Update .env and retry."
                )
                sys.exit(1)

                for required in ("OPERATOR_ID", "OPERATOR_KEY", "TREASURY_ID", "TREASURY_KEY"):
                    if not os.getenv(required, "").strip():
                        print(f"[ERROR] {required} not set in .env")
                        sys.exit(1)

                        id_fields = ("HCS_TOPIC_ID", "CONTEXT_TOKEN_ID", "VALIDATOR_CONTRACT_ID")
                        already_set = {
                            k: os.getenv(k, "").strip().strip("'\"")
                            for k in id_fields
                            if os.getenv(k, "").strip().strip("'\"")
                        }

                        if already_set and not force:
                            print("[ERROR] Some IDs are already set in .env:")
                            for k, v in already_set.items():
                                print(f" {k}={v}")
                                print(" Use --force to overwrite, or clear them manually first.")
                                sys.exit(1)

                                if force and already_set:
                                    print("[WARN] --force: overwriting existing IDs:")
                                    for k, v in already_set.items():
                                        print(f" {k}={v} -> will be replaced")
                                        # Clear local vault cache too
                                        if VAULT_INDEX_CACHE.exists():
                                            VAULT_INDEX_CACHE.unlink()
                                            print(
                                                f" Cleared local vault cache: {VAULT_INDEX_CACHE.name}"
                                            )

                                            op_id = os.getenv("OPERATOR_ID")
                                            print(f"\n[OK] Prereqs verified.")
                                            print(f" Network: mainnet")
                                            print(f" Operator: {op_id}")
                                            print()

                                            # ---------------------------------------------------------------------------
                                            # Step 1: HCS Topic
                                            # ---------------------------------------------------------------------------

            def step1_create_topic() -> str:
                print("[1/7] Creating HCS audit topic (secured with treasury submit key)...")
                from src.event_log import create_topic

                topic_id = create_topic()
                write_env("HCS_TOPIC_ID", topic_id)
                print(f" HCS topic: {topic_id}\n")
                return topic_id

                # ---------------------------------------------------------------------------
                # Step 2: Genesis HFS file
                # ---------------------------------------------------------------------------

                def step2_create_genesis_file() -> str:
                    """
                    Create a minimal HFS file as the anchor reference for the context token memo.
                    This is not the encrypted vault — just a genesis marker. The contract
                    is the authority for finding the real vault index.
                    """
                    print("[2/7] Creating genesis HFS file (context token anchor)...")
                    from hiero_sdk_python import FileCreateTransaction
                    from src.config import get_client, get_treasury

                    client = get_client()
                    _, treasury_key = get_treasury()

                    genesis_content = json.dumps(
                        {
                            "type": "sovereign-ai-context-genesis",
                            "version": "2.0",
                            "network": "mainnet",
                            "note": "Anchor file for context token. Vault index is registered in ContextValidator contract.",
                        },
                        indent=2,
                    ).encode("utf-8")

                    tx = (
                        FileCreateTransaction()
                        .set_contents(genesis_content)
                        .set_keys([treasury_key.public_key()])
                        .freeze_with(client)
                        .sign(treasury_key)
                    )

                    receipt = tx.execute(client)
                    file_id = str(receipt.file_id)
                    write_env("CONTEXT_FILE_ID", file_id)
                    print(f" Genesis file: {file_id}\n")
                    return file_id

                    # ---------------------------------------------------------------------------
                    # Step 3: Mint CONTEXT TOKEN
                    # ---------------------------------------------------------------------------

                    def step3_mint_CONTEXT_TOKEN(genesis_file_id: str) -> str:
                        print("[3/7] Minting CONTEXT TOKEN (immutable — no admin/supply key)...")
                        from src.context_token import mint_CONTEXT_TOKEN

                        token_id = mint_CONTEXT_TOKEN(
                            context_file_id=genesis_file_id, companion_name="Assistant"
                        )
                        write_env("CONTEXT_TOKEN_ID", token_id)
                        print(f" Context token: {token_id}\n")
                        return token_id

                        # ---------------------------------------------------------------------------
                        # Step 4: Push vault sections (subprocess for fresh env)
                        # ---------------------------------------------------------------------------

                        def step4_push_vault() -> str:
                            print("[4/7] Pushing vault sections to HFS (force-new)...")
                            # Clear stale local cache so vault_push creates fresh mainnet files
                            if VAULT_INDEX_CACHE.exists():
                                VAULT_INDEX_CACHE.unlink()

                                result = subprocess.run(
                                    [sys.executable, "scripts/vault_push.py", "--force-new"],
                                    cwd=str(Path(__file__).parent.parent),
                                )
                                if result.returncode != 0:
                                    print("[ERROR] vault_push.py failed — check output above.")
                                    sys.exit(1)

                                    # Read vault index file ID from local cache
                                    if not VAULT_INDEX_CACHE.exists():
                                        print(
                                            "[ERROR] .vault_index.json not found after vault_push. Cannot continue."
                                        )
                                        sys.exit(1)

                                        with open(VAULT_INDEX_CACHE, encoding="utf-8") as f:
                                            cache = json.load(f)

                                            vault_index_file_id = cache.get("index_file_id", "")
                                            if not vault_index_file_id:
                                                print(
                                                    f"[ERROR] index_file_id missing from .vault_index.json: {cache}"
                                                )
                                                sys.exit(1)

                                                print(f"\n Vault index: {vault_index_file_id}\n")
                                                return vault_index_file_id

                                                # ---------------------------------------------------------------------------
                                                # Step 5: Push memory packages (subprocess for fresh env)
                                                # ---------------------------------------------------------------------------

                            def step5_push_packages() -> None:
                                print("[5/7] Pushing memory packages to HFS (force-new)...")
                                result = subprocess.run(
                                    [sys.executable, "scripts/package_push.py", "--force-new"],
                                    cwd=str(Path(__file__).parent.parent),
                                )
                                if result.returncode != 0:
                                    print("[ERROR] package_push.py failed — check output above.")
                                    sys.exit(1)
                                    print()

                                    # ---------------------------------------------------------------------------
                                    # Step 6: Deploy contract
                                    # ---------------------------------------------------------------------------

                                def step6_deploy_contract() -> str:
                                    print("[6/7] Deploying ContextValidator v2 to mainnet...")
                                    from src.contract import deploy_contract

                                    contract_id = deploy_contract()
                                    write_env("VALIDATOR_CONTRACT_ID", contract_id)
                                    print(f" Contract: {contract_id}\n")
                                    return contract_id

                                    # ---------------------------------------------------------------------------
                                    # Step 7: Register vault index + verify
                                    # ---------------------------------------------------------------------------

                                    def step7_register_and_verify(
                                        contract_id: str, vault_index_file_id: str
                                    ) -> None:
                                        print(
                                            "[7/7] Registering vault index in contract + verifying..."
                                        )
                                        reload_env()
                                        from src.contract import (
                                            register_file,
                                            token_id_to_evm_address,
                                            get_registered_file_id,
                                        )

                                        CONTEXT_TOKEN_id = os.environ["CONTEXT_TOKEN_ID"]
                                        token_evm = token_id_to_evm_address(CONTEXT_TOKEN_id)

                                        register_file(
                                            contract_id,
                                            token_evm,
                                            serial=1,
                                            file_id=vault_index_file_id,
                                        )

                                        registered = get_registered_file_id(
                                            contract_id, token_evm, serial=1
                                        )
                                        if registered != vault_index_file_id:
                                            print(
                                                f"[ERROR] Registration mismatch! Expected {vault_index_file_id!r}, got {registered!r}"
                                            )
                                            sys.exit(1)

                                            print(
                                                f" Registered: {vault_index_file_id} [verified]\n"
                                            )

                                            # ---------------------------------------------------------------------------
                                            # Main
                                            # ---------------------------------------------------------------------------

                                        def main():
                                            parser = argparse.ArgumentParser(
                                                description="Full mainnet initialization for Sovereign AI Context",
                                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                                epilog="""
                                            Examples:
                                            python scripts/init_mainnet.py # full init
                                            python scripts/init_mainnet.py --skip-packages # skip memory package push
                                            python scripts/init_mainnet.py --force # re-init (clears existing IDs)
                                            """,
                                            )
                                            parser.add_argument(
                                                "--skip-packages",
                                                action="store_true",
                                                help="Skip memory package push (vault sections only)",
                                            )
                                            parser.add_argument(
                                                "--force",
                                                action="store_true",
                                                help="Allow re-initialization even if IDs already exist in .env",
                                            )
                                            parser.add_argument(
                                                "--resume",
                                                action="store_true",
                                                help="Resume a partial init — skip steps where IDs are already set in .env",
                                            )
                                            args = parser.parse_args()

                                            print("=" * 60)
                                            print(" Sovereign AI Context - Mainnet Init")
                                            print("=" * 60)

                                            check_prereqs(force=args.force or args.resume)

                                            reload_env()

                                            # Step 1
                                            topic_id = (
                                                os.getenv("HCS_TOPIC_ID", "").strip().strip("'\"")
                                            )
                                            if topic_id and args.resume:
                                                print(
                                                    f"[1/7] HCS topic already set: {topic_id} (skipping)"
                                                )
                                            else:
                                                topic_id = step1_create_topic()

                                                # Step 2
                                                genesis_file_id = (
                                                    os.getenv("CONTEXT_FILE_ID", "")
                                                    .strip()
                                                    .strip("'\"")
                                                )
                                                if genesis_file_id and args.resume:
                                                    print(
                                                        f"[2/7] Genesis file already set: {genesis_file_id} (skipping)"
                                                    )
                                                else:
                                                    genesis_file_id = step2_create_genesis_file()

                                                    # Step 3
                                                    token_id = (
                                                        os.getenv("CONTEXT_TOKEN_ID", "")
                                                        .strip()
                                                        .strip("'\"")
                                                    )
                                                    if token_id and args.resume:
                                                        print(
                                                            f"[3/7] Context token already set: {token_id} (skipping)"
                                                        )
                                                    else:
                                                        token_id = step3_mint_CONTEXT_TOKEN(
                                                            genesis_file_id
                                                        )

                                                        # Step 4
                                                        vault_index_file_id = step4_push_vault()

                                                        # Step 5
                                                        if args.skip_packages:
                                                            print(
                                                                "[5/7] Skipping packages (--skip-packages)\n"
                                                            )
                                                        else:
                                                            step5_push_packages()

                                                            # Step 6
                                                            contract_id = (
                                                                os.getenv(
                                                                    "VALIDATOR_CONTRACT_ID", ""
                                                                )
                                                                .strip()
                                                                .strip("'\"")
                                                            )
                                                            if contract_id and args.resume:
                                                                print(
                                                                    f"[6/7] Contract already set: {contract_id} (skipping)"
                                                                )
                                                            else:
                                                                contract_id = (
                                                                    step6_deploy_contract()
                                                                )

                                                                # Step 7
                                                                step7_register_and_verify(
                                                                    contract_id, vault_index_file_id
                                                                )

                                                                print("=" * 60)
                                                                print(" MAINNET INIT COMPLETE")
                                                                print("=" * 60)
                                                                print(f" HCS topic: {topic_id}")
                                                                print(f" Context token: {token_id}")
                                                                print(
                                                                    f" Vault index: {vault_index_file_id}"
                                                                )
                                                                print(f" Contract: {contract_id}")
                                                                print("=" * 60)
                                                                print(
                                                                    "\nAll IDs written to .env. Vault is live on Hedera mainnet."
                                                                )
                                                                print(
                                                                    "Run vault_pull.py to verify decryption end-to-end."
                                                                )

                                                                if __name__ == "__main__":
                                                                    main()
