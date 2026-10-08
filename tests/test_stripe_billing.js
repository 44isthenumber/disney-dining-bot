#!/usr/bin/env node
const assert = require("assert");

process.env.MTF_USER_STORE = "memory";
process.env.STRIPE_SECRET_KEY = "sk_test_fake";
process.env.STRIPE_WEBHOOK_SECRET = "whsec_test";
process.env.STRIPE_PRICE_SINGLE_WATCH = "price_single";
process.env.STRIPE_PRICE_PLANNER = "price_planner";
process.env.URL = "https://magictablefinder.com";

const store = require("../netlify/functions/user_store");
store.resetMemoryStore();
const billing = require("../netlify/functions/stripe_billing");

function fakeStripe() {
  const created = [];
  const portal = [];
  const promoLists = [];
  const promos = { byCode: {}, throwOn: false };
  return {
    created,
    portal,
    promoLists,
    promos,
    promotionCodes: {
      list: async (query) => {
        promoLists.push(query);
        if (promos.throwOn) {
          promos.throwOn = false;
          throw new Error("lookup failed");
        }
        const code = String((query && query.code) || "");
        const found = promos.byCode[code];
        return { data: found ? [found] : [] };
      },
    },
    checkout: {
      sessions: {
        create: async (args) => {
          created.push(args);
          return {
            id: "cs_test_1",
            url: "https://checkout.stripe.com/c/pay/cs_test_1",
            customer: args.customer || null,
            metadata: args.metadata,
            client_reference_id: args.client_reference_id,
            mode: args.mode,
          };
        },
        retrieve: async () => null,
      },
    },
    billingPortal: {
      sessions: {
        create: async (args) => {
          portal.push(args);
          return { url: "https://billing.stripe.com/session/test" };
        },
      },
    },
    webhooks: {
      constructEvent: (body, sig) => {
        if (sig !== "sig_ok") throw new Error("bad sig");
        return JSON.parse(body);
      },
    },
  };
}

(async function main() {
  const stripe = fakeStripe();
  billing.setStripeForTests(stripe);

  const user = await store.upsertByEmail("pay@example.com");
  const first = await billing.createCheckoutSession({
    user,
    sku: "single_watch",
    billableId: "bill_abc",
  });
  assert.strictEqual(first.ok, true);
  const args = stripe.created[0];
  assert.strictEqual(args.mode, "payment");
  assert.strictEqual(args.allow_promotion_codes, true);
  assert.ok(!Object.prototype.hasOwnProperty.call(args, "discounts"));
  assert.strictEqual(args.client_reference_id, user.id);
  assert.strictEqual(args.metadata.user_id, user.id);
  assert.strictEqual(args.metadata.sku, "single_watch");
  assert.strictEqual(args.metadata.billable_id, "bill_abc");
  assert.strictEqual(args.customer_email, "pay@example.com");
  assert.ok(!Object.prototype.hasOwnProperty.call(args, "customer"));
  assert.strictEqual(args.line_items[0].quantity, 1);
  assert.ok(args.success_url.includes("paid=ok"));

  await store.put({ ...user, stripe_customer_id: "cus_1" });
  const withCustomer = await store.getById(user.id);
  stripe.created.length = 0;
  await billing.createCheckoutSession({ user: withCustomer, sku: "planner" });
  const subArgs = stripe.created[0];
  assert.strictEqual(subArgs.mode, "subscription");
  assert.strictEqual(subArgs.allow_promotion_codes, true);
  assert.ok(!Object.prototype.hasOwnProperty.call(subArgs, "discounts"));
  assert.strictEqual(subArgs.customer, "cus_1");
  assert.ok(!Object.prototype.hasOwnProperty.call(subArgs, "customer_email"));

  const internal = await billing.createCheckoutSession({
    user: { id: "craig", kind: "internal" },
    sku: "single_watch",
  });
  assert.strictEqual(internal.status, 403);
  assert.strictEqual(internal.code, "internal_no_stripe");

  stripe.promos.byCode.eeccalisa = { id: "promo_1UO5Ek5BXyxSSEMUtvf0uxkF", code: "eeccalisa" };
  stripe.created.length = 0;
  stripe.promoLists.length = 0;
  const withPromo = await billing.createCheckoutSession({
    user,
    sku: "single_watch",
    billableId: "bill_promo",
    promoCode: "eeccalisa",
  });
  assert.strictEqual(withPromo.ok, true);
  const promoArgs = stripe.created[0];
  assert.deepStrictEqual(promoArgs.discounts, [{ promotion_code: "promo_1UO5Ek5BXyxSSEMUtvf0uxkF" }]);
  assert.ok(!Object.prototype.hasOwnProperty.call(promoArgs, "allow_promotion_codes"));
  assert.strictEqual(promoArgs.metadata.promo_code, "eeccalisa");
  assert.strictEqual(promoArgs.metadata.billable_id, "bill_promo");
  assert.strictEqual(stripe.promoLists.length, 1);
  assert.deepStrictEqual(stripe.promoLists[0], { code: "eeccalisa", active: true, limit: 1 });

  stripe.created.length = 0;
  stripe.promoLists.length = 0;
  const upperPromo = await billing.createCheckoutSession({
    user,
    sku: "single_watch",
    promoCode: " EECCALISA ",
  });
  assert.strictEqual(upperPromo.ok, true);
  assert.deepStrictEqual(stripe.promoLists[0], { code: "eeccalisa", active: true, limit: 1 });
  assert.deepStrictEqual(stripe.created[0].discounts, [{ promotion_code: "promo_1UO5Ek5BXyxSSEMUtvf0uxkF" }]);
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0], "allow_promotion_codes"));
  assert.strictEqual(stripe.created[0].metadata.promo_code, "eeccalisa");

  stripe.created.length = 0;
  stripe.promoLists.length = 0;
  const unknownPromo = await billing.createCheckoutSession({
    user,
    sku: "single_watch",
    promoCode: "not-a-real-code",
  });
  assert.strictEqual(unknownPromo.ok, true);
  assert.strictEqual(stripe.promoLists.length, 1);
  assert.strictEqual(stripe.created[0].allow_promotion_codes, true);
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0], "discounts"));
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0].metadata, "promo_code"));

  stripe.created.length = 0;
  stripe.promoLists.length = 0;
  const invalidPromo = await billing.createCheckoutSession({
    user,
    sku: "single_watch",
    promoCode: "bad code!",
  });
  assert.strictEqual(invalidPromo.ok, true);
  assert.strictEqual(stripe.promoLists.length, 0);
  assert.strictEqual(stripe.created[0].allow_promotion_codes, true);
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0], "discounts"));
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0].metadata, "promo_code"));

  stripe.created.length = 0;
  const shortPromo = await billing.createCheckoutSession({
    user,
    sku: "planner",
    promoCode: "ab",
  });
  assert.strictEqual(shortPromo.ok, true);
  assert.strictEqual(stripe.promoLists.length, 0);
  assert.strictEqual(stripe.created[0].allow_promotion_codes, true);
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0], "discounts"));

  stripe.promos.throwOn = true;
  stripe.created.length = 0;
  const lookupThrew = await billing.createCheckoutSession({
    user,
    sku: "single_watch",
    promoCode: "eeccalisa",
  });
  assert.strictEqual(lookupThrew.ok, true);
  assert.strictEqual(stripe.created[0].allow_promotion_codes, true);
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0], "discounts"));
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0].metadata, "promo_code"));

  const originalCreate = stripe.checkout.sessions.create;
  let createAttempts = 0;
  stripe.checkout.sessions.create = async (sessionArgs) => {
    createAttempts += 1;
    stripe.created.push(sessionArgs);
    if (createAttempts === 1) throw new Error("This coupon does not apply");
    return {
      id: "cs_retry",
      url: "https://checkout.stripe.com/c/pay/cs_retry",
      customer: sessionArgs.customer || null,
      metadata: sessionArgs.metadata,
      client_reference_id: sessionArgs.client_reference_id,
      mode: sessionArgs.mode,
    };
  };
  stripe.created.length = 0;
  const retried = await billing.createCheckoutSession({
    user: withCustomer,
    sku: "planner",
    promoCode: "eeccalisa",
  });
  assert.strictEqual(retried.ok, true);
  assert.strictEqual(retried.session.id, "cs_retry");
  assert.strictEqual(createAttempts, 2);
  assert.deepStrictEqual(stripe.created[0].discounts, [{ promotion_code: "promo_1UO5Ek5BXyxSSEMUtvf0uxkF" }]);
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0], "allow_promotion_codes"));
  assert.strictEqual(stripe.created[0].metadata.promo_code, "eeccalisa");
  assert.strictEqual(stripe.created[1].allow_promotion_codes, true);
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[1], "discounts"));
  assert.strictEqual(stripe.created[1].metadata.promo_code, "eeccalisa");
  stripe.checkout.sessions.create = originalCreate;

  createAttempts = 0;
  stripe.checkout.sessions.create = async (sessionArgs) => {
    createAttempts += 1;
    stripe.created.push(sessionArgs);
    throw new Error("socket hang up");
  };
  stripe.created.length = 0;
  let networkErr = null;
  try {
    await billing.createCheckoutSession({
      user,
      sku: "single_watch",
      promoCode: "eeccalisa",
    });
  } catch (err) {
    networkErr = err;
  }
  assert.ok(networkErr);
  assert.strictEqual(networkErr.message, "socket hang up");
  assert.strictEqual(createAttempts, 1);
  assert.deepStrictEqual(stripe.created[0].discounts, [{ promotion_code: "promo_1UO5Ek5BXyxSSEMUtvf0uxkF" }]);
  assert.ok(!Object.prototype.hasOwnProperty.call(stripe.created[0], "allow_promotion_codes"));
  stripe.checkout.sessions.create = originalCreate;

  const writes = [];
  const helpers = {
    loadWatches: async () => writes.slice(),
    saveWatches: async (rows) => {
      writes.splice(0, writes.length, ...rows);
    },
    appendWatchPayload: async (u, payload, billableId) => {
      for (const date of payload.dates) {
        writes.push({
          owner_id: u.id,
          facility_id: payload.facility_id,
          date,
          billable_id: billableId,
          recipient_phone: u.phone || "",
        });
      }
    },
  };

  const reserved = await billing.applyStripeEvent(
    {
      id: "evt_reserved",
      type: "checkout.session.completed",
      data: {
        object: {
          id: "cs_bad",
          client_reference_id: "craig",
          metadata: { user_id: "craig", sku: "single_watch" },
        },
      },
    },
    helpers
  );
  assert.strictEqual(reserved.skipped, "reserved");
  assert.strictEqual(writes.length, 0);

  await store.put({ ...withCustomer, phone: "+15551212" });
  const paidUser = await store.getById(user.id);
  await store.putCheckout("cs_test_1", {
    user_id: paidUser.id,
    sku: "single_watch",
    billable_id: "bill_abc",
    watch: {
      facility_id: "90002686",
      name: "Test",
      slug: "test",
      party_size: 2,
      dates: ["2099-01-01", "2099-01-02"],
      meal_periods: ["DINNER"],
    },
  });
  await billing.applyCheckoutCompleted(
    {
      id: "cs_test_1",
      payment_status: "paid",
      customer: "cus_1",
      metadata: { user_id: paidUser.id, sku: "single_watch", billable_id: "bill_abc" },
      client_reference_id: paidUser.id,
    },
    helpers
  );
  assert.strictEqual(writes.length, 2);
  assert.ok(writes.every((w) => w.billable_id === "bill_abc"));
  assert.ok(writes.every((w) => w.recipient_phone === "+15551212"));
  const after = await store.getById(paidUser.id);
  assert.strictEqual(after.single_watch_count, 1);

  await billing.applyCheckoutCompleted(
    {
      id: "cs_test_1",
      payment_status: "paid",
      customer: "cus_1",
      metadata: { user_id: paidUser.id, sku: "single_watch", billable_id: "bill_abc" },
      client_reference_id: paidUser.id,
    },
    helpers
  );
  assert.strictEqual(writes.length, 2);

  const freeUser = await store.upsertByEmail("free100@example.com");
  await store.put({ ...freeUser, phone: "+15557777" });
  const freeFresh = await store.getById(freeUser.id);
  await store.putCheckout("cs_free_100", {
    user_id: freeFresh.id,
    sku: "single_watch",
    billable_id: "bill_free_100",
    watch: {
      facility_id: "90002686",
      name: "Free",
      slug: "free",
      party_size: 2,
      dates: ["2099-02-01", "2099-02-02"],
      meal_periods: ["DINNER"],
    },
  });
  const freeApplied = await billing.applyCheckoutCompleted(
    {
      id: "cs_free_100",
      status: "complete",
      payment_status: "no_payment_required",
      customer: "cus_free",
      metadata: { user_id: freeFresh.id, sku: "single_watch", billable_id: "bill_free_100" },
      client_reference_id: freeFresh.id,
    },
    helpers
  );
  assert.strictEqual(freeApplied.applied, "single_watch");
  assert.ok(
    writes.some((w) => w.billable_id === "bill_free_100" && w.owner_id === freeFresh.id)
  );
  assert.ok(
    writes
      .filter((w) => w.billable_id === "bill_free_100")
      .every((w) => w.recipient_phone === "+15557777")
  );
  assert.strictEqual(writes.filter((w) => w.billable_id === "bill_free_100").length, 2);
  const freeAfter = await store.getById(freeFresh.id);
  assert.strictEqual(freeAfter.single_watch_count, 1);
  assert.strictEqual(freeAfter.stripe_customer_id, "cus_free");
  assert.strictEqual(await store.getCheckout("cs_free_100"), null);

  const mixedReserved = await billing.applyCheckoutCompleted(
    {
      id: "cs_mix",
      payment_status: "paid",
      client_reference_id: "craig",
      metadata: { user_id: paidUser.id, sku: "single_watch", billable_id: "bill_hack" },
      customer: "cus_evil",
    },
    helpers
  );
  assert.strictEqual(mixedReserved.skipped, "reserved");

  const unpaid = await billing.applyCheckoutCompleted(
    {
      id: "cs_open",
      status: "open",
      payment_status: "unpaid",
      metadata: { user_id: paidUser.id, sku: "single_watch", billable_id: "bill_open" },
      client_reference_id: paidUser.id,
    },
    helpers
  );
  assert.strictEqual(unpaid.skipped, "unpaid");
  assert.strictEqual(writes.length, 4);

  const asyncUser = await store.upsertByEmail("async@example.com");
  await store.put({ ...asyncUser, phone: "+15558888" });
  await store.putCheckout("cs_async", {
    user_id: asyncUser.id,
    billable_id: "bill_async",
    watch: { facility_id: "x", dates: ["2099-04-01"], party_size: 2, meal_periods: ["DINNER"] },
  });
  const asyncSucceeded = await billing.applyStripeEvent(
    {
      id: "evt_async_ok",
      type: "checkout.session.async_payment_succeeded",
      data: {
        object: {
          id: "cs_async",
          payment_status: "paid",
          customer: "cus_async",
          metadata: { user_id: asyncUser.id, sku: "single_watch", billable_id: "bill_async" },
          client_reference_id: asyncUser.id,
        },
      },
    },
    helpers
  );
  assert.strictEqual(asyncSucceeded.applied, "single_watch");
  assert.ok(writes.some((w) => w.billable_id === "bill_async" && w.owner_id === asyncUser.id));

  const asyncFailed = await billing.applyStripeEvent(
    {
      id: "evt_async_fail",
      type: "checkout.session.async_payment_failed",
      data: {
        object: {
          id: "cs_async_fail",
          payment_status: "unpaid",
          metadata: { user_id: asyncUser.id, sku: "single_watch", billable_id: "bill_fail" },
          client_reference_id: asyncUser.id,
        },
      },
    },
    helpers
  );
  assert.strictEqual(asyncFailed.skipped, "async_failed");
  assert.ok(!writes.some((w) => w.billable_id === "bill_fail"));

  const repairUser = await store.upsertByEmail("repair@example.com");
  await store.put({ ...repairUser, phone: "+15550000", single_watch_count: 2 });
  await store.putCheckout("cs_repair", {
    user_id: repairUser.id,
    billable_id: "bill_repair",
    watch: { facility_id: "x", dates: ["2099-03-01"], party_size: 2, meal_periods: ["DINNER"] },
  });
  writes.push({
    owner_id: repairUser.id,
    billable_id: "bill_repair",
    date: "2099-03-01",
    facility_id: "x",
  });
  await billing.applyCheckoutCompleted(
    {
      id: "cs_repair",
      payment_status: "paid",
      customer: "cus_repair",
      metadata: { user_id: repairUser.id, sku: "single_watch", billable_id: "bill_repair" },
      client_reference_id: repairUser.id,
    },
    helpers
  );
  const repaired = await store.getById(repairUser.id);
  assert.strictEqual(repaired.stripe_customer_id, "cus_repair");
  assert.strictEqual(repaired.single_watch_count, 3);
  assert.strictEqual(await store.getCheckout("cs_repair"), null);

  const plannerUser = await store.upsertByEmail("plan@example.com");
  const writesBeforePlanner = writes.length;
  await billing.applyCheckoutCompleted(
    {
      id: "cs_plan",
      mode: "subscription",
      payment_status: "paid",
      status: "complete",
      customer: "cus_plan",
      metadata: { user_id: plannerUser.id, sku: "planner" },
      client_reference_id: plannerUser.id,
      subscription: { id: "sub_1", status: "active", current_period_end: 2000000000 },
    },
    helpers
  );
  assert.strictEqual(writes.length, writesBeforePlanner);
  const planned = await store.getById(plannerUser.id);
  assert.strictEqual(planned.planner_status, "active");
  assert.strictEqual(planned.stripe_customer_id, "cus_plan");

  const whBad = await billing.handleWebhook(
    { body: "{}", headers: { "stripe-signature": "nope" } },
    helpers
  );
  assert.strictEqual(whBad.statusCode, 400);

  const eventBody = JSON.stringify({
    id: "evt_1",
    type: "invoice.payment_failed",
    data: { object: { customer: "cus_plan" } },
  });
  const wh = await billing.handleWebhook(
    { body: eventBody, headers: { "stripe-signature": "sig_ok" } },
    helpers
  );
  assert.strictEqual(wh.statusCode, 200);
  const past = await store.getById(plannerUser.id);
  assert.strictEqual(past.planner_status, "past_due");

  const dup = await billing.handleWebhook(
    { body: eventBody, headers: { "stripe-signature": "sig_ok" } },
    helpers
  );
  assert.strictEqual(dup.statusCode, 200);
  assert.strictEqual(dup.body.duplicate, true);

  const portal = await billing.createPortalSession(planned);
  assert.strictEqual(portal.ok, true);
  assert.ok(portal.url.startsWith("https://"));
  const noCus = await billing.createPortalSession(await store.upsertByEmail("none@example.com"));
  assert.strictEqual(noCus.status, 404);

  stripe.checkout.sessions.retrieve = async () => ({
    id: "cs_sync_open",
    status: "open",
    payment_status: "unpaid",
    metadata: { user_id: paidUser.id, sku: "single_watch" },
    client_reference_id: paidUser.id,
  });
  const syncOpen = await billing.syncSession(paidUser, "cs_sync_open", helpers);
  assert.strictEqual(syncOpen.ok, true);
  assert.strictEqual(syncOpen.pending, true);

  process.env.CONSUMER_ACTIVE_WATCH_BUDGET = "1";
  const budgetUser = await store.upsertByEmail("budget@example.com");
  await store.put({ ...budgetUser, phone: "+15559999" });
  await store.putCheckout("cs_over_budget", {
    user_id: budgetUser.id,
    sku: "single_watch",
    billable_id: "bill_over",
    watch: { facility_id: "x", dates: ["2099-09-01"], party_size: 2, meal_periods: ["DINNER"] },
  });
  const writesBeforeOver = writes.length;
  writes.push({
    owner_id: "u_existing_consumer",
    date: "2099-09-02",
    facility_id: "x",
  });
  let overErr = null;
  try {
    await billing.applyCheckoutCompleted(
      {
        id: "cs_over_budget",
        payment_status: "paid",
        customer: "cus_over",
        metadata: { user_id: budgetUser.id, sku: "single_watch", billable_id: "bill_over" },
        client_reference_id: budgetUser.id,
      },
      helpers
    );
  } catch (err) {
    overErr = err;
  }
  assert.ok(overErr);
  assert.strictEqual(overErr.code, "watch_budget");
  assert.strictEqual(writes.filter((w) => w.billable_id === "bill_over").length, 0);
  assert.ok(await store.getCheckout("cs_over_budget"));
  const overCount = await store.getById(budgetUser.id);
  assert.notStrictEqual(overCount.single_watch_count, 1);

  const overWh = await billing.handleWebhook(
    {
      body: JSON.stringify({
        id: "evt_over_budget",
        type: "checkout.session.completed",
        data: {
          object: {
            id: "cs_over_budget",
            payment_status: "paid",
            customer: "cus_over",
            metadata: { user_id: budgetUser.id, sku: "single_watch", billable_id: "bill_over" },
            client_reference_id: budgetUser.id,
          },
        },
      }),
      headers: { "stripe-signature": "sig_ok" },
    },
    helpers
  );
  assert.strictEqual(overWh.statusCode, 500);
  assert.strictEqual(writes.filter((w) => w.billable_id === "bill_over").length, 0);
  assert.strictEqual(await store.isNonceUsed("stripe_event:evt_over_budget"), false);

  stripe.checkout.sessions.retrieve = async () => ({
    id: "cs_over_budget",
    payment_status: "paid",
    status: "complete",
    customer: "cus_over",
    metadata: { user_id: budgetUser.id, sku: "single_watch", billable_id: "bill_over" },
    client_reference_id: budgetUser.id,
  });
  const syncOver = await billing.syncSession(budgetUser, "cs_over_budget", helpers);
  assert.strictEqual(syncOver.ok, false);
  assert.strictEqual(syncOver.status, 503);
  assert.strictEqual(syncOver.code, "watch_budget");

  writes.length = writesBeforeOver;
  process.env.CONSUMER_ACTIVE_WATCH_BUDGET = "40";
  await store.putCheckout("cs_under_budget", {
    user_id: budgetUser.id,
    sku: "single_watch",
    billable_id: "bill_under",
    watch: { facility_id: "x", dates: ["2099-09-03"], party_size: 2, meal_periods: ["DINNER"] },
  });
  await billing.applyCheckoutCompleted(
    {
      id: "cs_under_budget",
      payment_status: "paid",
      customer: "cus_under",
      metadata: { user_id: budgetUser.id, sku: "single_watch", billable_id: "bill_under" },
      client_reference_id: budgetUser.id,
    },
    helpers
  );
  assert.ok(writes.some((w) => w.billable_id === "bill_under"));
  delete process.env.CONSUMER_ACTIVE_WATCH_BUDGET;

  const validCoupon = {
    id: "creator-eeccalisa-planner",
    valid: true,
    max_redemptions: 1,
    times_redeemed: 0,
  };
  stripe.coupons = {
    retrieve: async () => validCoupon,
  };
  stripe.created.length = 0;
  const creatorUser = await store.upsertByEmail("creator@example.com");
  const creatorOk = await billing.createCreatorCompCheckout({
    user: creatorUser,
    promoCode: "EECCALISA",
    billableId: "bill_creator",
  });
  assert.strictEqual(creatorOk.ok, true);
  const creatorArgs = stripe.created[0];
  assert.strictEqual(creatorArgs.mode, "subscription");
  assert.deepStrictEqual(creatorArgs.line_items, [{ price: "price_planner", quantity: 1 }]);
  assert.deepStrictEqual(creatorArgs.discounts, [{ coupon: "creator-eeccalisa-planner" }]);
  assert.strictEqual(creatorArgs.payment_method_collection, "if_required");
  assert.ok(!Object.prototype.hasOwnProperty.call(creatorArgs, "allow_promotion_codes"));
  assert.strictEqual(creatorArgs.metadata.user_id, creatorUser.id);
  assert.strictEqual(creatorArgs.metadata.sku, "planner");
  assert.strictEqual(creatorArgs.metadata.promo_code, "eeccalisa");
  assert.strictEqual(creatorArgs.metadata.creator_comp, "true");
  assert.strictEqual(creatorArgs.metadata.watch_cap, "10");
  assert.strictEqual(creatorArgs.metadata.billable_id, "bill_creator");
  assert.strictEqual(creatorArgs.subscription_data.metadata.user_id, creatorUser.id);
  assert.strictEqual(creatorArgs.subscription_data.metadata.promo_code, "eeccalisa");
  assert.strictEqual(creatorArgs.subscription_data.metadata.creator_comp, "true");
  assert.strictEqual(creatorArgs.subscription_data.metadata.watch_cap, "10");
  assert.ok(!Object.prototype.hasOwnProperty.call(creatorArgs.subscription_data.metadata, "billable_id"));
  assert.strictEqual(typeof billing.createCreatorCompCheckout, "function");
  assert.strictEqual(billing.createCreatorCompCheckout.length, 1);

  const reservedCreator = await billing.createCreatorCompCheckout({
    user: { id: "craig", kind: "internal" },
    promoCode: "eeccalisa",
  });
  assert.strictEqual(reservedCreator.ok, false);
  assert.strictEqual(reservedCreator.status, 403);
  assert.strictEqual(reservedCreator.code, "internal_no_stripe");
  assert.ok(!reservedCreator.fallback);

  stripe.coupons = {
    retrieve: async () => ({ id: "creator-eeccalisa-planner", valid: false }),
  };
  stripe.created.length = 0;
  const invalidCoupon = await billing.createCreatorCompCheckout({
    user: creatorUser,
    promoCode: "eeccalisa",
  });
  assert.strictEqual(invalidCoupon.ok, false);
  assert.strictEqual(invalidCoupon.fallback, true);
  assert.strictEqual(stripe.created.length, 0);

  stripe.coupons = {
    retrieve: async () => ({
      id: "creator-eeccalisa-planner",
      valid: true,
      max_redemptions: 1,
      times_redeemed: 1,
    }),
  };
  const exhausted = await billing.createCreatorCompCheckout({
    user: creatorUser,
    promoCode: "eeccalisa",
  });
  assert.strictEqual(exhausted.ok, false);
  assert.strictEqual(exhausted.fallback, true);
  assert.strictEqual(stripe.created.length, 0);

  stripe.coupons = {
    retrieve: async () => {
      throw new Error("retrieve failed");
    },
  };
  const retrieveThrew = await billing.createCreatorCompCheckout({
    user: creatorUser,
    promoCode: "eeccalisa",
  });
  assert.strictEqual(retrieveThrew.ok, false);
  assert.strictEqual(retrieveThrew.fallback, true);
  assert.strictEqual(stripe.created.length, 0);

  delete stripe.coupons;
  const missingRetrieve = await billing.createCreatorCompCheckout({
    user: creatorUser,
    promoCode: "eeccalisa",
  });
  assert.strictEqual(missingRetrieve.ok, false);
  assert.strictEqual(missingRetrieve.fallback, true);
  assert.strictEqual(stripe.created.length, 0);

  stripe.coupons = { retrieve: async () => validCoupon };
  const originalCreatorCreate = stripe.checkout.sessions.create;
  stripe.checkout.sessions.create = async (sessionArgs) => {
    stripe.created.push(sessionArgs);
    throw new Error("This coupon does not apply");
  };
  stripe.created.length = 0;
  const couponRejected = await billing.createCreatorCompCheckout({
    user: creatorUser,
    promoCode: "eeccalisa",
  });
  assert.strictEqual(couponRejected.ok, false);
  assert.strictEqual(couponRejected.fallback, true);

  stripe.checkout.sessions.create = async (sessionArgs) => {
    stripe.created.push(sessionArgs);
    throw new Error("socket hang up");
  };
  let creatorNetwork = null;
  try {
    await billing.createCreatorCompCheckout({
      user: creatorUser,
      promoCode: "eeccalisa",
    });
  } catch (err) {
    creatorNetwork = err;
  }
  assert.ok(creatorNetwork);
  assert.strictEqual(creatorNetwork.message, "socket hang up");
  stripe.checkout.sessions.create = originalCreatorCreate;

  await store.put({ ...creatorUser, phone: "+15550101010" });
  const creatorFresh = await store.getById(creatorUser.id);
  await store.putCheckout("cs_creator_comp", {
    user_id: creatorFresh.id,
    sku: "planner",
    billable_id: "bill_creator_watch",
    watch: {
      facility_id: "90002686",
      name: "Creator",
      slug: "creator",
      party_size: 2,
      dates: ["2099-10-01"],
      meal_periods: ["DINNER"],
    },
  });
  const writesBeforeCreator = writes.length;
  const countBeforeCreator = Number(creatorFresh.single_watch_count || 0);
  const creatorSession = {
    id: "cs_creator_comp",
    mode: "subscription",
    payment_status: "no_payment_required",
    status: "complete",
    customer: "cus_creator",
    metadata: {
      user_id: creatorFresh.id,
      sku: "planner",
      watch_cap: "10",
      creator_comp: "true",
      billable_id: "bill_creator_watch",
    },
    client_reference_id: creatorFresh.id,
    subscription: { id: "sub_creator", status: "active", current_period_end: 2000000000 },
  };
  await billing.applyCheckoutCompleted(creatorSession, helpers);
  const creatorRows = writes.filter((w) => w.billable_id === "bill_creator_watch");
  assert.strictEqual(creatorRows.length, 1);
  assert.strictEqual(creatorRows[0].recipient_phone, "+15550101010");
  const creatorAfter = await store.getById(creatorFresh.id);
  assert.strictEqual(creatorAfter.planner_status, "active");
  assert.strictEqual(creatorAfter.planner_watch_cap, 10);
  assert.strictEqual(creatorAfter.single_watch_count, countBeforeCreator);
  assert.strictEqual(await store.getCheckout("cs_creator_comp"), null);

  await billing.applyCheckoutCompleted(creatorSession, helpers);
  assert.strictEqual(writes.filter((w) => w.billable_id === "bill_creator_watch").length, 1);
  const creatorRepeat = await store.getById(creatorFresh.id);
  assert.strictEqual(creatorRepeat.single_watch_count, countBeforeCreator);
  assert.strictEqual(writes.length, writesBeforeCreator + 1);

  const paidCreator = await store.upsertByEmail("creator-paid@example.com");
  await store.put({ ...paidCreator, phone: "+15550202020" });
  await store.putCheckout("cs_creator_paid", {
    user_id: paidCreator.id,
    sku: "planner",
    billable_id: "bill_creator_paid",
    watch: { facility_id: "90002686", dates: ["2099-10-02"], party_size: 2, meal_periods: ["DINNER"] },
  });
  await billing.applyCheckoutCompleted(
    {
      id: "cs_creator_paid",
      mode: "subscription",
      payment_status: "paid",
      status: "complete",
      customer: "cus_creator_paid",
      metadata: {
        user_id: paidCreator.id,
        sku: "planner",
        watch_cap: "10",
        creator_comp: "true",
        billable_id: "bill_creator_paid",
      },
      client_reference_id: paidCreator.id,
      subscription: { id: "sub_paid", status: "active" },
    },
    helpers
  );
  assert.ok(writes.some((w) => w.billable_id === "bill_creator_paid"));
  const paidAfter = await store.getById(paidCreator.id);
  assert.strictEqual(paidAfter.planner_watch_cap, 10);
  assert.strictEqual(paidAfter.planner_status, "active");

  const garbageUser = await store.upsertByEmail("garbage-cap@example.com");
  await billing.applyCheckoutCompleted(
    {
      id: "cs_garbage_cap",
      mode: "subscription",
      payment_status: "paid",
      metadata: { user_id: garbageUser.id, sku: "planner", watch_cap: "10abc" },
      client_reference_id: garbageUser.id,
      customer: "cus_garbage",
      subscription: { id: "sub_garbage", status: "active" },
    },
    helpers
  );
  const garbageAfter = await store.getById(garbageUser.id);
  assert.ok(garbageAfter.planner_watch_cap == null || garbageAfter.planner_watch_cap === undefined);

  await store.put({ ...garbageAfter, planner_watch_cap: 10, planner_status: "active" });
  await billing.applyCheckoutCompleted(
    {
      id: "cs_keep_cap",
      mode: "subscription",
      payment_status: "paid",
      metadata: { user_id: garbageUser.id, sku: "planner" },
      client_reference_id: garbageUser.id,
      customer: "cus_garbage",
      subscription: { id: "sub_keep", status: "active" },
    },
    helpers
  );
  const keptCap = await store.getById(garbageUser.id);
  assert.strictEqual(keptCap.planner_watch_cap, 10);

  const stale = {
    id: garbageUser.id,
    email: garbageUser.email,
    planner_status: "active",
    stripe_customer_id: "cus_garbage",
  };
  await billing.applyPlannerFields(stale, { id: "sub_stale", status: "active" }, "cus_garbage");
  const afterStale = await store.getById(garbageUser.id);
  assert.strictEqual(afterStale.planner_watch_cap, 10);

  stripe.subscriptions = {
    list: async () => ({
      data: [{ id: "sub_sync", status: "active", metadata: {} }],
    }),
  };
  await billing.syncSession(stale, null, helpers);
  const afterSync = await store.getById(garbageUser.id);
  assert.strictEqual(afterSync.planner_watch_cap, 10);

  const capFailUser = await store.upsertByEmail("cap-fail@example.com");
  await store.put({
    ...capFailUser,
    planner_status: "active",
    planner_subscription_id: "sub_cap_fail",
    planner_watch_cap: 10,
    stripe_customer_id: "cus_cap_fail",
  });
  const capFailBody = JSON.stringify({
    id: "evt_cap_fail",
    type: "invoice.payment_failed",
    data: { object: { customer: "cus_cap_fail" } },
  });
  const capFailWh = await billing.handleWebhook(
    { body: capFailBody, headers: { "stripe-signature": "sig_ok" } },
    helpers
  );
  assert.strictEqual(capFailWh.statusCode, 200);
  const capFailed = await store.getById(capFailUser.id);
  assert.strictEqual(capFailed.planner_status, "past_due");
  assert.strictEqual(capFailed.planner_watch_cap, 10);

  console.log("test_stripe_billing ok");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
