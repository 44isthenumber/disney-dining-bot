/** Watch-creation entitlement. Slice 3: internal free; Planner in-app; else Single Watch Checkout. */

const BILLING_REQUIRED_DETAIL =
  "Paid watches are next. You can browse restaurants now.";
const BILLING_UNAVAILABLE_DETAIL = "Paid watches are not available yet.";
const PAST_DUE_DETAIL =
  "Update billing to add watches. Existing watches keep alerting.";
const CANCELING_DETAIL =
  "Your Planner stays active until the period ends. You can't add watches.";
const PLANNER_CAP_DETAIL = "You're at this month's watch limit.";
const WATCH_BUDGET_DETAIL =
  "We're at capacity for new watches right now. Existing watches keep alerting. Try again later.";
const WATCH_STORE_UNAVAILABLE_DETAIL =
  "We couldn't start this watch just now. Try again in a minute.";
const DEFAULT_CONSUMER_WATCH_BUDGET = 40;

class WatchBudgetError extends Error {
  constructor(message) {
    super(message || WATCH_BUDGET_DETAIL);
    this.name = "WatchBudgetError";
    this.code = "watch_budget";
    this.status = 503;
    this.detail = message || WATCH_BUDGET_DETAIL;
  }
}

function watchUserIds() {
  const raw = process.env.WATCH_USERS || process.env.DISNEY_USERS || "";
  if (!raw.trim()) return new Set();
  try {
    return new Set(Object.keys(JSON.parse(raw)));
  } catch {
    return new Set();
  }
}

function isInternalUser(user) {
  if (!user || !user.id) return false;
  if (user.kind === "consumer") return false;
  if (user.kind === "internal") return true;
  return watchUserIds().has(user.id);
}

function plannerCap() {
  const n = parseInt(process.env.PLANNER_WATCH_CAP || "4", 10);
  return Number.isFinite(n) && n > 0 ? n : 4;
}

function consumerWatchBudget() {
  const n = parseInt(process.env.CONSUMER_ACTIVE_WATCH_BUDGET || String(DEFAULT_CONSUMER_WATCH_BUDGET), 10);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_CONSUMER_WATCH_BUDGET;
}

function defaultOwnerId() {
  return String(process.env.DEFAULT_OWNER_ID || "craig").trim() || "craig";
}

function todayIsoInParkTime() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function isActiveWatchRow(watch, today = todayIsoInParkTime()) {
  return typeof watch.date === "string" && watch.date >= today;
}

function isInternalOwnerId(ownerId) {
  const resolved = String(ownerId || "").trim() || defaultOwnerId();
  const lower = resolved.toLowerCase();
  if (lower === "craig" || lower === "jessica") return true;
  return watchUserIds().has(resolved);
}

function countActiveConsumerWatchRows(watches, today = todayIsoInParkTime()) {
  let n = 0;
  for (const w of watches || []) {
    if (!isActiveWatchRow(w, today)) continue;
    const owner = String(w.owner_id || "").trim() || defaultOwnerId();
    if (isInternalOwnerId(owner)) continue;
    n += 1;
  }
  return n;
}

function livePlanner(user) {
  const status = (user && user.planner_status) || "none";
  return status === "active" || status === "trialing";
}

function stripeSingleConfigured() {
  try {
    return require("./stripe_billing").isConfigured("single_watch");
  } catch {
    return false;
  }
}

function canCreateWatch(user, opts = {}) {
  if (!user) {
    return {
      ok: false,
      code: "auth",
      status: 401,
      detail: "Please sign in.",
    };
  }
  if (isInternalUser(user)) {
    return { ok: true, code: "internal" };
  }

  const status = user.planner_status || "none";
  if (status === "past_due") {
    return {
      ok: false,
      code: "past_due",
      status: 402,
      detail: PAST_DUE_DETAIL,
    };
  }
  if (livePlanner(user) && user.cancel_at_period_end) {
    return {
      ok: false,
      code: "canceling",
      status: 402,
      detail: CANCELING_DETAIL,
    };
  }
  if (livePlanner(user)) {
    if (opts.activeBillableCount == null || opts.activeBillableCount >= plannerCap()) {
      return {
        ok: false,
        code: "planner_cap",
        status: 402,
        detail: PLANNER_CAP_DETAIL,
      };
    }
    return finishConsumerCreate(user, "planner", opts);
  }
  return finishConsumerCreate(user, "single_watch", opts);
}

function finishConsumerCreate(user, code, opts) {
  const current =
    opts.consumerActiveWatchCount == null ? 0 : Number(opts.consumerActiveWatchCount);
  const incoming = opts.incomingWatchCount == null ? 0 : Number(opts.incomingWatchCount);
  const budget = consumerWatchBudget();
  if (
    !Number.isFinite(current) ||
    !Number.isFinite(incoming) ||
    current >= budget ||
    current + incoming > budget
  ) {
    return {
      ok: false,
      code: "watch_budget",
      status: 503,
      detail: WATCH_BUDGET_DETAIL,
    };
  }
  return { ok: true, code };
}

function publicIdentity(user, opts = {}) {
  if (!user) return null;
  const gate = canCreateWatch(user, opts);
  let billing_mode = "blocked";
  if (isInternalUser(user)) billing_mode = "internal";
  else if (gate.ok && gate.code === "planner") billing_mode = "planner";
  else if (gate.ok && gate.code === "single_watch") billing_mode = "single_watch";

  let can = Boolean(gate.ok);
  let code = gate.ok ? null : gate.code;
  const stripeOk =
    opts.stripeConfigured != null ? opts.stripeConfigured : stripeSingleConfigured();
  if (billing_mode === "single_watch" && !stripeOk) {
    can = false;
    billing_mode = "blocked";
    code = "billing_unavailable";
  }
  if (!isInternalUser(user) && opts.storeAvailable === false) {
    can = false;
    billing_mode = "blocked";
    code = "watch_store_unavailable";
  }

  const plannerLive = livePlanner(user);
  return {
    id: user.id,
    email: user.email || "",
    name: user.name || user.email || user.id,
    kind: isInternalUser(user) ? "internal" : "consumer",
    has_phone: Boolean(user.phone),
    can_create_watch: can,
    planner_status: user.planner_status || "none",
    cancel_at_period_end: Boolean(user.cancel_at_period_end),
    has_stripe_customer: Boolean(user.stripe_customer_id),
    billing_mode,
    billing_code: code,
    upgrade_prompt:
      !isInternalUser(user) &&
      !plannerLive &&
      Number(user.single_watch_count || 0) >= 2,
  };
}

module.exports = {
  BILLING_REQUIRED_DETAIL,
  BILLING_UNAVAILABLE_DETAIL,
  PAST_DUE_DETAIL,
  CANCELING_DETAIL,
  PLANNER_CAP_DETAIL,
  WATCH_BUDGET_DETAIL,
  WATCH_STORE_UNAVAILABLE_DETAIL,
  DEFAULT_CONSUMER_WATCH_BUDGET,
  WatchBudgetError,
  isInternalUser,
  isInternalOwnerId,
  canCreateWatch,
  publicIdentity,
  plannerCap,
  consumerWatchBudget,
  countActiveConsumerWatchRows,
  livePlanner,
};
