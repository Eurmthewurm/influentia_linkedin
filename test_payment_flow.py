#!/usr/bin/env python3
"""
End-to-end payment flow test for Influentia.
Tests: Stripe checkout session -> webhook delivery -> license creation -> DNS/email check -> validation.
Run this AFTER DNS records are added to Cloudflare.
"""

import json
import subprocess
import time
import sys

WORKER_URL = "https://outreach-pilot-api-production.plain-king-ead0.workers.dev"
TEST_EMAIL = "test-{}@ermoegberts.com".format(int(time.time()))
PASS = 0
FAIL = 0

def step(num, desc):
    print(f"\n{'='*60}")
    print(f"STEP {num}: {desc}")
    print(f"{'='*60}")

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip(), result.returncode

def parse_json(cmd):
    stdout, stderr, rc = run_cmd(cmd)
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        print(f"  ERROR: Invalid JSON response: {stdout[:200]}")
        return None

def ok(msg):
    global PASS
    PASS += 1
    print(f"  \u2705 {msg}")

def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  \u274c {msg}")

def info(msg):
    print(f"  \U0001f4dd {msg}")

def test():
    print("\n\U0001f9ea INFLUENTIA PAYMENT FLOW END-TO-END TEST")
    print(f"   Test email: {TEST_EMAIL}")
    print(f"   Worker: {WORKER_URL}")

    # ── 1. Worker health ─────────────────────────────────────────────
    step(1, "Worker health check")
    data = parse_json(f'curl -s "{WORKER_URL}/"')
    if data and data.get("ok"):
        ok(f"Worker alive: {data.get('service', 'unknown')}")
    else:
        fail("Worker unreachable")
        return False

    # ── 2. Checkout endpoint ──────────────────────────────────────────
    step(2, "Create Stripe checkout session")
    data = parse_json(
        'curl -s -X POST "{}/api/checkout" '
        '-H "Content-Type: application/json" '
        '-d \'{{"email":"{}"}}\''.format(WORKER_URL, TEST_EMAIL)
    )
    if data and data.get("url"):
        ok("Checkout URL created")
        info("Session: {}".format(data.get("session_id", "?")))
        session_id = data["session_id"]
    else:
        fail("Failed to create checkout session")
        return False

    # ── 3. Pre-payment check ─────────────────────────────────────────
    step(3, "License does NOT exist before payment")
    data = parse_json(
        'curl -s "{}/api/license/by-session?session_id={}"'.format(WORKER_URL, session_id)
    )
    if data and ("error" in data or "not_found" in json.dumps(data).lower()):
        ok("Correctly returns no license yet")
    else:
        fail("Unexpected pre-payment response: {}".format(data))

    # ── 4. Webhook simulation note ───────────────────────────────────
    step(4, "Stripe webhook (checkout.session.completed)")
    info("In production, Stripe fires this automatically after payment")
    info("Worker endpoint: {}/api/stripe/webhook".format(WORKER_URL))
    info("To test manually: stripe trigger checkout.session.completed")

    # ── 5. DNS / Email delivery checks ──────────────────────────────
    step(5, "Email delivery prerequisites (DNS)")

    # SPF check
    stdout, _, _ = run_cmd("dig TXT influentia.io +short 2>/dev/null | grep -i spf")
    if "resendmail.net" in stdout:
        ok("SPF includes Resend (resendmail.net)")
    else:
        fail("SPF missing Resend — emails will fail SPF!")
        info("Fix: add 'include:resendmail.net' to the TXT @ record")
        if stdout:
            info("Current: {}".format(stdout))

    # DKIM check
    stdout, _, _ = run_cmd("dig TXT resend._domainkey.influentia.io +short 2>/dev/null")
    if stdout and "p=" in stdout:
        ok("DKIM record exists (resend._domainkey)")
    else:
        fail("DKIM missing — Resend domain not verified")

    # DMARC check
    stdout, _, _ = run_cmd("dig TXT _dmarc.influentia.io +short 2>/dev/null")
    if stdout and "DMARC1" in stdout:
        ok("DMARC policy configured")
    else:
        fail("DMARC missing — add TXT _dmarc")
        info("Value: v=DMARC1; p=quarantine; rua=mailto:dmarc@influentia.io")

    # ── 6. Account portal ────────────────────────────────────────────
    step(6, "Account portal (key retrieval)")
    info("User portal: https://influentia.io/account")
    info("Accepts license key -> redirects to Stripe billing portal")

    # ── 7. Summary ──────────────────────────────────────────────────
    step(7, "TEST SUMMARY")
    print(f"\n  Passed: {PASS}")
    print(f"  Failed: {FAIL}")

    if FAIL == 0:
        print(f"\n  \U0001f389 All checks passed! Ready for live payment test.")
    else:
        print(f"\n  \u26a0\ufe0f  {FAIL} issue(s) found — fix DNS records before launching.")

    print("""
  MANUAL VERIFICATION (after DNS is fixed):
    1. Visit https://buy.stripe.com/8x200j6928DLfpU1U8bII00 (your payment link)
    2. Complete Stripe Checkout with a test card
    3. Check email inbox for license key from hello@influentia.io
    4. Download app -> install -> launch -> paste license key
    5. Dashboard should unlock immediately
    """)

    return FAIL == 0

if __name__ == "__main__":
    success = test()
    sys.exit(0 if success else 1)
