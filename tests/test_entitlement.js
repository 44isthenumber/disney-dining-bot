#!/usr/bin/env node
const assert = require("assert");
const {
  isInternalUser,
  isInternalOwnerId,
  canCreateWatch,
  publicIdentity,
  plannerCap,
  consumerWatchBudget,
  countActiveConsumerWatchRows,
  PAST_DUE_DETAIL,
  CANCELING_DETAIL,
  PLANNER_CAP_DETAIL,
  WATCH_BUDGET_DETAIL,
  DEFAULT_CONSUMER_WATCH_BUDGET,
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

assert.strictEqual(consumerWatchBudget(), DEFAULT_CONSUMER_WATCH_BUDGET);
assert.strictEqual(DEFAULT_CONSUMER_WATCH_BUDGET, 40);
process.env.CONSUMER_ACTIVE_WATCH_BUDGET = "20";
assert.strictEqual(consumerWatchBudget(), 20);
process.env.CONSUMER_ACTIVE_WATCH_BUDGET = "0";
assert.strictEqual(consumerWatchBudget(), 40);
process.env.CONSUMER_ACTIVE_WATCH_BUDGET = "20x";
assert.strictEqual(consumerWatchBudget(), 40);
process.env.CONSUMER_ACTIVE_WATCH_BUDGET = "1.5";
assert.strictEqual(consumerWatchBudget(), 40);
process.env.CONSUMER_ACTIVE_WATCH_BUDGET = "-5";
assert.strictEqual(consumerWatchBudget(), 40);
delete process.env.CONSUMER_ACTIVE_WATCH_BUDGET;

assert.strictEqual(isInternalOwnerId("craig"), true);
assert.strictEqual(isInternalOwnerId("CRAIG"), true);
assert.strictEqual(isInternalOwnerId("Jessica"), true);
assert.strictEqual(isInternalOwnerId(""), true);
assert.strictEqual(isInternalOwnerId("u_abc"), false);

const today = "2026-09-10";
const counted = countActiveConsumerWatchRows(
  [
    { owner_id: "u_1", date: "2026-09-11" },
    { owner_id: "u_1", date: "2026-09-12" },
    { owner_id: "craig", date: "2026-09-20" },
    { owner_id: "Jessica", date: "2026-09-20" },
    { owner_id: "u_2", date: "2026-09-01" },
    { date: "2026-09-20" },
  ],
  today
);
assert.strictEqual(counted, 2);

process.env.CONSUMER_ACTIVE_WATCH_BUDGET = "40";
assert.strictEqual(canCreateWatch(consumer, { consumerActiveWatchCount: 39, incomingWatchCount: 1 }).ok, true);
assert.strictEqual(canCreateWatch(consumer, { consumerActiveWatchCount: 39, incomingWatchCount: 1 }).code, "single_watch");
const over = canCreateWatch(consumer, { consumerActiveWatchCount: 40, incomingWatchCount: 1 });
assert.strictEqual(over.ok, false);
assert.strictEqual(over.code, "watch_budget");
assert.strictEqual(over.status, 503);
assert.strictEqual(over.detail, WATCH_BUDGET_DETAIL);
assert.strictEqual(canCreateWatch(consumer, { consumerActiveWatchCount: 40 }).code, "watch_budget");
assert.strictEqual(canCreateWatch(internal, { consumerActiveWatchCount: 999, incomingWatchCount: 50 }).ok, true);
assert.strictEqual(
  canCreateWatch({ ...consumer, planner_status: "active" }, { activeBillableCount: 1, consumerActiveWatchCount: 40, incomingWatchCount: 1 }).code,
  "watch_budget"
);
const atCapId = publicIdentity(consumer, { stripeConfigured: true, consumerActiveWatchCount: 40 });
assert.strictEqual(atCapId.can_create_watch, false);
assert.strictEqual(atCapId.billing_mode, "blocked");
assert.strictEqual(atCapId.billing_code, "watch_budget");
const storeDown = publicIdentity(consumer, { stripeConfigured: true, storeAvailable: false });
assert.strictEqual(storeDown.can_create_watch, false);
assert.strictEqual(storeDown.billing_code, "watch_store_unavailable");
assert.strictEqual(publicIdentity(internal, { storeAvailable: false }).can_create_watch, true);
delete process.env.CONSUMER_ACTIVE_WATCH_BUDGET;

console.log("test_entitlement ok");
