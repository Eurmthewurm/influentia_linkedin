#!/usr/bin/env python3
"""
Beta license generator for r/SaaS outreach.
Generates limited-use license keys for beta testers.
"""

import secrets
import string
import sys

def generate_beta_key():
    """Generate a license key in the format XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX"""
    chars = string.ascii_uppercase + string.digits
    parts = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(6)]
    tail = ''.join(secrets.choice(chars) for _ in range(2))
    return '-'.join(parts) + '-' + tail

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"Generating {count} beta license keys:\n")
    for i in range(count):
        key = generate_beta_key()
        print(f"  {i+1}. {key}")
    print(f"\nThese need to be inserted into the D1 database with:")
    print(f"  tier='beta', trial_ends_at=now+7days, subscription_status='trialing'")
    print(f"  token_day_limit=50000, token_month_limit=150000")
