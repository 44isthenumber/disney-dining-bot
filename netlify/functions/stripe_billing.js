/** Stripe Checkout, Portal, and webhook apply. Tests inject a fake client. */

const crypto = require("crypto");
const userStore = require("./user_store");
const {
  isInternalUser,
  countActiveConsumerWatchRows,
  consumerWatchBudget,
  WatchBudgetError,
  WATCH_BUDGET_DETAIL,
} = require("./entitlement");

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

function isPaidCheckout(session) {
  if (!session) return false;
  if (session.payment_status === "unpaid") return false;
  if (session.status === "open" || session.status === "expired") return false;
  return session.payment_status === "paid" || session.payment_status === "no_payment_required";
}

function hasReservedCheckoutId(session) {
  const meta = session && session.metadata && session.metadata.user_id;
  const ref = session && session.client_reference_id;
  return userStore.isReservedId(meta) || userStore.isReservedId(ref);
}

function userIdFromSession(session) {
  return (
    (session && session.metadata && session.metadata.user_id) ||
    (session && session.client_reference_id) ||
    ""
  );
}

const PROMO_CODE_RE = /^[A-Za-z0-9-]{3,40}$/;

const CREATOR_COMPS = {
  eeccalisa: { planner_coupon: "creator-eeccalisa-planner", watch_cap: 10 },
};

function acceptedPromoCode(raw) {
  const code = String(raw == null ? "" : raw).trim();
  if (!PROMO_CODE_RE.test(code)) return null;
  return code;
}

function creatorCompFor(raw) {
  const code = acceptedPromoCode(raw);
  if (!code) return null;
  return CREATOR_COMPS[code.toLowerCase()] || null;
}

function watchCapFromMetadata(metadata) {
  if (!metadata || metadata.watch_cap == null || metadata.watch_cap === "") return null;
  const raw = metadata.watch_cap;
  if (typeof raw === "number") {
    if (Number.isFinite(raw) && Number.isInteger(raw) && raw > 0) return raw;
    return null;
  }
  const text = String(raw);
  if (!/^\d+$/.test(text)) return null;
  const n = Number(text);
  if (!Number.isInteger(n) || n <= 0) return null;
  return n;
}

function discountRejectedByStripe(err) {
  const raw = err && err.raw && err.raw.message;
  const msg = String((err && err.message) || raw || "").toLowerCase();
  return msg.includes("promotion code") || msg.includes("coupon") || msg.includes("does not apply");
}

async function lookupPromotionCode(stripe, promoCode) {
  const code = acceptedPromoCode(promoCode);
  if (!code) return null;
  try {
    const listed = await stripe.promotionCodes.list({
      code: code.toLowerCase(),
      active: true,
      limit: 1,
    });
    const found = listed && Array.isArray(listed.data) ? listed.data[0] : null;
    if (!found || !found.id) return null;
    const recorded = String(found.code || code).trim() || code;
    return { id: found.id, code: recorded };
  } catch {
    return null;
  }
}

async function createCheckoutSession({ user, sku, billableId, promoCode }) {
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
  const urls = checkoutUrls();
  const args = {
    mode: sku === "planner" ? "subscription" : "payment",
    client_reference_id: user.id,
    line_items: [{ price, quantity: 1 }],
    success_url: urls.success_url,
    cancel_url: urls.cancel_url,
    metadata: { user_id: user.id, sku },
  };
  if (sku === "single_watch" && billableId) {
    args.metadata.billable_id = billableId;
  }
  attachCustomer(args, user);
  const promo = await lookupPromotionCode(stripe, promoCode);
  if (promo) {
    args.discounts = [{ promotion_code: promo.id }];
    args.metadata.promo_code = promo.code;
  } else {
    args.allow_promotion_codes = true;
  }
  let session;
  try {
    session = await stripe.checkout.sessions.create(args);
  } catch (err) {
    if (!args.discounts || !discountRejectedByStripe(err)) throw err;
    const retry = {
      ...args,
      allow_promotion_codes: true,
      metadata: { ...args.metadata },
    };
    delete retry.discounts;
    session = await stripe.checkout.sessions.create(retry);
  }
  return { ok: true, session };
}

function checkoutUrls() {
  const origin = siteOrigin();
  return {
    success_url: `${origin}/?paid=ok&session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/?paid=cancel`,
  };
}

function attachCustomer(args, user) {
  if (user.stripe_customer_id) {
    args.customer = user.stripe_customer_id;
  } else if (user.email) {
    args.customer_email = user.email;
  }
}

async function createCreatorCompCheckout({ user, promoCode, billableId }) {
  if (!user || isInternalUser(user) || userStore.isReservedId(user.id)) {
    return { ok: false, status: 403, code: "internal_no_stripe", detail: "Internal accounts do not use Stripe." };
  }
  if (!isConfigured("planner")) return { ok: false, fallback: true };
  const stripe = getStripe();
  if (!stripe) return { ok: false, fallback: true };

  const accepted = acceptedPromoCode(promoCode);
  const comp = creatorCompFor(promoCode);
  if (!accepted || !comp) return { ok: false, fallback: true };

  if (!stripe.coupons || typeof stripe.coupons.retrieve !== "function") {
    return { ok: false, fallback: true };
  }
  let coupon;
  try {
    coupon = await stripe.coupons.retrieve(comp.planner_coupon);
  } catch {
    return { ok: false, fallback: true };
  }
  if (!coupon || typeof coupon !== "object" || coupon.valid === false) {
    return { ok: false, fallback: true };
  }
  if (coupon.max_redemptions != null && coupon.times_redeemed >= coupon.max_redemptions) {
    return { ok: false, fallback: true };
  }

  const price = String(process.env.STRIPE_PRICE_PLANNER || "").trim();
  const urls = checkoutUrls();
  const promo = accepted.toLowerCase();
  const metadata = {
    user_id: String(user.id),
    sku: "planner",
    promo_code: promo,
    creator_comp: "true",
    watch_cap: String(comp.watch_cap),
  };
  if (billableId) metadata.billable_id = String(billableId);
  const args = {
    mode: "subscription",
    client_reference_id: user.id,
    line_items: [{ price, quantity: 1 }],
    success_url: urls.success_url,
    cancel_url: urls.cancel_url,
    payment_method_collection: "if_required",
    discounts: [{ coupon: comp.planner_coupon }],
    metadata,
    subscription_data: {
      metadata: {
        user_id: String(user.id),
        promo_code: promo,
        creator_comp: "true",
        watch_cap: String(comp.watch_cap),
      },
    },
  };
  attachCustomer(args, user);

  let session;
  try {
    session = await stripe.checkout.sessions.create(args);
  } catch (err) {
    if (discountRejectedByStripe(err)) return { ok: false, fallback: true };
    throw err;
  }
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
  const { loadWatches, appendWatchPayload } = helpers;
  if (hasReservedCheckoutId(session)) return { skipped: "reserved" };

  const pending = await userStore.getCheckout(session.id);
  const billableId =
    (pending && pending.billable_id) || (session.metadata && session.metadata.billable_id);
  const watches = await loadWatches();
  const ownerId = (pending && pending.user_id) || userIdFromSession(session);
  const user = await userStore.getById(ownerId);
  if (!user) throw new Error("consumer not found");
  const customerId = customerIdFrom(session);

  async function finishAccount({ increment }) {
    await userStore.put({
      ...user,
      stripe_customer_id: customerId || user.stripe_customer_id,
      single_watch_count: increment
        ? Number(user.single_watch_count || 0) + 1
        : Number(user.single_watch_count || 0),
    });
    if (session.id) await userStore.deleteCheckout(session.id);
  }

  if (gistHasBillable(watches, ownerId, billableId)) {
    await finishAccount({ increment: Boolean(pending) });
    return { skipped: "already_written" };
  }
  if (!pending || !pending.watch) {
    throw new Error("pending checkout missing");
  }
  const incoming = (pending.watch.dates || []).length;
  const current = countActiveConsumerWatchRows(watches);
  const budget = consumerWatchBudget();
  if (current >= budget || current + incoming > budget) {
    throw new WatchBudgetError();
  }
  await appendWatchPayload(user, pending.watch, billableId);
  await finishAccount({ increment: true });
  return { applied: "single_watch" };
}

function periodEnd(sub) {
  const end = sub && (sub.current_period_end || (sub.items && sub.items.data && sub.items.data[0] && sub.items.data[0].current_period_end));
  if (!end) return null;
  if (typeof end === "number") return new Date(end * 1000).toISOString();
  return String(end);
}

async function applyPlannerFields(user, sub, customerId, metadata) {
  const fresh = (user && user.id && (await userStore.getById(user.id))) || user;
  const status = (sub && sub.status) || "active";
  let plannerStatus = "none";
  if (status === "active" || status === "trialing") plannerStatus = status;
  else if (status === "past_due") plannerStatus = "past_due";
  else if (status === "canceled" || status === "unpaid" || status === "incomplete_expired") plannerStatus = "canceled";
  else plannerStatus = status || "active";
  const next = {
    ...fresh,
    stripe_customer_id: customerId || (fresh && fresh.stripe_customer_id),
    planner_status: plannerStatus,
    planner_subscription_id: (sub && sub.id) || (fresh && fresh.planner_subscription_id),
    planner_current_period_end: periodEnd(sub),
    cancel_at_period_end: Boolean(sub && sub.cancel_at_period_end),
  };
  const cap = watchCapFromMetadata(metadata);
  if (cap != null) next.planner_watch_cap = cap;
  await userStore.put(next);
}

async function applyCheckoutCompleted(session, helpers) {
  if (hasReservedCheckoutId(session)) return { skipped: "reserved" };
  if (!isPaidCheckout(session)) return { skipped: "unpaid" };
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
    const subObj = sub && typeof sub === "object" ? sub : { id: sub, status: "active" };
    const metadata = { ...(subObj.metadata || {}), ...((session && session.metadata) || {}) };
    await applyPlannerFields(user, subObj, customerId, metadata);
    const pending = await userStore.getCheckout(session.id);
    const sessionBillable = session.metadata && session.metadata.billable_id;
    if (sessionBillable || (pending && pending.watch)) {
      const { loadWatches, appendWatchPayload } = helpers;
      const watches = await loadWatches();
      const ownerId = (pending && pending.user_id) || userIdFromSession(session);
      const billableId = sessionBillable || (pending && pending.billable_id);
      if (gistHasBillable(watches, ownerId, billableId)) {
        if (session.id) await userStore.deleteCheckout(session.id);
      } else if (pending && pending.watch) {
        const incoming = (pending.watch.dates || []).length;
        const current = countActiveConsumerWatchRows(watches);
        const budget = consumerWatchBudget();
        if (current >= budget || current + incoming > budget) {
          throw new WatchBudgetError();
        }
        const freshUser = (user && user.id && (await userStore.getById(user.id))) || user;
        await appendWatchPayload(freshUser, pending.watch, billableId);
        if (session.id) await userStore.deleteCheckout(session.id);
      } else {
        throw new Error("pending checkout missing");
      }
    }
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
  await applyPlannerFields(user, { ...sub, ...extras }, customerId, obj.metadata);
  return { applied: "subscription" };
}

async function applyStripeEvent(stripeEvent, helpers) {
  const type = stripeEvent.type;
  const obj = stripeEvent.data && stripeEvent.data.object;
  if (!obj) return { skipped: "no_object" };
  // completed can fire while payment_status is unpaid (Klarna, bank debit).
  // Fulfill only when paid / no_payment_required. Async success is a second event.
  if (type === "checkout.session.completed" || type === "checkout.session.async_payment_succeeded") {
    return applyCheckoutCompleted(obj, helpers);
  }
  if (type === "checkout.session.async_payment_failed") {
    return { skipped: "async_failed" };
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
    if (!isPaidCheckout(session)) {
      return { ok: true, pending: true };
    }
    try {
      await applyCheckoutCompleted(session, helpers);
    } catch (err) {
      if (err && err.code === "watch_budget") {
        return {
          ok: false,
          status: 503,
          code: "watch_budget",
          detail: err.detail || WATCH_BUDGET_DETAIL,
        };
      }
      throw err;
    }
  }
  if (user.stripe_customer_id && stripe.subscriptions && stripe.subscriptions.list) {
    const listed = await stripe.subscriptions.list({ customer: user.stripe_customer_id, status: "all", limit: 1 });
    const sub = listed && listed.data && listed.data[0];
    if (sub) await applyPlannerFields(user, sub, user.stripe_customer_id, sub.metadata);
  } else if (user.planner_subscription_id && stripe.subscriptions && stripe.subscriptions.retrieve) {
    const fresh = await userStore.getById(user.id);
    const sub = await stripe.subscriptions.retrieve(user.planner_subscription_id);
    await applyPlannerFields(fresh || user, sub, (fresh || user).stripe_customer_id, sub.metadata);
  }
  return { ok: true };
}

module.exports = {
  setStripeForTests,
  isConfigured,
  newBillableId,
  creatorCompFor,
  createCheckoutSession,
  createCreatorCompCheckout,
  createPortalSession,
  handleWebhook,
  syncSession,
  applyCheckoutCompleted,
  applyPlannerFields,
  applyStripeEvent,
  rawBody,
  isActiveWatch,
};
