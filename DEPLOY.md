# Outreach Pilot Production Deployment Guide

Internal operations runbook for deploying the Outreach Pilot commercial layer from code to live production.

## Prerequisites

Before starting, ensure you have:

- **Cloudflare account** with Workers, Pages, R2, and registered domain (`outreachpilot.app`) with DNS managed by Cloudflare
- **Stripe account** in live mode (not sandbox)
- **wrangler CLI** installed: `npm install -g wrangler` and authenticated with `wrangler login`
- **Local copy** of the repository at `/Users/ermoegberts/Desktop/linkedin_outreach/`

---

## Step 1: Stripe Product & Account Setup

### 1.1 Create the Product

1. Go to [Stripe Dashboard](https://dashboard.stripe.com) → **Products**
2. Click **+ Add product**
3. Name: `Outreach Pilot Pro`
4. Description: `Monthly subscription for Outreach Pilot`
5. Pricing model: **Recurring**
   - Standard pricing: `$29.00 USD per month`
6. Billing period: `Monthly`
7. Click **Save product**
8. On the product page, scroll to **Pricing** and copy the `price_...` ID. Save this for Step 2.

### 1.2 Configure Customer Portal

1. Go to **Settings** → **Billing portal**
2. Click **Activate portal** (if not already active)
3. Customize:
   - **Return URL**: `https://outreachpilot.app/account`
   - **Customer features**: Check `Allow customers to update their payment method` and `Allow customers to cancel subscriptions`
4. Save changes

### 1.3 Get Live API Keys

1. Go to **Developers** → **API keys**
2. Ensure you're in **Live** mode (toggle at top right)
3. Copy the **Secret key** (starts with `sk_live_`). Save for Step 2.
4. Do NOT share this key publicly. It will be stored as a secret in Cloudflare.

---

## Step 2: Deploy the Cloudflare Worker

The worker is the billing & license backend at `api.outreachpilot.app`. It handles Stripe webhooks, license issuance, and validation.

### 2.1 Create the D1 Database

```bash
cd /Users/ermoegberts/Desktop/linkedin_outreach/worker

# Create the database
wrangler d1 create outreach-pilot-db

# Output will show:
# ✅ Successfully created DB 'outreach-pilot-db' in account ...
# 📝 Add this to your wrangler.toml:
# [[d1_databases]]
# binding = "DB"
# database_name = "outreach-pilot"
# database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

Copy the `database_id` and update `/Users/ermoegberts/Desktop/linkedin_outreach/worker/wrangler.toml`:

```toml
[[d1_databases]]
binding = "DB"
database_name = "outreach-pilot"
database_id = "YOUR_DATABASE_ID_HERE"  # <- Paste here
```

### 2.2 Initialize the Database Schema

```bash
wrangler d1 execute outreach-pilot-db --remote --file=./migrations/0001_init.sql
```

Verify the table was created:

```bash
wrangler d1 execute outreach-pilot-db --remote --command="SELECT name FROM sqlite_master WHERE type='table';"
```

You should see `licenses` in the results.

### 2.3 Set Environment Variables

Update `/Users/ermoegberts/Desktop/linkedin_outreach/worker/wrangler.toml` with the Stripe price ID from Step 1:

```toml
[env.production]
vars = { LANDING_URL = "https://outreachpilot.app", STRIPE_PRICE_ID = "price_1234567890ABCDEF" }
```

(Replace `price_1234567890ABCDEF` with your actual price ID from Step 1.8.)

### 2.4 Add Stripe Secrets

```bash
# Stripe Secret Key (from Step 1.3)
wrangler secret put STRIPE_SECRET_KEY --env production
# Paste: sk_live_...

# Webhook secret (placeholder for now, will update in Step 3)
wrangler secret put STRIPE_WEBHOOK_SECRET --env production
# Paste: whsec_placeholder
```

### 2.5 Deploy the Worker

```bash
wrangler deploy --env production

# Output will show:
# ✅ Deployed to api.outreachpilot.workers.dev
```

Note the deployed URL (e.g., `outreach-pilot-api.YOUR_ACCOUNT.workers.dev`).

### 2.6 Bind Custom Domain

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → **Workers** → **Routes**
2. Click **Add route**
3. Route: `api.outreachpilot.app/*`
4. Service: `outreach-pilot-api`
5. Environment: `production`
6. Click **Add route**

Alternatively, add to `wrangler.toml`:

```toml
routes = [
  { pattern = "api.outreachpilot.app/*", zone_name = "outreachpilot.app" }
]
```

### 2.7 Smoke Test

```bash
curl https://api.outreachpilot.app/

# Expected response:
# {"service":"outreach-pilot-api","ok":true}
```

---

## Step 3: Wire Stripe Webhook

The worker needs to receive events from Stripe when customers complete checkout or update their subscriptions.

### 3.1 Create Webhook Endpoint

1. Go to [Stripe Dashboard](https://dashboard.stripe.com) → **Developers** → **Webhooks**
2. Click **Add endpoint**
3. Endpoint URL: `https://api.outreachpilot.app/api/stripe/webhook`
4. Select events:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Click **Add endpoint**

### 3.2 Get Webhook Secret

1. On the webhook endpoint page, scroll to **Signing secret**
2. Click **Reveal**
3. Copy the secret (starts with `whsec_`)

### 3.3 Update Worker Secret

```bash
cd /Users/ermoegberts/Desktop/linkedin_outreach/worker

wrangler secret put STRIPE_WEBHOOK_SECRET --env production
# Paste: whsec_...

# Redeploy to pick up the new secret
wrangler deploy --env production
```

### 3.4 Test Webhook Delivery

1. In Stripe Webhooks page, click on your endpoint
2. Scroll to **Recent events** and click **Send test event**
3. Select `checkout.session.completed`
4. A test event will fire
5. You should see response code **200** and the worker will log it (visible in `wrangler tail`)

---

## Step 4: Deploy the Landing Page

The landing page is a static site at `outreachpilot.app` with checkout, success, and account pages.

### 4.1 Deploy to Cloudflare Pages

Option A: **Git Integration** (recommended)

1. Push `/Users/ermoegberts/Desktop/linkedin_outreach/landing/` to a GitHub repo
2. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → **Pages** → **Create a project**
3. Select the GitHub repo
4. Build settings:
   - Framework: `None`
   - Build command: (leave empty)
   - Build output directory: `.` (current directory)
5. Click **Save and Deploy**

Option B: **Direct Upload**

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → **Pages** → **Create a project** → **Direct Upload**
2. Drag and drop the contents of `/Users/ermoegberts/Desktop/linkedin_outreach/landing/`
3. Click **Deploy**

### 4.2 Set Custom Domain

1. In the Pages deployment, go to **Settings** → **Custom domain**
2. Add `outreachpilot.app`
3. Add `www.outreachpilot.app` (Cloudflare will set up the redirects automatically)
4. Verify DNS records are pointing to Cloudflare

### 4.3 Verify Deployment

Visit `https://outreachpilot.app` in your browser. You should see the landing page with a "Start free trial" button.

---

## Step 5: Host the Tester Zip

The tester application is distributed via R2 bucket at `downloads.outreachpilot.app`.

### 5.1 Create R2 Bucket

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → **R2** → **Create bucket**
2. Bucket name: `outreach-pilot-downloads`
3. Region: Auto
4. Click **Create bucket**

### 5.2 Upload the Zip File

1. In the bucket, click **Upload**
2. Select `outreach-pilot.zip` from your local machine
3. Rename to `outreach-pilot-latest.zip` (if not already)
4. Click **Upload**

### 5.3 Enable Public Access & Custom Domain

Option A: **Custom Domain** (recommended)

1. In the bucket, go to **Settings** → **Domain**
2. Add custom domain: `downloads.outreachpilot.app`
3. Save

Option B: **Public Bucket** (if not using custom domain)

1. In the bucket, go to **Settings**
2. Check **Allow public access**
3. Note the public URL (e.g., `https://pub-xxxxxxx.r2.dev/outreach-pilot-latest.zip`)

### 5.4 Verify Download

```bash
# Should return a 200 and stream the zip file
curl -I https://downloads.outreachpilot.app/outreach-pilot-latest.zip

# Expected headers:
# HTTP/1.1 200 OK
# Content-Type: application/zip
# Content-Length: XXXXXX
```

---

## Step 6: End-to-End Smoke Test

### 6.1 Test Checkout Flow

1. Open `https://outreachpilot.app` in an **incognito/private window**
2. Click **Start free trial** (or similar CTA)
3. Enter a test email (e.g., `test@example.com`)
4. You should be redirected to Stripe Checkout
5. **Option A (Test Mode):**
   - Use test card `4242 4242 4242 4242`
   - Any future expiry (e.g., `12/26`)
   - Any CVC (e.g., `123`)
   - This requires temporarily swapping your Stripe keys to test mode; not recommended for live test.
6. **Option B (Live Test with Real Card):**
   - Use a real credit card you own
   - This will charge $29 to your card (you can refund via Stripe dashboard later)
   - Complete the checkout

### 6.2 Verify License Issuance

After successful checkout, you should be redirected to `https://outreachpilot.app/success.html?session_id=cs_...`

1. The success page should display a license key (e.g., `AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GG`)
2. Verify the webhook fired in Stripe:
   - Go to [Stripe Dashboard](https://dashboard.stripe.com) → **Developers** → **Webhooks** → Your endpoint
   - Click on the webhook
   - You should see **Response status: 200**
3. Verify the license was written to the database:

```bash
cd /Users/ermoegberts/Desktop/linkedin_outreach/worker

wrangler d1 execute outreach-pilot-db --remote \
  --command="SELECT key, email, tier, subscription_status FROM licenses ORDER BY id DESC LIMIT 1"

# Expected output:
# ┌─────────────────────────────────────────────┬─────────────────────┬───────┬─────────────────────┐
# │ key                                         │ email               │ tier  │ subscription_status │
# ├─────────────────────────────────────────────┼─────────────────────┼───────┼─────────────────────┤
# │ AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GG            │ test@example.com    │ trial │ trialing            │
# └─────────────────────────────────────────────┴─────────────────────┴───────┴─────────────────────┘
```

### 6.3 Test License Validation

```bash
# Validate the license key from Step 6.2
curl -X POST https://api.outreachpilot.app/api/license/validate \
  -H "Content-Type: application/json" \
  -d '{"key":"AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GG"}'

# Expected response:
# {
#   "valid": true,
#   "email": "test@example.com",
#   "tier": "trial",
#   "trial_ends_at": XXXXXXXXXX,
#   "subscription_status": "trialing",
#   "days_remaining_in_trial": 7
# }
```

### 6.4 Test Customer Portal

1. Extract the license key from Step 6.2 (e.g., `AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GG`)
2. Open `https://outreachpilot.app/account?license=AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GG` (or visit the account page and enter the key)
3. You should be redirected to Stripe's customer portal
4. You can view the subscription, update payment method, and cancel the subscription

### 6.5 Test Subscription Cancellation

1. In the Stripe customer portal, click **Cancel subscription**
2. Confirm the cancellation
3. Wait 1-2 minutes for the webhook to fire
4. Validate the license again:

```bash
curl -X POST https://api.outreachpilot.app/api/license/validate \
  -H "Content-Type: application/json" \
  -d '{"key":"AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GG"}'

# Expected response (after webhook):
# {
#   "valid": false,
#   "reason": "revoked"
# }
```

### 6.6 Test Download Link

```bash
# Download the zip file
curl -O https://downloads.outreachpilot.app/outreach-pilot-latest.zip

# Verify it's a valid zip
unzip -t outreach-pilot-latest.zip

# Expected output:
# Archive:  outreach-pilot-latest.zip
# ...
# No errors detected in compressed data of outreach-pilot-latest.zip.
```

---

## Step 7: Transition from Test to Live (If You Used Test Mode)

If you tested with Stripe's test mode cards in Step 6, transition to live mode now.

### 7.1 Swap to Live Secrets

```bash
cd /Users/ermoegberts/Desktop/linkedin_outreach/worker

# Stripe Secret Key (live mode, from Step 1.3)
wrangler secret put STRIPE_SECRET_KEY --env production
# Paste: sk_live_...

# Stripe Webhook Secret (live mode, from Step 3.2)
wrangler secret put STRIPE_WEBHOOK_SECRET --env production
# Paste: whsec_...
```

### 7.2 Verify Stripe Price ID is Live

Confirm that `STRIPE_PRICE_ID` in `wrangler.toml` (from Step 2.3) is the live price ID (starts with `price_`, created in live mode). If you used a test price, update it now.

### 7.3 Redeploy Worker

```bash
wrangler deploy --env production
```

### 7.4 Verify Webhook is Wired to Live Mode

Go to [Stripe Dashboard](https://dashboard.stripe.com) → **Developers** → **Webhooks**. Ensure the webhook endpoint is the same as in Step 3.1 and is receiving events in live mode (check the **Recent events** section).

---

## Operations & Maintenance

### Monitor Customer Licenses

```bash
cd /Users/ermoegberts/Desktop/linkedin_outreach/worker

# List all active licenses
wrangler d1 execute outreach-pilot-db --remote \
  --command="SELECT key, email, tier, subscription_status, created_at FROM licenses WHERE tier IN ('trial', 'active') ORDER BY created_at DESC"

# Check a specific customer's license
wrangler d1 execute outreach-pilot-db --remote \
  --command="SELECT key, email, tier, subscription_status, trial_ends_at, current_period_end FROM licenses WHERE email='user@example.com'"
```

### Manually Revoke a License

If you need to disable a customer's license (e.g., for abuse), update the database:

```bash
wrangler d1 execute outreach-pilot-db --remote \
  --command="UPDATE licenses SET tier='revoked' WHERE key='AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GG'"
```

Alternatively, cancel the subscription in Stripe (the webhook will automatically set tier to 'cancelled').

### Refund a Customer

1. Go to [Stripe Dashboard](https://dashboard.stripe.com) → **Payments**
2. Find the charge
3. Click **Refund** to issue a full or partial refund
4. The customer's subscription is NOT affected; cancellation is a separate action

### Monitor Errors

View real-time logs from the worker:

```bash
cd /Users/ermoegberts/Desktop/linkedin_outreach/worker
wrangler tail --env production
```

View Stripe webhook events:
- [Stripe Dashboard](https://dashboard.stripe.com) → **Developers** → **Webhooks** → Your endpoint → **Recent events**

View Cloudflare Pages deployment:
- [Cloudflare Dashboard](https://dash.cloudflare.com) → **Pages** → Deployment → **Logs**

### Update the Tester Zip

When you have a new version of `outreach-pilot.zip`:

1. Upload to R2: Cloudflare → **R2** → `outreach-pilot-downloads` → **Upload** → Select new zip → Rename to `outreach-pilot-latest.zip`
2. Users will download the latest version automatically (no code deployment needed)

---

## Cost Estimate

| Component | Cost | Notes |
|-----------|------|-------|
| Cloudflare Workers | Free | 100k requests/day free tier likely sufficient |
| Cloudflare D1 | Free | 5M reads/day free tier likely sufficient |
| Cloudflare Pages | Free | Unlimited static sites |
| Cloudflare R2 | ~$0.015/GB-month | Storage only; egress to Cloudflare is free (downloads are free) |
| Domain | ~$10/year | Assuming registration with Cloudflare |
| Stripe | 2.9% + $0.30 | Per successful charge (revenue split) |
| **Total Infra** | **~$1/month** | Low-volume estimate; scales linearly with storage |

---

## Troubleshooting

### Issue: Webhook not firing

**Symptoms:** License not created after checkout, Stripe webhook shows failed delivery.

**Solution:**
1. Check the webhook endpoint URL is exactly `https://api.outreachpilot.app/api/stripe/webhook`
2. Verify the webhook secret is correct: `wrangler secret put STRIPE_WEBHOOK_SECRET --env production`
3. Check worker logs: `wrangler tail --env production`
4. Re-test the webhook from Stripe Dashboard → **Developers** → **Webhooks** → Your endpoint → **Send test event**

### Issue: License key not appearing on success page

**Symptoms:** Checkout succeeds, redirects to `/success.html?session_id=...`, but no license key is shown.

**Solution:**
1. Check the D1 database for the session:
   ```bash
   wrangler d1 execute outreach-pilot-db --remote \
     --command="SELECT key, email FROM licenses WHERE stripe_checkout_session_id='cs_...'"
   ```
2. If the license is in the database, the issue is in the frontend. Check `landing/success.html` to ensure it's calling `/api/license/by-session`.
3. If the license is NOT in the database, the webhook did not fire. See "Webhook not firing" above.
4. Check CORS: Open browser DevTools → **Network** → Look for failed requests to `/api/license/by-session`. If they're blocked, verify CORS in `worker/src/index.ts` allows `https://outreachpilot.app`.

### Issue: CORS errors on checkout or license validation

**Symptoms:** Browser console shows "CORS policy" error when calling API from landing page.

**Solution:**
1. Verify the origin is allowed in `worker/src/index.ts`. The landing page should be served from `https://outreachpilot.app`, which is already whitelisted.
2. If testing locally, ensure `http://localhost:3000` or `http://localhost:5173` is in the allowed origins.
3. Redeploy the worker: `wrangler deploy --env production`

### Issue: D1 database is slow or unresponsive

**Symptoms:** API requests to `/api/license/validate` or `/api/checkout` are timing out.

**Solution:**
1. Check if you're exceeding D1 free tier limits (5M reads/day). View usage in Cloudflare → **Analytics** → **D1**.
2. Optimize queries: The current schema has indexes on `stripe_subscription_id`, `email`, `stripe_checkout_session_id`, and `key`. All queries are indexed.
3. If limits are exceeded, upgrade D1 to paid tier: Cloudflare → **D1** → Database → **Settings** → **Plan**.

### Issue: Customer can use license after cancelling

**Symptoms:** After cancelling subscription in Stripe, the customer can still use the app (license validates as true).

**Solution:**
1. Check that the webhook event `customer.subscription.deleted` or `customer.subscription.updated` fired. View in Stripe → **Developers** → **Webhooks** → Endpoint → **Recent events**.
2. Check the worker logs for errors: `wrangler tail --env production`
3. Manually update the license in D1:
   ```bash
   wrangler d1 execute outreach-pilot-db --remote \
     --command="UPDATE licenses SET tier='cancelled', subscription_status='canceled' WHERE stripe_subscription_id='sub_...'"
   ```
4. The customer's license key will now fail validation: `{"valid":false,"reason":"revoked"}`

### Issue: Can't find the database ID

**Symptoms:** Deployment fails with "database_id not found in wrangler.toml".

**Solution:**
1. Ensure you ran `wrangler d1 create outreach-pilot-db` in Step 2.1 and copied the ID.
2. Check `wrangler.toml` for the database binding:
   ```toml
   [[d1_databases]]
   binding = "DB"
   database_name = "outreach-pilot"
   database_id = "YOUR_DATABASE_ID_HERE"
   ```
3. If the database was already created, list existing databases: `wrangler d1 list` and copy the ID.

---

## Rollback Plan

If a deployment breaks production, follow this order:

1. **Revert the landing page**: Cloudflare → **Pages** → Select deployment → **Rollback** (one-click)
2. **Revert the worker**: Re-run the last known-good commit: `git checkout <commit-hash> worker/` then `wrangler deploy --env production`
3. **Check Stripe webhooks**: Temporarily disable the endpoint (Cloudflare → **Developers** → **Webhooks** → Disable) to prevent corrupted data from webhooks. Re-enable once fixed.
4. **Notify customers**: If the outage is > 1 hour, send a brief status update to customers via email.

---

## Post-Launch Checklist

- [ ] Stripe webhook is firing successfully (check **Recent events** in Stripe)
- [ ] Test checkout flow end-to-end (incognito window, real or test card)
- [ ] License is created in D1 after checkout
- [ ] License validates correctly
- [ ] Customer portal works (can view subscription, update payment, cancel)
- [ ] Zip file downloads from R2 without errors
- [ ] Worker logs show no errors (`wrangler tail`)
- [ ] Cloudflare Pages deployment is live (custom domain resolves)
- [ ] DNS is pointing to Cloudflare for all subdomains
- [ ] SSL/TLS certificates are valid (check lock icon in browser)
- [ ] Smoke test from incognito window (no cached state)
- [ ] Backup: Save Stripe price ID, webhook endpoint URL, and database ID to a secure location

---

## Support Contacts

- **Cloudflare Support**: https://dash.cloudflare.com → **Support** → **Open a ticket**
- **Stripe Support**: https://dashboard.stripe.com → **Help** → **Support**
- **Wrangler Docs**: https://developers.cloudflare.com/workers/
- **D1 Docs**: https://developers.cloudflare.com/d1/

---

*Last updated: April 2026*
