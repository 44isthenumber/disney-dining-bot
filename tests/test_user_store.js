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

  console.log("test_user_store ok");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
