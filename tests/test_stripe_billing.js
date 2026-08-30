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
  return {
    created,
    portal,
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
  assert.strictEqual(subArgs.customer, "cus_1");
  assert.ok(!Object.prototype.hasOwnProperty.call(subArgs, "customer_email"));

  const internal = await billing.createCheckoutSession({
    user: { id: "craig", kind: "internal" },
    sku: "single_watch",
  });
  assert.strictEqual(internal.status, 403);
  assert.strictEqual(internal.code, "internal_no_stripe");

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
  assert.strictEqual(writes.length, 2);

  const repairUser = await store.upsertByEmail("repair@example.com");
  await store.put({ ...repairUser, phone: "+15550000" });
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

  console.log("test_stripe_billing ok");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
