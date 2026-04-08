"""
Award a badge to an Arty Fitchel's user by email address.

Usage:
    python scripts/award_badge.py --email user@example.com --label "Early Adopter"
    python scripts/award_badge.py --email user@example.com --label "Founding Member" --color amber
    python scripts/award_badge.py --email user@example.com --label "Beta Tester" --color cyan --dry-run

Colors: violet (default), amber, cyan, emerald, rose, slate

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_KEY env vars (NOT the anon key).
    pip install requests python-dotenv
"""

import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

VALID_COLORS = {"violet", "amber", "cyan", "emerald", "rose", "slate"}


def get_user_id_by_email(url: str, service_key: str, email: str) -> str | None:
    """Look up a user's UUID by email using the Supabase admin API."""
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    res = requests.get(
        f"{url.rstrip('/')}/auth/v1/admin/users",
        headers=headers,
        params={"page": 1, "per_page": 1000},
        timeout=10,
    )
    if res.status_code != 200:
        print(f"ERROR fetching users {res.status_code}: {res.text}", file=sys.stderr)
        return None
    users = res.json().get("users", [])
    for u in users:
        if u.get("email", "").lower() == email.lower():
            return u["id"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Award a badge to an Arty Fitchel's user")
    parser.add_argument("--email", required=True, help="User's email address")
    parser.add_argument("--label", required=True, help="Badge label text (e.g. 'Early Adopter')")
    parser.add_argument("--color", default="violet", choices=sorted(VALID_COLORS), help="Badge color (default: violet)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without inserting")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not service_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    print(f"Looking up user: {args.email}")
    user_id = get_user_id_by_email(url, service_key, args.email)
    if not user_id:
        print(f"ERROR: No user found with email '{args.email}'", file=sys.stderr)
        sys.exit(1)

    print(f"Found user: {user_id}")

    if args.dry_run:
        print(f"[DRY RUN] Would award badge '{args.label}' ({args.color}) to {args.email} ({user_id})")
        return

    endpoint = f"{url.rstrip('/')}/rest/v1/user_badges"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    row = {"user_id": user_id, "label": args.label, "color": args.color}

    res = requests.post(endpoint, headers=headers, data=json.dumps(row), timeout=10)
    if res.status_code not in (200, 201):
        print(f"ERROR {res.status_code}: {res.text}", file=sys.stderr)
        sys.exit(1)

    result = res.json()
    badge_id = result[0]["id"] if result else "?"
    print(f"Awarded badge '{args.label}' ({args.color}) to {args.email}")
    print(f"  Badge ID: {badge_id}")


if __name__ == "__main__":
    main()
