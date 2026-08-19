/**
 * HMAC session cookies for Magic Table Finder people-identity.
 * Cookie is httpOnly. Payload is {uid, exp} — not a Disney JWT.
 */

const crypto = require("crypto");

const COOKIE_NAME = "mtf_session";
const DEFAULT_TTL_MS = 30 * 24 * 60 * 60 * 1000;

function resolveSessionSecret(explicit) {
  if (explicit && String(explicit).trim()) return String(explicit).trim();
  const envSecret = (process.env.SESSION_SECRET || "").trim();
  if (envSecret) return envSecret;
  const apiSecret = (process.env.API_SECRET || "").trim();
  if (apiSecret) {
    return crypto.createHash("sha256").update(`mtf-session:${apiSecret}`).digest("hex");
  }
  return "";
}

function signSession(uid, secret, expMs) {
  const payload = Buffer.from(JSON.stringify({ uid: String(uid), exp: expMs }), "utf8").toString("base64url");
  const sig = crypto.createHmac("sha256", secret).update(payload).digest("base64url");
  return `${payload}.${sig}`;
}

function verifySession(token, secret, nowMs) {
  if (!token || !secret) return null;
  const parts = String(token).split(".");
  if (parts.length !== 2) return null;
  const [payload, sig] = parts;
  const expected = crypto.createHmac("sha256", secret).update(payload).digest("base64url");
  const sigBuf = Buffer.from(sig);
  const expectedBuf = Buffer.from(expected);
  if (sigBuf.length !== expectedBuf.length) return null;
  if (!crypto.timingSafeEqual(sigBuf, expectedBuf)) return null;
  let data;
  try {
    data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
  } catch {
    return null;
  }
  if (!data || typeof data.uid !== "string" || !data.uid) return null;
  if (typeof data.exp !== "number" || data.exp <= nowMs) return null;
  return { uid: data.uid, exp: data.exp };
}

function readCookie(header, name = COOKIE_NAME) {
  if (!header) return "";
  const chunks = String(header).split(";");
  for (const chunk of chunks) {
    const trimmed = chunk.trim();
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    if (trimmed.slice(0, eq) === name) return trimmed.slice(eq + 1);
  }
  return "";
}

function cookieHeader(event) {
  if (!event || !event.headers) return "";
  return event.headers.cookie || event.headers.Cookie || "";
}

function isHttps(event) {
  const proto = (
    (event && event.headers && (event.headers["x-forwarded-proto"] || event.headers["X-Forwarded-Proto"])) ||
    ""
  ).toLowerCase();
  if (proto.split(",")[0].trim() === "https") return true;
  if (process.env.CONTEXT === "production") return true;
  return false;
}

function serializeCookie(value, { maxAgeSec, https }) {
  const parts = [
    `${COOKIE_NAME}=${value}`,
    "HttpOnly",
    "SameSite=Lax",
    "Path=/",
    `Max-Age=${maxAgeSec}`,
  ];
  if (https) parts.push("Secure");
  return parts.join("; ");
}

function sessionCookie(uid, secret, event, nowMs, ttlMs = DEFAULT_TTL_MS) {
  const exp = nowMs + ttlMs;
  const token = signSession(uid, secret, exp);
  return serializeCookie(token, {
    maxAgeSec: Math.floor(ttlMs / 1000),
    https: isHttps(event),
  });
}

function clearCookie(event) {
  return serializeCookie("", { maxAgeSec: 0, https: isHttps(event) });
}

function sessionFromEvent(event, secret, nowMs) {
  const token = readCookie(cookieHeader(event));
  return verifySession(token, secret, nowMs);
}

module.exports = {
  COOKIE_NAME,
  DEFAULT_TTL_MS,
  resolveSessionSecret,
  signSession,
  verifySession,
  readCookie,
  cookieHeader,
  isHttps,
  serializeCookie,
  sessionCookie,
  clearCookie,
  sessionFromEvent,
};
