import { Hono } from 'hono';
import { cors } from 'hono/cors';
import Stripe from 'stripe';

type Env = {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_PRICE_ID: string;
  LANDING_URL: string;
  ANTHROPIC_API_KEY: string;
  BRAVE_API_KEY: string;
  RESEND_API_KEY: string;
};

const app = new Hono<{ Bindings: Env }>();

// CORS for frontend calls
const ALLOWED_ORIGINS = [
  'https://influentia.io',
  'https://www.influentia.io',
  'https://influentia-79b.pages.dev',
  'https://outreach-pilot.pages.dev',
  'http://localhost:3000',
  'http://localhost:5173',
  'http://localhost:5555',
];

const strictCors = cors({
  origin: (origin) => {
    if (!origin) return ALLOWED_ORIGINS[0];
    if (ALLOWED_ORIGINS.includes(origin)) return origin;
    // Allow any Cloudflare Pages preview URL for either project
    if (origin.endsWith('.outreach-pilot.pages.dev')) return origin;
    if (origin.endsWith('.influentia-79b.pages.dev')) return origin;
    return ALLOWED_ORIGINS[0];
  },
});

app.use('/api/checkout', strictCors);
app.use('/api/portal', strictCors);
app.use('/api/license/*', cors({ origin: '*' }));

// License key generation: 32 chars, base32-ish (no 0/O/1/I/l), formatted as XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XX
const CHARSET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

function generateLicenseKey(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  const chars = Array.from(bytes).map((b) => CHARSET[b % CHARSET.length]);
  const key = chars.join('');
  return [
    key.slice(0, 4),
    key.slice(4, 8),
    key.slice(8, 12),
    key.slice(12, 16),
    key.slice(16, 20),
    key.slice(20, 24),
    key.slice(24, 32),
  ].join('-');
}

interface License {
  key: string;
  email: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  stripe_checkout_session_id: string | null;
  tier: 'trial' | 'active' | 'expired' | 'cancelled';
  trial_ends_at: number | null;
  current_period_end: number | null;
  subscription_status: string | null;
  created_at: number;
  last_seen_at: number | null;
}

// Health check
app.get('/', (c) => {
  return c.json({ service: 'outreach-pilot-api', ok: true });
});

// POST /api/checkout - Create Stripe Checkout session
app.post('/api/checkout', async (c) => {
  try {
    const { email } = await c.req.json<{ email?: string }>();
    const stripe = new Stripe(c.env.STRIPE_SECRET_KEY, {
      apiVersion: '2023-08-16',
      httpClient: Stripe.createFetchHttpClient(),
    });

    // 14-day money-back model: card is charged immediately. Refunds are
    // handled in /api/stripe/webhook on charge.refunded → license.tier = 'cancelled'.
    // Don't add trial_period_days here — that creates a free trial, which is
    // a different commercial structure that conflicts with our refund promise.
    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      line_items: [
        {
          price: c.env.STRIPE_PRICE_ID,
          quantity: 1,
        },
      ],
      success_url: `${c.env.LANDING_URL}/success.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${c.env.LANDING_URL}/`,
      customer_email: email || undefined,
    });

    return c.json({ url: session.url, session_id: session.id });
  } catch (error) {
    console.error('Checkout error:', error);
    return c.json({ error: 'Failed to create checkout session' }, 500);
  }
});

// POST /api/stripe/webhook - Handle Stripe webhooks
app.post('/api/stripe/webhook', async (c) => {
  try {
    const signature = c.req.header('stripe-signature');
    if (!signature) {
      return c.json({ error: 'Missing signature' }, 400);
    }

    const body = await c.req.text();
    const stripe = new Stripe(c.env.STRIPE_SECRET_KEY, {
      apiVersion: '2023-08-16',
      httpClient: Stripe.createFetchHttpClient(),
    });

    let event: Stripe.Event;
    try {
      event = await stripe.webhooks.constructEventAsync(
        body,
        signature,
        c.env.STRIPE_WEBHOOK_SECRET
      );
    } catch (err) {
      console.error('Webhook signature verification failed:', err);
      return c.json({ error: 'Signature verification failed' }, 400);
    }

    const now = Math.floor(Date.now() / 1000);

    // Handle checkout.session.completed
    if (event.type === 'checkout.session.completed') {
      const session = event.data.object as Stripe.Checkout.Session;
      const email = session.customer_details?.email;
      if (!email) {
        console.warn('No email in checkout session', session.id);
        return c.json({ received: true });
      }

      // Idempotency check
      const existing = await c.env.DB.prepare(
        'SELECT id FROM licenses WHERE stripe_checkout_session_id = ?'
      ).bind(session.id).first<{ id: number }>();

      if (!existing) {
        const key = generateLicenseKey();
        await c.env.DB.prepare(
          `INSERT INTO licenses (key, email, stripe_customer_id, stripe_subscription_id, stripe_checkout_session_id, tier, trial_ends_at, subscription_status, created_at)
           VALUES (?, ?, ?, ?, ?, 'trial', ?, 'trialing', ?)`)
          .bind(
            key,
            email,
            session.customer || null,
            session.subscription || null,
            session.id,
            now + 14 * 86400,
            now
          )
          .run();
        console.log('License created:', { key, email, session_id: session.id });
        await sendLicenseEmail(c.env.RESEND_API_KEY, c.env.LANDING_URL, email, key);
      }
    }

    // Handle customer.subscription.updated
    if (event.type === 'customer.subscription.updated') {
      const sub = event.data.object as Stripe.Subscription;
      const newStatus = sub.status;
      const periodEnd = sub.current_period_end;

      const license = await c.env.DB.prepare(
        'SELECT tier FROM licenses WHERE stripe_subscription_id = ?'
      )
        .bind(sub.id)
        .first<License>();

      if (license) {
        let newTier = license.tier;
        if (newStatus === 'active') {
          // Transition TO active from trial, expired, or even cancelled (re-subscribe)
          newTier = 'active';
        } else if (newStatus === 'trialing' || newStatus === 'past_due') {
          // Keep existing tier if trialing/past_due — status will be checked separately
          // Don't downgrade an active user on past_due — allow_runs blocks it
        } else if (newStatus === 'canceled' || newStatus === 'unpaid' || newStatus === 'incomplete_expired') {
          newTier = 'cancelled';
        }

        await c.env.DB.prepare(
          'UPDATE licenses SET subscription_status = ?, current_period_end = ?, tier = ? WHERE stripe_subscription_id = ?'
        )
          .bind(newStatus, periodEnd, newTier, sub.id)
          .run();
        console.log('License updated:', { subscription_id: sub.id, tier: newTier });
      }
    }

    // Handle customer.subscription.deleted
    if (event.type === 'customer.subscription.deleted') {
      const sub = event.data.object as Stripe.Subscription;
      await c.env.DB.prepare(
        'UPDATE licenses SET tier = ?, subscription_status = ? WHERE stripe_subscription_id = ?'
      )
        .bind('cancelled', 'canceled', sub.id)
        .run();
      console.log('License cancelled:', { subscription_id: sub.id });
    }

    // Unknown events: log but return 200
    if (
      ![
        'checkout.session.completed',
        'customer.subscription.updated',
        'customer.subscription.deleted',
      ].includes(event.type)
    ) {
      console.log('Unhandled event type:', event.type);
    }

    return c.json({ received: true });
  } catch (error) {
    console.error('Webhook handler error:', error);
    return c.json({ error: 'Internal error' }, 500);
  }
});

// GET /api/license/by-session?session_id=cs_...
app.get('/api/license/by-session', async (c) => {
  try {
    const sessionId = c.req.query('session_id');
    if (!sessionId) {
      return c.json({ error: 'Missing session_id' }, 400);
    }

    const license = await c.env.DB.prepare(
      'SELECT key, email, tier, trial_ends_at FROM licenses WHERE stripe_checkout_session_id = ?'
    )
      .bind(sessionId)
      .first<License>();

    if (!license) {
      return c.json({ error: 'License not found' }, 404);
    }

    return c.json({
      key: license.key,
      email: license.email,
      tier: license.tier,
      trial_ends_at: license.trial_ends_at,
    });
  } catch (error) {
    console.error('by-session error:', error);
    return c.json({ error: 'Failed to fetch license' }, 500);
  }
});

// POST /api/license/validate - Validate a license key
app.post('/api/license/validate', async (c) => {
  try {
    const body = await c.req.json<{
      key: string;
      device_id?: string;
      device_name?: string;
    }>();
    const { key, device_id, device_name } = body;
    if (!key) {
      return c.json({ valid: false, reason: 'not_found' }, 400);
    }

    const now = Math.floor(Date.now() / 1000);
    const license = await c.env.DB.prepare(
      'SELECT * FROM licenses WHERE key = ?'
    )
      .bind(key)
      .first<License>();

    if (!license) {
      return c.json({ valid: false, reason: 'not_found' });
    }

    // Update last_seen_at
    await c.env.DB.prepare(
      'UPDATE licenses SET last_seen_at = ? WHERE key = ?'
    )
      .bind(now, key)
      .run();

    // Check if trial expired
    let tier = license.tier;
    if (tier === 'trial' && license.trial_ends_at && license.trial_ends_at < now) {
      tier = 'expired';
      await c.env.DB.prepare(
        'UPDATE licenses SET tier = ? WHERE key = ?'
      )
        .bind('expired', key)
        .run();
    }

    if (tier === 'cancelled' || tier === 'expired') {
      return c.json({
        valid: false,
        reason: 'revoked',
      });
    }

    // Device cap — register or reject. Older clients that don't send
    // device_id pass through unchanged.
    const dev = await enforceDeviceCap(key, device_id, device_name, c.env.DB);
    if (!dev.allowed) {
      return c.json({
        valid: false,
        reason: 'device_limit',
        message: 'This license is already active on the maximum number of machines (3). Sign out of one to use it on a new computer, or contact support@influentia.io.',
        device_count: dev.device_count,
      });
    }

    const daysRemaining =
      tier === 'trial' && license.trial_ends_at
        ? Math.max(0, Math.ceil((license.trial_ends_at - now) / 86400))
        : null;

    return c.json({
      valid: true,
      email: license.email,
      tier,
      trial_ends_at: license.trial_ends_at,
      current_period_end: license.current_period_end,
      subscription_status: license.subscription_status,
      days_remaining_in_trial: daysRemaining,
      device_count: dev.device_count,
    });
  } catch (error) {
    console.error('Validate error:', error);
    return c.json({ error: 'Failed to validate license' }, 500);
  }
});

// GET /api/admin/licenses - List all licenses (for morning briefing)
app.get('/api/admin/licenses', async (c) => {
  try {
    const { results } = await c.env.DB.prepare(
      `SELECT key, email, tier, trial_ends_at, subscription_status,
              current_period_end, created_at, last_seen_at
       FROM licenses ORDER BY created_at DESC LIMIT 100`
    ).all();

    const now = Math.floor(Date.now() / 1000);
    const two_days_ago = now - 2 * 86400;

    return c.json({
      total: results.length,
      licenses: (results as any[]).map((l: any) => {
        const trialEnded = l.tier === 'trial' && l.trial_ends_at && l.trial_ends_at < now;
        const tier = trialEnded ? 'expired' : l.tier;
        const daysAgo = Math.floor((now - l.created_at) / 86400);
        const lastSeenHoursAgo = l.last_seen_at
          ? Math.floor((now - l.last_seen_at) / 3600)
          : null;
        const hasNoActivity = !l.last_seen_at || lastSeenHoursAgo! > 48;

        return {
          key_masked: '••••-' + (l.key || '').slice(-4),
          email: l.email,
          tier,
          days_since_signup: daysAgo,
          last_seen_hours_ago: lastSeenHoursAgo,
          inactive: hasNoActivity && daysAgo >= 2,
          trial_ends_soon: l.tier === 'trial' && l.trial_ends_at && (l.trial_ends_at - now) < 3 * 86400,
        };
      }),
    });
  } catch (error) {
    console.error('Admin licenses error:', error);
    return c.json({ error: 'Failed to fetch licenses' }, 500);
  }
});

// POST /api/portal - Create Stripe customer portal session
app.post('/api/portal', async (c) => {
  try {
    const { key } = await c.req.json<{ key: string }>();
    if (!key) {
      return c.json({ error: 'Missing key' }, 400);
    }

    const license = await c.env.DB.prepare(
      'SELECT stripe_customer_id FROM licenses WHERE key = ?'
    )
      .bind(key)
      .first<License>();

    if (!license || !license.stripe_customer_id) {
      return c.json({ error: 'License not found' }, 404);
    }

    const stripe = new Stripe(c.env.STRIPE_SECRET_KEY, {
      apiVersion: '2023-08-16',
      httpClient: Stripe.createFetchHttpClient(),
    });

    const session = await stripe.billingPortal.sessions.create({
      customer: license.stripe_customer_id,
      return_url: `${c.env.LANDING_URL}/account`,
    });

    return c.json({ url: session.url });
  } catch (error) {
    console.error('Portal error:', error);
    return c.json({ error: 'Failed to create portal session' }, 500);
  }
});

// ── License key email via Resend ──────────────────────────────────────────
async function sendLicenseEmail(
  resendApiKey: string,
  landingUrl: string,
  email: string,
  licenseKey: string
): Promise<void> {
  if (!resendApiKey) return; // gracefully skip if secret not set yet

  const html = `<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0c0c0e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0c0c0e;padding:40px 20px">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#141417;border-radius:16px;border:1px solid rgba(255,255,255,0.08);overflow:hidden;max-width:560px;width:100%">
        <!-- Header -->
        <tr><td style="background:linear-gradient(135deg,#7c6aff,#a78bfa);padding:32px;text-align:center">
          <div style="font-size:28px;margin-bottom:8px">🎉</div>
          <div style="font-size:22px;font-weight:800;color:#fff;letter-spacing:-0.5px">You're in, ${email.split('@')[0]}.</div>
          <div style="font-size:14px;color:rgba(255,255,255,0.8);margin-top:6px">Your 14-day money-back guarantee has started.</div>
        </td></tr>
        <!-- Key -->
        <tr><td style="padding:32px">
          <div style="font-size:12px;color:#8b8a9e;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;text-align:center">Your License Key</div>
          <div style="background:#0c0c0e;border:1px solid rgba(124,106,255,0.4);border-radius:12px;padding:20px;text-align:center;box-shadow:0 0 20px rgba(124,106,255,0.1)">
            <span style="font-family:'SF Mono','Fira Code','Courier New',monospace;font-size:15px;color:#a78bfa;letter-spacing:1px;word-break:break-all">${licenseKey}</span>
          </div>
          <div style="font-size:12px;color:#8b8a9e;text-align:center;margin-top:10px">Keep this safe. You'll enter it once when installing the app.</div>
        </td></tr>
        <!-- Steps -->
        <tr><td style="padding:0 32px 32px">
          <div style="font-size:14px;font-weight:700;color:#f1f0ff;margin-bottom:16px">Get started in 3 steps:</div>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06)">
              <span style="color:#7c6aff;font-weight:700;margin-right:10px">1</span>
              <span style="color:#f1f0ff;font-size:14px">Copy your license key above</span>
            </td></tr>
            <tr><td style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06)">
              <span style="color:#7c6aff;font-weight:700;margin-right:10px">2</span>
              <span style="color:#f1f0ff;font-size:14px">Download the app at <a href="${landingUrl}/start.html" style="color:#a78bfa">influentia.io/start.html</a></span>
            </td></tr>
            <tr><td style="padding:10px 0">
              <span style="color:#7c6aff;font-weight:700;margin-right:10px">3</span>
              <span style="color:#f1f0ff;font-size:14px">Follow the <a href="${landingUrl}/start.html" style="color:#a78bfa">setup guide</a> — takes 10 minutes</span>
            </td></tr>
          </table>
          <div style="margin-top:28px;text-align:center">
            <a href="${landingUrl}/start.html" style="display:inline-block;background:#7c6aff;color:#fff;text-decoration:none;padding:14px 32px;border-radius:10px;font-weight:700;font-size:15px">Open Setup Guide →</a>
          </div>
        </td></tr>
        <!-- Book a call -->
        <tr><td style="padding:0 32px 28px">
          <div style="background:#0c0c0e;border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:16px 20px;display:flex;align-items:center;gap:16px">
            <div style="font-size:28px;flex-shrink:0">📅</div>
            <div>
              <div style="font-size:13px;font-weight:700;color:#f1f0ff;margin-bottom:4px">Want a quick walkthrough?</div>
              <div style="font-size:12px;color:#8b8a9e;margin-bottom:10px">I'll show you the dashboard live — 15 minutes, no prep needed.</div>
              <a href="mailto:info@ermoegberts.com?subject=Influentia setup call" style="display:inline-block;background:rgba(124,106,255,0.15);border:1px solid rgba(124,106,255,0.3);color:#a78bfa;padding:7px 16px;border-radius:8px;font-size:12px;font-weight:600;text-decoration:none">Book 15 min with Eurm →</a>
            </div>
          </div>
        </td></tr>
        <!-- Footer -->
        <tr><td style="padding:20px 32px;border-top:1px solid rgba(255,255,255,0.06);text-align:center">
          <div style="font-size:12px;color:#8b8a9e">Questions? Reply to this email or reach us at <a href="mailto:support@influentia.io" style="color:#a78bfa">support@influentia.io</a></div>
          <div style="font-size:11px;color:#555;margin-top:6px">You can always retrieve your key at <a href="${landingUrl}/account.html" style="color:#666">influentia.io/account.html</a></div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>`;

  try {
    await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${resendApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: 'Influentia <hello@influentia.io>',
        to: [email],
        subject: '🔑 Your Influentia license key',
        html,
      }),
    });
  } catch (err) {
    console.error('Failed to send license email:', err);
    // Non-fatal — key is shown on success page regardless
  }
}

// ── Per-license rate limiting (in-memory, resets on Worker cold start) ───────
// Limits: 120 proxy calls per hour per license key.
// This prevents abuse or runaway automation without affecting normal use
// (a typical active session does ~20–40 calls/hour).
const _rateLimitMap = new Map<string, { count: number; windowStart: number }>();
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000; // 1 hour
const RATE_LIMIT_MAX = 120; // calls per hour per license

function checkRateLimit(key: string): boolean {
  const now = Date.now();
  const entry = _rateLimitMap.get(key);
  if (!entry || now - entry.windowStart > RATE_LIMIT_WINDOW_MS) {
    _rateLimitMap.set(key, { count: 1, windowStart: now });
    return true; // allowed
  }
  if (entry.count >= RATE_LIMIT_MAX) return false; // blocked
  entry.count++;
  return true; // allowed
}

// ── Shared license-check helper for proxy routes ──────────────────────────
async function checkLicenseForProxy(
  key: string,
  db: D1Database,
  deviceId?: string,
  deviceName?: string,
): Promise<{ valid: boolean; reason?: string; tier?: string }> {
  if (!key) return { valid: false, reason: 'missing_key' };

  // Rate limit check (fast, in-memory — before any DB hit)
  if (!checkRateLimit(key)) {
    return { valid: false, reason: 'rate_limited' };
  }

  const now = Math.floor(Date.now() / 1000);

  const license = await db
    .prepare('SELECT * FROM licenses WHERE key = ?')
    .bind(key)
    .first<License>();

  if (!license) return { valid: false, reason: 'not_found' };

  // Update last_seen_at
  await db
    .prepare('UPDATE licenses SET last_seen_at = ? WHERE key = ?')
    .bind(now, key)
    .run();

  let tier = license.tier;
  if (tier === 'trial' && license.trial_ends_at && license.trial_ends_at < now) {
    tier = 'expired';
    await db.prepare('UPDATE licenses SET tier = ? WHERE key = ?').bind('expired', key).run();
  }

  if (tier === 'cancelled' || tier === 'expired') {
    return { valid: false, reason: 'revoked' };
  }

  // Device cap — enforced on every proxy call, not just validation
  if (deviceId) {
    const dev = await enforceDeviceCap(key, deviceId, deviceName, db);
    if (!dev.allowed) {
      return { valid: false, reason: 'device_limit' };
    }
  }

  return { valid: true, tier };
}

// ─── Usage caps + device caps ──────────────────────────────────────────────
// Per-license soft daily cap and hard monthly cap on Anthropic token spend.
// Heavy use is fine; runaway abuse is not. Defaults sized so a customer
// running maximum-cap LinkedIn outreach + Reddit scans stays well under.
const TOKEN_DAY_LIMIT   = 1_000_000;  // 1M tokens / day  (~$5 of Sonnet usage)
const TOKEN_MONTH_LIMIT = 3_000_000;  // 3M tokens / month (~$15)
const DEVICE_LIMIT      = 3;          // distinct device_ids per license

function dayKey(d: Date = new Date()): string {
  return d.toISOString().slice(0, 10);   // 'YYYY-MM-DD'
}
function monthKey(d: Date = new Date()): string {
  return d.toISOString().slice(0, 7);    // 'YYYY-MM'
}

/** Returns { allowed, reason, dayUsed, monthUsed } before a Claude call. */
async function enforceUsageCap(
  key: string,
  db: D1Database,
  tier: string = 'active'
): Promise<{ allowed: boolean; reason?: string; day_used?: number; month_used?: number }> {
  // Beta users get lower limits to control costs
  const dayLimit   = tier === 'beta' ? 50_000   : TOKEN_DAY_LIMIT;
  const monthLimit = tier === 'beta' ? 150_000  : TOKEN_MONTH_LIMIT;
  const day   = dayKey();
  const month = monthKey();

  const dayRow = await db
    .prepare(
      'SELECT tokens_in + tokens_out AS total FROM license_usage WHERE license_key = ? AND period_key = ? AND period_type = ?'
    )
    .bind(key, day, 'day')
    .first<{ total: number }>();
  const monthRow = await db
    .prepare(
      'SELECT tokens_in + tokens_out AS total FROM license_usage WHERE license_key = ? AND period_key = ? AND period_type = ?'
    )
    .bind(key, month, 'month')
    .first<{ total: number }>();

  const dayUsed   = dayRow?.total   ?? 0;
  const monthUsed = monthRow?.total ?? 0;

  if (monthUsed >= TOKEN_MONTH_LIMIT) {
    return { allowed: false, reason: 'monthly_cap', day_used: dayUsed, month_used: monthUsed };
  }
  if (dayUsed >= TOKEN_DAY_LIMIT) {
    return { allowed: false, reason: 'daily_cap', day_used: dayUsed, month_used: monthUsed };
  }
  return { allowed: true, day_used: dayUsed, month_used: monthUsed };
}

/** Records token usage after a successful Claude call. */
async function recordUsage(
  key: string,
  tokensIn: number,
  tokensOut: number,
  db: D1Database
): Promise<void> {
  const now   = Math.floor(Date.now() / 1000);
  const day   = dayKey();
  const month = monthKey();
  // UPSERT for both daily and monthly buckets.
  for (const [periodKey, periodType] of [[day, 'day'], [month, 'month']] as const) {
    await db
      .prepare(
        `INSERT INTO license_usage (license_key, period_key, period_type, tokens_in, tokens_out, request_count, updated_at)
         VALUES (?, ?, ?, ?, ?, 1, ?)
         ON CONFLICT(license_key, period_key, period_type) DO UPDATE SET
           tokens_in     = tokens_in + excluded.tokens_in,
           tokens_out    = tokens_out + excluded.tokens_out,
           request_count = request_count + 1,
           updated_at    = excluded.updated_at`
      )
      .bind(key, periodKey, periodType, tokensIn, tokensOut, now)
      .run();
  }
}

/**
 * Enforces device cap on license activate. Registers a new device_id if there
 * is room (<= DEVICE_LIMIT distinct devices). Refreshes last_seen_at if known.
 * Returns { allowed: false, reason: 'device_limit' } if the license already
 * has DEVICE_LIMIT distinct devices and this is a new one.
 */
async function enforceDeviceCap(
  key: string,
  deviceId: string | undefined,
  deviceName: string | undefined,
  db: D1Database
): Promise<{ allowed: boolean; reason?: string; device_count?: number }> {
  if (!deviceId) return { allowed: true };  // legacy clients without device_id pass

  const now = Math.floor(Date.now() / 1000);
  // Is this device already registered?
  const existing = await db
    .prepare('SELECT device_id FROM license_devices WHERE license_key = ? AND device_id = ?')
    .bind(key, deviceId)
    .first<{ device_id: string }>();

  if (existing) {
    await db
      .prepare('UPDATE license_devices SET last_seen_at = ? WHERE license_key = ? AND device_id = ?')
      .bind(now, key, deviceId)
      .run();
    return { allowed: true };
  }

  // New device — count current registrations.
  const count = await db
    .prepare('SELECT COUNT(*) AS n FROM license_devices WHERE license_key = ?')
    .bind(key)
    .first<{ n: number }>();
  const n = count?.n ?? 0;

  if (n >= DEVICE_LIMIT) {
    return { allowed: false, reason: 'device_limit', device_count: n };
  }

  await db
    .prepare(
      'INSERT INTO license_devices (license_key, device_id, device_name, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)'
    )
    .bind(key, deviceId, deviceName || null, now, now)
    .run();
  return { allowed: true, device_count: n + 1 };
}

// POST /api/proxy/message  — AI calls on behalf of a verified license
// Body: { license_key, model, max_tokens, messages, system? }
app.post('/api/proxy/message', async (c) => {
  try {
    const body = await c.req.json<{
      license_key: string;
      device_id?: string;
      model?: string;
      max_tokens?: number;
      messages: Array<{ role: string; content: string }>;
      system?: string;
    }>();

    const { license_key, device_id, model, max_tokens, messages, system } = body;

    const check = await checkLicenseForProxy(license_key, c.env.DB, device_id);
    if (!check.valid) {
      return c.json({ error: 'License invalid', reason: check.reason }, 403);
    }

    // Usage cap — daily soft + monthly hard. Beta users get lower limits.
    const cap = await enforceUsageCap(license_key, c.env.DB, check.tier);
    if (!cap.allowed) {
      const friendly =
        cap.reason === 'monthly_cap'
          ? 'You\'ve hit Influentia\'s fair-use monthly limit. The cap resets on the 1st. Reach out to support@influentia.io if you need an exception.'
          : 'You\'ve hit today\'s fair-use limit. The cap resets at midnight UTC. We do this to keep Influentia profitable so we can keep running it.';
      return c.json(
        {
          error: 'Usage cap reached',
          reason: cap.reason,
          message: friendly,
          day_used:   cap.day_used,
          month_used: cap.month_used,
        },
        429
      );
    }

    const anthropicBody: Record<string, unknown> = {
      model: model || 'claude-haiku-4-5-20251001',
      max_tokens: max_tokens || 256,
      messages,
    };
    if (system) anthropicBody.system = system;

    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': c.env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify(anthropicBody),
    });

    if (!resp.ok) {
      const err = await resp.text();
      console.error('Anthropic proxy error', resp.status, err);
      return c.json({ error: 'AI service error', status: resp.status }, 502);
    }

    const data = await resp.json() as { usage?: { input_tokens?: number; output_tokens?: number } };
    // Record usage after the call (Anthropic returns the actual token counts).
    const tokensIn  = data?.usage?.input_tokens  ?? 0;
    const tokensOut = data?.usage?.output_tokens ?? 0;
    if (tokensIn || tokensOut) {
      await recordUsage(license_key, tokensIn, tokensOut, c.env.DB);
    }
    return c.json(data);
  } catch (error) {
    console.error('Proxy message error:', error);
    return c.json({ error: 'Internal error' }, 500);
  }
});

// POST /api/proxy/search  — Brave Search on behalf of a verified license
// Body: { license_key, query, count?, offset? }
app.post('/api/proxy/search', async (c) => {
  try {
    const body = await c.req.json<{
      license_key: string;
      device_id?: string;
      query: string;
      count?: number;
      offset?: number;
      freshness?: string;
    }>();

    const { license_key, device_id, query, count = 20, offset = 0, freshness = '' } = body;

    if (!query) return c.json({ error: 'Missing query' }, 400);

    const check = await checkLicenseForProxy(license_key, c.env.DB, device_id);
    if (!check.valid) {
      return c.json({ error: 'License invalid', reason: check.reason }, 403);
    }

    const encoded = encodeURIComponent(query);
    const freshnessParam = freshness ? `&freshness=${freshness}` : '';
    const braveUrl = `https://api.search.brave.com/res/v1/web/search?q=${encoded}&count=${Math.min(20, count)}&offset=${offset}&search_lang=en${freshnessParam}`;

    const resp = await fetch(braveUrl, {
      headers: {
        Accept: 'application/json',
        'X-Subscription-Token': c.env.BRAVE_API_KEY,
      },
    });

    if (!resp.ok) {
      const err = await resp.text();
      console.error('Brave proxy error', resp.status, err);
      return c.json({ error: 'Search service error', status: resp.status }, 502);
    }

    const data = await resp.json();
    return c.json(data);
  } catch (error) {
    console.error('Proxy search error:', error);
    return c.json({ error: 'Internal error' }, 500);
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// VIDEO OUTREACH  — personalised landing pages for LinkedIn DMs
// ─────────────────────────────────────────────────────────────────────────────

/** Generate a short random token (12 URL-safe chars). */
function generateVideoToken(): string {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789';
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return Array.from(bytes).map((b) => chars[b % chars.length]).join('');
}

// POST /api/video/create
// Body: { license_key, lead_name, lead_company?, lead_linkedin_url?, video_url }
// Returns: { ok: true, token, landing_url }
app.post('/api/video/create', async (c) => {
  try {
    const body = await c.req.json<{
      license_key: string;
      lead_name: string;
      lead_company?: string;
      lead_linkedin_url?: string;
      video_url: string;
    }>();

    const { license_key, lead_name, lead_company, lead_linkedin_url, video_url } = body;

    if (!lead_name || !video_url) {
      return c.json({ error: 'Missing lead_name or video_url' }, 400);
    }

    const check = await checkLicenseForProxy(license_key, c.env.DB);
    if (!check.valid) {
      return c.json({ error: 'License invalid', reason: check.reason }, 403);
    }

    const token = generateVideoToken();
    const now = Math.floor(Date.now() / 1000);

    await c.env.DB.prepare(
      `INSERT INTO video_views (token, license_key, lead_name, lead_company, lead_linkedin_url, video_url, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(token, license_key, lead_name, lead_company ?? null, lead_linkedin_url ?? null, video_url, now)
      .run();

    const landing_url = `${c.env.LANDING_URL}/v?t=${token}`;
    return c.json({ ok: true, token, landing_url });
  } catch (error) {
    console.error('Video create error:', error);
    return c.json({ error: 'Internal error' }, 500);
  }
});

// GET /api/video/:token
// Returns lead data for the landing page + records the click
app.get('/api/video/:token', async (c) => {
  try {
    const token = c.req.param('token');
    if (!token) return c.json({ error: 'Missing token' }, 400);

    const row = await c.env.DB.prepare(
      `SELECT lead_name, lead_company, video_url, click_count FROM video_views WHERE token = ?`
    )
      .bind(token)
      .first<{ lead_name: string; lead_company: string | null; video_url: string; click_count: number }>();

    if (!row) return c.json({ error: 'Not found' }, 404);

    // Record click asynchronously (don't block the response)
    const now = Math.floor(Date.now() / 1000);
    c.executionCtx.waitUntil(
      c.env.DB.prepare(
        `UPDATE video_views SET click_count = click_count + 1, clicked_at = ? WHERE token = ? AND clicked_at IS NULL`
      )
        .bind(now, token)
        .run()
    );

    return c.json({
      ok: true,
      lead_name: row.lead_name,
      lead_company: row.lead_company,
      video_url: row.video_url,
    });
  } catch (error) {
    console.error('Video fetch error:', error);
    return c.json({ error: 'Internal error' }, 500);
  }
});

export default app;
