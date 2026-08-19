/**
 * Signup / login / session resolution for Magic Table Finder people-identity.
 */

const crypto = require("crypto");
const { hashPassword, verifyPassword } = require("./password");
const { sessionCookie, clearCookie, sessionFromEvent } = require("./session");
const { normalizeEmail, publicUser } = require("./user-store");

const MIN_PASSWORD_LEN = 8;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const DUMMY_HASH = hashPassword("mtf-dummy-not-a-real-password");

function newUserId() {
  return `user_${crypto.randomBytes(8).toString("hex")}`;
}

function parseBody(event) {
  try {
    return JSON.parse(event.body || "{}");
  } catch {
    return null;
  }
}

function safePhone(value) {
  return String(value || "").trim();
}

async function ensureSeeded(store, env = process.env) {
  const { parseEnvUsers } = require("./user-store");
  await store.seedFromEnvUsers(parseEnvUsers(env));
}

async function handleSignup(event, store, { secret, nowMs, jsonResponse }) {
  if (!secret) {
    return jsonResponse(500, { detail: "Server session is not configured" });
  }
  const body = parseBody(event);
  if (!body) return jsonResponse(400, { detail: "Invalid JSON body" });

  const email = normalizeEmail(body.email);
  const password = String(body.password || "");
  const phone = safePhone(body.phone);
  const name = String(body.name || "").trim() || (email ? email.split("@")[0] : "");
  const smsConsent = body.sms_consent === true;

  const errors = [];
  if (!email || !EMAIL_RE.test(email)) errors.push("Enter a valid email address.");
  if (password.length < MIN_PASSWORD_LEN) errors.push("Password must be at least 8 characters.");
  if (phone.length < 8) errors.push("Enter a mobile number for SMS alerts.");
  if (!smsConsent) errors.push("SMS consent is required to create an account.");
  if (errors.length) return jsonResponse(400, { detail: errors.join(" ") });

  const user = {
    id: newUserId(),
    name,
    email,
    phone,
    password_hash: hashPassword(password),
    sms_consent_at: new Date(nowMs).toISOString(),
    created_at: new Date(nowMs).toISOString(),
    seeded: false,
  };
  const result = await store.createUser(user);
  if (!result.ok && result.reason === "email_taken") {
    return jsonResponse(409, { detail: "Could not create account" });
  }
  if (!result.ok) return jsonResponse(400, { detail: "Could not create account" });

  return jsonResponse(201, { profile: publicUser(result.user) }, {
    "Set-Cookie": sessionCookie(result.user.id, secret, event, nowMs),
  });
}

async function handleLogin(event, store, { secret, nowMs, jsonResponse }) {
  if (!secret) {
    return jsonResponse(500, { detail: "Server session is not configured" });
  }
  const body = parseBody(event);
  if (!body) return jsonResponse(400, { detail: "Invalid JSON body" });
  const identifier = String(body.identifier || body.email || "").trim();
  const password = String(body.password || "");
  if (!identifier || !password) {
    return jsonResponse(401, { detail: "Incorrect email or password" });
  }

  const user = await store.findByIdentifier(identifier);
  const ok = verifyPassword(password, user ? user.password_hash : DUMMY_HASH);
  if (!user || !ok) {
    return jsonResponse(401, { detail: "Incorrect email or password" });
  }

  return jsonResponse(200, { profile: publicUser(user) }, {
    "Set-Cookie": sessionCookie(user.id, secret, event, nowMs),
  });
}

function handleLogout(event, { jsonResponse }) {
  return {
    statusCode: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Set-Cookie": clearCookie(event),
    },
    body: "",
  };
}

async function requireUser(event, store, { secret, nowMs, jsonResponse }) {
  const session = sessionFromEvent(event, secret, nowMs);
  if (!session) {
    return { error: jsonResponse(401, { detail: "Sign in required" }) };
  }
  const user = await store.getById(session.uid);
  if (!user) {
    return { error: jsonResponse(401, { detail: "Sign in required" }) };
  }
  return { user };
}

module.exports = {
  MIN_PASSWORD_LEN,
  newUserId,
  ensureSeeded,
  handleSignup,
  handleLogin,
  handleLogout,
  requireUser,
  publicUser,
};
