/** Stripe Checkout, Portal, and webhook apply. Tests inject a fake client. */

const crypto = require("crypto");
const userStore = require("./user_store");
const { isInternalUser } = require("./entitlement");

let _stripeForTests = null;

function setStripeForTests(client) {
  _stripeForTests = client || null;
}

function isConfigured(sku) {
  if (!String(process.env.STRIPE_SECRET_KEY || "").trim()) return false;
  if (sku === "planner") return Boolean(String(process.env.STRIPE_PRICE_PLANNER || "").trim());
  return Boolean(String(process.env.STRIPE_PRICE_SINGLE_WATCH || "").trim());
}

function siteOrigin() {
  return String(process.env.URL || "https://magictablefinder.com").replace(/\/$/, "");
}

function newBillableId() {
  return `bill_${crypto.randomBytes(8).toString("hex")}`;
}

function getStripe() {
  if (_stripeForTests) return _stripeForTests;
  const key = String(process.env.STRIPE_SECRET_KEY || "").trim();
  if (!key) return null;
  const Stripe = require("stripe");
  return new Stripe(key);
}

function billingUnavailable() {
  return {
    ok: false,
    status: 503,
    code: "billing_unavailable",
    detail: "Paid watches are not available yet.",
  };
}

function rawBody(event) {
  if (!event || event.body == null) return "";
  if (event.isBase64Encoded) {
    return Buffer.from(event.body, "base64").toString("utf8");
  }
  return typeof event.body === "string" ? event.body : JSON.stringify(event.body);
}

function customerIdFrom(session) {
  const c = session && session.customer;
  if (!c) return null;
  return typeof c === "string" ? c : c.id || null;
}

function userIdFromSession(session) {
  return (
    (session && session.metadata && session.metadata.user_id) ||
    (session && session.client_reference_id) ||
    ""
  );
}

async function createCheckoutSession({ user, sku, billableId }) {
  if (!user || isInternalUser(user) || userStore.isReservedId(user.id)) {
    return { ok: false, status: 403, code: "internal_no_stripe", detail: "Internal accounts do not use Stripe." };
  }
  if (!isConfigured(sku)) return billingUnavailable();
  const stripe = getStripe();
  if (!stripe) return billingUnavailable();

  const price =
    sku === "planner"
      ? String(process.env.STRIPE_PRICE_PLANNER || "").trim()
      : String(process.env.STRIPE_PRICE_SINGLE_WATCH || "").trim();
  const origin = siteOrigin();
  const args = {
    mode: sku === "planner" ? "subscription" : "payment",
    client_reference_id: user.id,
    line_items: [{ price, quantity: 1 }],
    success_url: `${origin}/?paid=ok&session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/?paid=cancel`,
    metadata: { user_id: user.id, sku },
  };
  if (sku === "single_watch" && billableId) {
    args.metadata.billable_id = billableId;
  }
  if (user.stripe_customer_id) {
    args.customer = user.stripe_customer_id;
  } else if (user.email) {
    args.customer_email = user.email;
  }
  const session = await stripe.checkout.sessions.create(args);
  return { ok: true, session };
}

async function createPortalSession(user) {
  if (!user || isInternalUser(user) || userStore.isReservedId(user.id)) {
    return { ok: false, status: 403, code: "internal_no_stripe", detail: "Internal accounts do not use Stripe." };
  }
  if (!user.stripe_customer_id) {
    return { ok: false, status: 404, code: "no_customer", detail: "No billing customer yet." };
  }
  if (!String(process.env.STRIPE_SECRET_KEY || "").trim()) return billingUnavailable();
  const stripe = getStripe();
  if (!stripe) return billingUnavailable();
  const session = await stripe.billingPortal.sessions.create({
    customer: user.stripe_customer_id,
    return_url: `${siteOrigin()}/?billing=portal`,
  });
  return { ok: true, url: session.url };
}

function todayIso() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function isActiveWatch(watch, today = todayIso()) {
  return typeof watch.date === "string" && watch.date >= today;
}

function gistHasBillable(watches, ownerId, billableId) {
  if (!billableId) return false;
  return (watches || []).some(
    (w) => w.owner_id === ownerId && w.billable_id === billableId && isActiveWatch(w)
  );
}

async function findConsumerForStripe(sessionOrSub) {
  const meta = (sessionOrSub && sessionOrSub.metadata) || {};
  const customerId = customerIdFrom(sessionOrSub) || sessionOrSub.customer || null;
  if (customerId) {
    const byCus = await userStore.getByStripeCustomerId(customerId);
    if (byCus && !userStore.isReservedId(byCus.id)) return byCus;
  }
  const uid = meta.user_id || sessionOrSub.client_reference_id || "";
  if (userStore.isReservedId(uid)) return null;
  if (uid) {
    const byId = await userStore.getById(uid);
    if (byId) return byId;
  }
  return null;
}

async function applySingleWatchSession(session, helpers) {
  const { loadWatches, saveWatches, appendWatchPayload } = helpers;
  const userId = userIdFromSession(session);
  if (userStore.isReservedId(userId)) return { skipped: "reserved" };

  const pending = await userStore.getCheckout(session.id);
  const billableId =
    (pending && pending.billable_id) || (session.metadata && session.metadata.billable_id);
  const watches = await loadWatches();
  const ownerId = (pending && pending.user_id) || userId;
  if (gistHasBillable(watches, ownerId, billableId)) {
    return { skipped: "already_written" };
  }
  if (!pending || !pending.watch) {
    if (!billableId) throw new Error("pending checkout missing");
    throw new Error("pending checkout missing");
  }
  const user = await userStore.getById(pending.user_id || userId);
  if (!user) throw new Error("consumer not found");
  const customerId = customerIdFrom(session);
  await appendWatchPayload(user, pending.watch, billableId);
  await userStore.put({
    ...user,
    stripe_customer_id: customerId || user.stripe_customer_id,
    single_watch_count: Number(user.single_watch_count || 0) + 1,
  });
  await userStore.deleteCheckout(session.id);
  return { applied: "single_watch" };
}

function periodEnd(sub) {
  const end = sub && (sub.current_period_end || (sub.items && sub.items.data && sub.items.data[0] && sub.items.data[0].current_period_end));
  if (!end) return null;
  if (typeof end === "number") return new Date(end * 1000).toISOString();
  return String(end);
}

async function applyPlannerFields(user, sub, customerId) {
  const status = (sub && sub.status) || "active";
  let plannerStatus = "none";
  if (status === "active" || status === "trialing") plannerStatus = status;
  else if (status === "past_due") plannerStatus = "past_due";
  else if (status === "canceled" || status === "unpaid" || status === "incomplete_expired") plannerStatus = "canceled";
  else plannerStatus = status || "active";
  await userStore.put({
    ...user,
    stripe_customer_id: customerId || user.stripe_customer_id,
    planner_status: plannerStatus,
    planner_subscription_id: (sub && sub.id) || user.planner_subscription_id,
    planner_current_period_end: periodEnd(sub),
    cancel_at_period_end: Boolean(sub && sub.cancel_at_period_end),
  });
}

async function applyCheckoutCompleted(session, helpers) {
  const userId = userIdFromSession(session);
  if (userStore.isReservedId(userId)) return { skipped: "reserved" };
  const sku = (session.metadata && session.metadata.sku) || "";
  if (sku === "single_watch") {
    return applySingleWatchSession(session, helpers);
  }
  const user = await findConsumerForStripe(session);
  if (!user) return { skipped: "no_user" };
  const customerId = customerIdFrom(session);
  const stripe = getStripe();
  let sub = session.subscription;
  if (typeof sub === "string" && stripe && stripe.subscriptions && stripe.subscriptions.retrieve) {
    sub = await stripe.subscriptions.retrieve(sub);
  }
  if (sku === "planner" || session.mode === "subscription") {
    await applyPlannerFields(user, sub && typeof sub === "object" ? sub : { id: sub, status: "active" }, customerId);
  } else if (customerId) {
    await userStore.put({ ...user, stripe_customer_id: customerId });
  }
  return { applied: "planner" };
}

async function applySubscriptionLike(obj, extras = {}) {
  const user = await findConsumerForStripe(obj);
  if (!user) {
    const uid = (obj.metadata && obj.metadata.user_id) || obj.client_reference_id;
    if (userStore.isReservedId(uid)) return { skipped: "reserved" };
    return { skipped: "no_user" };
  }
  const customerId = customerIdFrom(obj) || obj.customer;
  const sub = obj.object === "subscription" ? obj : obj;
  await applyPlannerFields(user, { ...sub, ...extras }, customerId);
  return { applied: "subscription" };
}

async function applyStripeEvent(stripeEvent, helpers) {
  const type = stripeEvent.type;
  const obj = stripeEvent.data && stripeEvent.data.object;
  if (!obj) return { skipped: "no_object" };
  if (type === "checkout.session.completed") {
    return applyCheckoutCompleted(obj, helpers);
  }
  if (
    type === "customer.subscription.created" ||
    type === "customer.subscription.updated"
  ) {
    return applySubscriptionLike(obj);
  }
  if (type === "customer.subscription.deleted") {
    return applySubscriptionLike(obj, { status: "canceled" });
  }
  if (type === "invoice.paid") {
    const user = await findConsumerForStripe({
      customer: obj.customer,
      metadata: obj.subscription_details && obj.subscription_details.metadata,
    });
    if (!user) return { skipped: "no_user" };
    if (user.planner_status === "past_due") {
      await userStore.put({ ...user, planner_status: "active" });
    }
    return { applied: "invoice.paid" };
  }
  if (type === "invoice.payment_failed") {
    const user = await findConsumerForStripe({ customer: obj.customer, metadata: obj.metadata });
    if (!user) return { skipped: "no_user" };
    if (user.planner_subscription_id || user.planner_status === "active" || user.planner_status === "trialing") {
      await userStore.put({ ...user, planner_status: "past_due" });
    }
    return { applied: "invoice.payment_failed" };
  }
  return { skipped: "unhandled" };
}

async function handleWebhook(event, helpers) {
  const stripe = getStripe();
  const secret = String(process.env.STRIPE_WEBHOOK_SECRET || "").trim();
  if (!stripe || !secret) {
    return { statusCode: 503, body: { code: "billing_unavailable", detail: "Paid watches are not available yet." } };
  }
  const sig = (() => {
    const headers = event.headers || {};
    for (const [k, v] of Object.entries(headers)) {
      if (String(k).toLowerCase() === "stripe-signature") return Array.isArray(v) ? v[0] : v;
    }
    return "";
  })();
  let stripeEvent;
  try {
    stripeEvent = stripe.webhooks.constructEvent(rawBody(event), sig, secret);
  } catch {
    return { statusCode: 400, body: { detail: "Invalid signature" } };
  }
  const eventKey = `stripe_event:${stripeEvent.id}`;
  if (await userStore.isNonceUsed(eventKey)) {
    return { statusCode: 200, body: { ok: true, duplicate: true } };
  }
  try {
    await applyStripeEvent(stripeEvent, helpers);
  } catch (err) {
    return { statusCode: 500, body: { detail: err.message || "apply failed" } };
  }
  await userStore.claimNonce(eventKey);
  return { statusCode: 200, body: { ok: true } };
}

async function syncSession(user, sessionId, helpers) {
  if (!user || isInternalUser(user)) {
    return { ok: false, status: 403, code: "internal_no_stripe", detail: "Internal accounts do not use Stripe." };
  }
  const stripe = getStripe();
  if (!stripe) return billingUnavailable();
  if (sessionId && stripe.checkout && stripe.checkout.sessions && stripe.checkout.sessions.retrieve) {
    const session = await stripe.checkout.sessions.retrieve(sessionId);
    const uid = userIdFromSession(session);
    if (uid && uid !== user.id) {
      return { ok: false, status: 403, code: "mismatch", detail: "Checkout does not belong to this account." };
    }
    await applyCheckoutCompleted(session, helpers);
  }
  if (user.stripe_customer_id && stripe.subscriptions && stripe.subscriptions.list) {
    const listed = await stripe.subscriptions.list({ customer: user.stripe_customer_id, status: "all", limit: 1 });
    const sub = listed && listed.data && listed.data[0];
    if (sub) await applyPlannerFields(user, sub, user.stripe_customer_id);
  } else if (user.planner_subscription_id && stripe.subscriptions && stripe.subscriptions.retrieve) {
    const fresh = await userStore.getById(user.id);
    const sub = await stripe.subscriptions.retrieve(user.planner_subscription_id);
    await applyPlannerFields(fresh || user, sub, (fresh || user).stripe_customer_id);
  }
  return { ok: true };
}

module.exports = {
  setStripeForTests,
  isConfigured,
  newBillableId,
  createCheckoutSession,
  createPortalSession,
  handleWebhook,
  syncSession,
  applyCheckoutCompleted,
  applyStripeEvent,
  rawBody,
  isActiveWatch,
};
