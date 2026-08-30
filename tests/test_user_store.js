#!/usr/bin/env node
const assert = require("assert");

process.env.MTF_USER_STORE = "memory";

const store = require("../netlify/functions/user_store");
store.resetMemoryStore();

assert.strictEqual(store.normalizeEmail("  A@B.Com "), "a@b.com");
assert.strictEqual(store.isReservedId("craig"), true);
assert.strictEqual(store.isReservedId("Jessica"), true);
assert.strictEqual(store.isReservedId("u_abc"), false);

(async function main() {
  const first = await store.upsertByEmail("Guest@Example.com");
  assert.ok(first.id.startsWith("u_"));
  assert.strictEqual(first.email, "guest@example.com");
  assert.strictEqual(first.kind, "consumer");
  assert.strictEqual(first.planner_status, "none");

  const again = await store.upsertByEmail("guest@example.com");
  assert.strictEqual(again.id, first.id);

  const [r1, r2] = await Promise.all([
    store.upsertByEmail("race@example.com"),
    store.upsertByEmail("RACE@example.com"),
  ]);
  assert.strictEqual(r1.id, r2.id);

  const byId = await store.getById(first.id);
  assert.strictEqual(byId.email, "guest@example.com");

  await assert.rejects(() => store.put({ id: "craig", email: "x@y.z" }), /reserved/i);
  await assert.rejects(() => store.put({ id: "Jessica", email: "x@y.z" }), /reserved/i);

  await store.markNonceUsed("nonce-1");
  assert.strictEqual(await store.isNonceUsed("nonce-1"), true);
  assert.strictEqual(await store.isNonceUsed("nonce-2"), false);

  assert.strictEqual(store.blobWriteCreatedEntry({ modified: true }), true);
  assert.strictEqual(store.blobWriteCreatedEntry({ modified: false }), false);
  assert.strictEqual(store.blobWriteCreatedEntry(undefined), true);

  const fake = new Map();
  const fakeStore = {
    async get(key) { return fake.get(key) || null; },
    async set(key, value, opts = {}) {
      if (opts.onlyIfNew && fake.has(key)) return { modified: false };
      fake.set(key, value);
      return { modified: true };
    },
  };
  assert.strictEqual(store.blobWriteCreatedEntry(await fakeStore.set("used:a", "1", { onlyIfNew: true })), true);
  assert.strictEqual(store.blobWriteCreatedEntry(await fakeStore.set("used:a", "1", { onlyIfNew: true })), false);

  const prevStore = process.env.MTF_USER_STORE;
  let connected = null;
  store.setBlobsModuleForTests({
    connectLambda(ev) {
      connected = ev;
    },
    getStore() {
      throw new Error("getStore should not run in this test");
    },
  });
  try {
    process.env.MTF_USER_STORE = "memory";
    connected = null;
    assert.strictEqual(store.connectBlobsFromEvent({ blobs: { token: "t" } }), false);
    assert.strictEqual(connected, null);

    delete process.env.MTF_USER_STORE;
    assert.strictEqual(store.connectBlobsFromEvent({ blobs: { token: "t" } }), true);
    assert.strictEqual(connected.blobs.token, "t");
    connected = null;
    assert.strictEqual(store.connectBlobsFromEvent({}), false);
    assert.strictEqual(connected, null);

    store.clearBackendForTests();
    store.setBlobFactoryForTests(() => {
      throw new Error("no blobs");
    });
    assert.throws(() => store.getBackend(), /no blobs/);
  } finally {
    store.setBlobsModuleForTests(null);
    store.setBlobFactoryForTests(null);
    process.env.MTF_USER_STORE = prevStore || "memory";
    store.resetMemoryStore();
  }

  await store.put({
    id: first.id,
    email: first.email,
    stripe_customer_id: "cus_mem",
    phone: "+1",
  });
  const byCus = await store.getByStripeCustomerId("cus_mem");
  assert.strictEqual(byCus.id, first.id);
  await store.putCheckout("cs_mem", { user_id: first.id, billable_id: "bill_1" });
  const pending = await store.getCheckout("cs_mem");
  assert.strictEqual(pending.billable_id, "bill_1");
  await store.deleteCheckout("cs_mem");
  assert.strictEqual(await store.getCheckout("cs_mem"), null);

  console.log("test_user_store ok");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
