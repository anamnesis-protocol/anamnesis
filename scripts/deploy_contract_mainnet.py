"""
One-shot script: deploy a fresh ContextValidator contract from the current operator account.
Run via: railway run python scripts/deploy_contract_mainnet.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.contract import deploy_contract

contract_id = deploy_contract()
print(f"\nSET THIS IN RAILWAY: VALIDATOR_CONTRACT_ID={contract_id}")
