#!/usr/bin/env node
const assert = require("assert");
const {
  isInternalUser,
  canCreateWatch,
  publicIdentity,
  plannerCap,
  PAST_DUE_DETAIL,
  CANCELING_DETAIL,
  PLANNER_CAP_DETAIL,
} = require("../netlify/functions/entitlement");

const internal = { id: "craig", name: "Craig", kind: "internal", password: "x" };
const jessica = { id: "Jessica", name: "Jessica", kind: "internal" };
const consumer = {
  id: "u_abc",
  email: "guest@example.com",
  kind: "consumer",
  planner_status: "none",
};

process.env.WATCH_USERS = JSON.stringify({
  craig: { name: "Craig", password: "x" },
  Jessica: { name: "Jessica", password: "y" },
});

assert.strictEqual(isInternalUser({ id: "craig" }), true);
assert.strictEqual(isInternalUser({ id: "Jessica" }), true);
assert.strictEqual(isInternalUser(internal), true);
assert.strictEqual(isInternalUser(jessica), true);
assert.strictEqual(isInternalUser(consumer), false);
assert.strictEqual(isInternalUser(null), false);
assert.strictEqual(isInternalUser({ id: "craig", kind: "consumer" }), false);

const ok = canCreateWatch(internal);
assert.strictEqual(ok.ok, true);
assert.strictEqual(ok.code, "internal");
assert.strictEqual(canCreateWatch(jessica).ok, true);

const single = canCreateWatch(consumer);
assert.strictEqual(single.ok, true);
assert.strictEqual(single.code, "single_watch");

assert.strictEqual(plannerCap(), 4);

const planner = { ...consumer, planner_status: "active" };
assert.strictEqual(canCreateWatch(planner, { activeBillableCount: 1 }).code, "planner");
assert.strictEqual(canCreateWatch(planner, { activeBillableCount: 1 }).ok, true);
assert.strictEqual(canCreateWatch(planner).code, "planner_cap");
assert.strictEqual(canCreateWatch(planner, { activeBillableCount: plannerCap() }).code, "planner_cap");
assert.strictEqual(canCreateWatch(planner, { activeBillableCount: plannerCap() }).detail, PLANNER_CAP_DETAIL);

const trialing = { ...consumer, planner_status: "trialing" };
assert.strictEqual(canCreateWatch(trialing, { activeBillableCount: 0 }).code, "planner");

const pastDue = { ...consumer, planner_status: "past_due" };
const blockedDue = canCreateWatch(pastDue);
assert.strictEqual(blockedDue.ok, false);
assert.strictEqual(blockedDue.code, "past_due");
assert.strictEqual(blockedDue.detail, PAST_DUE_DETAIL);

const canceling = { ...consumer, planner_status: "active", cancel_at_period_end: true };
const blockedCancel = canCreateWatch(canceling, { activeBillableCount: 0 });
assert.strictEqual(blockedCancel.ok, false);
assert.strictEqual(blockedCancel.code, "canceling");
assert.strictEqual(blockedCancel.detail, CANCELING_DETAIL);

const pub = publicIdentity(consumer, { stripeConfigured: true });
assert.strictEqual(pub.can_create_watch, true);
assert.strictEqual(pub.kind, "consumer");
assert.strictEqual(pub.billing_mode, "single_watch");
assert.strictEqual(pub.upgrade_prompt, false);

const blockedStripe = publicIdentity(consumer, { stripeConfigured: false });
assert.strictEqual(blockedStripe.can_create_watch, false);
assert.strictEqual(blockedStripe.billing_mode, "blocked");
assert.strictEqual(blockedStripe.billing_code, "billing_unavailable");

assert.strictEqual(publicIdentity(internal).can_create_watch, true);
assert.strictEqual(publicIdentity(internal).billing_mode, "internal");

const upgradeUser = publicIdentity(
  { ...consumer, single_watch_count: 2 },
  { stripeConfigured: true }
);
assert.strictEqual(upgradeUser.upgrade_prompt, true);
assert.strictEqual(
  publicIdentity({ ...consumer, single_watch_count: 2, planner_status: "active" }, { activeBillableCount: 0 }).upgrade_prompt,
  false
);

console.log("test_entitlement ok");
