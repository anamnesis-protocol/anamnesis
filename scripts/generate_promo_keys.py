"""
Generate promotional keys for Arty Fitchel's and insert them into Supabase.

Usage:
    python scripts/generate_promo_keys.py --count 10
    python scripts/generate_promo_keys.py --count 5 --note "beta testers"
    python scripts/generate_promo_keys.py --count 3 --dry-run

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_KEY env vars (NOT the anon key).
    pip install requests python-dotenv
"""

import argparse
import json
import os
import secrets
import string
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

SEGMENT_CHARS = string.ascii_uppercase + string.digits
# Remove ambiguous chars: 0/O, 1/I/L
SEGMENT_CHARS = "".join(c for c in SEGMENT_CHARS if c not in "01IOL")
SEGMENT_LENGTH = 4
SEGMENTS = 3  # produces AF-XXXX-XXXX-XXXX


def generate_key() -> str:
    segments = [
        "".join(secrets.choice(SEGMENT_CHARS) for _ in range(SEGMENT_LENGTH))
        for _ in range(SEGMENTS)
    ]
    return "AF-" + "-".join(segments)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Arty Fitchel's promo keys")
    parser.add_argument("--count", type=int, default=1, help="Number of keys to generate")
    parser.add_argument("--note", type=str, default="", help="Optional note stored with the keys")
    parser.add_argument("--vip", action="store_true", help="Mark keys as VIP (no subscription required, permanent access)")
    parser.add_argument("--founding", action="store_true", help="Mark keys as Founding Member (permanent access, founding member badge)")
    parser.add_argument("--dry-run", action="store_true", help="Print keys without inserting")
    args = parser.parse_args()

    if args.vip and args.founding:
        print("ERROR: --vip and --founding are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    keys = [generate_key() for _ in range(args.count)]

    key_type = "founding" if args.founding else "VIP" if args.vip else "promo"

    if args.dry_run:
        print(f"[DRY RUN] Generated {len(keys)} {key_type} key(s):")
        for k in keys:
            print(f"  {k}")
        return

    url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not service_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    endpoint = f"{url.rstrip('/')}/rest/v1/promo_keys"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    rows = [{"key": k, "note": args.note or None, "vip": args.vip, "founding": args.founding} for k in keys]

    res = requests.post(endpoint, headers=headers, data=json.dumps(rows), timeout=10)
    if res.status_code not in (200, 201):
        print(f"ERROR {res.status_code}: {res.text}", file=sys.stderr)
        sys.exit(1)

    print(f"Inserted {len(keys)} {key_type} key(s):")
    for k in keys:
        print(f"  {k}")


if __name__ == "__main__":
    main()
