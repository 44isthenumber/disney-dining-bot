/** Watch-creation entitlement. Slice 2: internal WATCH_USERS only; consumers wait for Stripe. */

const BILLING_REQUIRED_DETAIL =
  "Paid watches are next. You can browse restaurants now.";

function isInternalUser(user) {
  if (!user || !user.id) return false;
  if (user.kind === "consumer") return false;
  if (user.kind === "internal") return true;
  return false;
}

function canCreateWatch(user) {
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
  return {
    ok: false,
    code: "billing_required",
    status: 402,
    detail: BILLING_REQUIRED_DETAIL,
  };
}

function publicIdentity(user) {
  if (!user) return null;
  const gate = canCreateWatch(user);
  return {
    id: user.id,
    email: user.email || "",
    name: user.name || user.email || user.id,
    kind: isInternalUser(user) ? "internal" : "consumer",
    has_phone: Boolean(user.phone),
    can_create_watch: Boolean(gate.ok),
  };
}

module.exports = {
  BILLING_REQUIRED_DETAIL,
  isInternalUser,
  canCreateWatch,
  publicIdentity,
};
