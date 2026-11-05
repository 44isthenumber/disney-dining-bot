#!/usr/bin/env node
const assert = require("assert");

process.env.MTF_USER_STORE = "memory";
const store = require("../functions/lib/user_store");

function memoryKv() {
  const data = new Map();
  return {
    async get(key) {
      const v = data.get(key);
      return v === undefined ? null : v;
    },
    async put(key, value) {
      data.set(key, value);
    },
  };
}

(async function main() {
  store.clearBackendForTests();
  delete process.env.MTF_USER_STORE;
  const kv = memoryKv();
  store.setKvBindingForTests(kv);
  const backend = store.getBackend();
  assert.strictEqual(backend.kind, "kv");

  const user = await store.upsertByEmail("kv-test@example.com", { phone: "+15551212" });
  assert.ok(user.id.startsWith("u_"));
  assert.strictEqual(await store.getByEmail("kv-test@example.com").then((u) => u.id), user.id);

  assert.strictEqual(await store.claimNonce("n1"), true);
  assert.strictEqual(await store.claimNonce("n1"), false);

  await store.putCheckout("cs_test_1", { user_id: user.id, sku: "single_watch" });
  const checkout = await store.getCheckout("cs_test_1");
  assert.strictEqual(checkout.user_id, user.id);
  await store.deleteCheckout("cs_test_1");
  assert.strictEqual(await store.getCheckout("cs_test_1"), null);

  console.log("test_kv_storage ok");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
