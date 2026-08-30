#!/usr/bin/env node
const assert = require("assert");
const {
  isInternalUser,
  canCreateWatch,
  publicIdentity,
  BILLING_REQUIRED_DETAIL,
} = require("../netlify/functions/entitlement");

const internal = { id: "craig", name: "Craig", kind: "internal", password: "x" };
const jessica = { id: "Jessica", name: "Jessica", kind: "internal" };
const consumer = {
  id: "u_abc",
  email: "guest@example.com",
  kind: "consumer",
  planner_status: "none",
};

assert.strictEqual(isInternalUser(internal), true);
assert.strictEqual(isInternalUser(jessica), true);
assert.strictEqual(isInternalUser(consumer), false);
assert.strictEqual(isInternalUser(null), false);
assert.strictEqual(isInternalUser({ id: "craig", kind: "consumer" }), false);

const ok = canCreateWatch(internal);
assert.strictEqual(ok.ok, true);
assert.strictEqual(ok.code, "internal");
assert.strictEqual(canCreateWatch(jessica).ok, true);

const blocked = canCreateWatch(consumer);
assert.strictEqual(blocked.ok, false);
assert.strictEqual(blocked.code, "billing_required");
assert.strictEqual(blocked.status, 402);
assert.strictEqual(blocked.detail, BILLING_REQUIRED_DETAIL);

const pub = publicIdentity(consumer);
assert.strictEqual(pub.can_create_watch, false);
assert.strictEqual(pub.kind, "consumer");
assert.strictEqual(publicIdentity(internal).can_create_watch, true);

console.log("test_entitlement ok");
