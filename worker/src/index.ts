import { Hono } from 'hono';
import { cors } from 'hono/cors';
import Stripe from 'stripe';

type Env = {
  DB: D1Database;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_PRICE_ID: string;
  LANDING_URL: string;
};

const app = new Hono<{ Bindings: Env }>();

// CORS for frontend calls
const ALLOWED_ORIGINS = [
  'https://outreachpilot.app',
  'https://outreach-pilot.pages.dev',
  'http://localhost:3000',
  'http://localhost:5173',
  'http://localhost:5555',
];

const strictCors = cors({
  origin: (origin) => ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
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

    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      line_items: [
        {
          price: c.env.STRIPE_PRICE_ID,
          quantity: 1,
        },
      ],
      subscription_data: {
        trial_period_days: 14,
      },
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
           VALUES (?, ?, ?, ?, ?, 'trial', ?, 'trialing', ?)`
        )
          .bind(
            key,
            email,
            session.customer || null,
            session.subscription || null,
            session.id,
            now + 7 * 86400,
            now
          )
          .run();
        console.log('License created:', { key, email, session_id: session.id });
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
        if (license.tier === 'trial' && newStatus === 'active') {
          newTier = 'active';
        } else if (newStatus === 'canceled' || newStatus === 'unpaid') {
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
    const { key } = await c.req.json<{ key: string }>();
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
    });
  } catch (error) {
    console.error('Validate error:', error);
    return c.json({ error: 'Failed to validate license' }, 500);
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

export default app;
