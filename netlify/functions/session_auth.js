/** HMAC magic-link tokens and session cookies. */

const crypto = require("crypto");
const https = require("https");
const {
  normalizeEmail,
  upsertByEmail,
  claimNonce,
} = require("./user_store");

const MAGIC_TTL_SEC = 900;
const SESSION_TTL_SEC = 30 * 24 * 60 * 60;
const SESSION_COOKIE = "mtf_session";
const UI_COOKIE = "mtf_ui";

let _sender = sendViaResend;

function setMagicLinkSender(fn) {
  _sender = typeof fn === "function" ? fn : sendViaResend;
}

function magicSecret() {
  return String(process.env.MAGIC_LINK_SECRET || "").trim();
}

function b64urlJson(obj) {
  return Buffer.from(JSON.stringify(obj), "utf8").toString("base64url");
}

function signPayload(payloadObj, secret) {
  const payload = b64urlJson(payloadObj);
  const sig = crypto.createHmac("sha256", secret).update(payload).digest();
  return `${payload}.${sig.toString("base64url")}`;
}

function verifySigned(token, secret) {
  if (!token || !secret) return null;
  const parts = String(token).split(".");
  if (parts.length !== 2) return null;
  const [payload, sig] = parts;
  let got;
  try {
    got = Buffer.from(sig, "base64url");
  } catch {
    return null;
  }
  const expected = crypto.createHmac("sha256", secret).update(payload).digest();
  if (got.length !== expected.length || !crypto.timingSafeEqual(got, expected)) {
    return null;
  }
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (!data.exp || Date.now() / 1000 > Number(data.exp)) return null;
    return data;
  } catch {
    return null;
  }
}

function isValidEmail(email) {
  const normalized = normalizeEmail(email);
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized);
}

function mintMagicToken(email, nowSec = Math.floor(Date.now() / 1000)) {
  const secret = magicSecret();
  if (!secret) return null;
  const nonce = crypto.randomBytes(16).toString("hex");
  const token = signPayload(
    { email: normalizeEmail(email), nonce, exp: nowSec + MAGIC_TTL_SEC },
    secret
  );
  return { token, nonce };
}

function mintSessionToken(userId, nowSec = Math.floor(Date.now() / 1000)) {
  const secret = magicSecret();
  if (!secret || !userId) return null;
  return signPayload({ uid: userId, exp: nowSec + SESSION_TTL_SEC }, secret);
}

function verifyMagicToken(token) {
  const data = verifySigned(token, magicSecret());
  if (!data || !data.email || !data.nonce) return null;
  return data;
}

function verifySessionToken(token) {
  const data = verifySigned(token, magicSecret());
  if (!data || !data.uid) return null;
  return data;
}

function parseCookies(event) {
  const headers = event.headers || {};
  const raw = headers.cookie || headers.Cookie || "";
  const out = {};
  String(raw)
    .split(";")
    .forEach((part) => {
      const i = part.indexOf("=");
      if (i === -1) return;
      const key = part.slice(0, i).trim();
      let val = part.slice(i + 1).trim();
      try {
        val = decodeURIComponent(val);
      } catch {
        /* keep raw */
      }
      if (key) out[key] = val;
    });
  return out;
}

function isHttps(event) {
  const headers = event.headers || {};
  const proto = String(headers["x-forwarded-proto"] || headers["X-Forwarded-Proto"] || "")
    .split(",")[0]
    .trim();
  return proto === "https";
}

function cookieSuffix(event, maxAge) {
  const parts = [`Path=/`, `SameSite=Lax`, `Max-Age=${maxAge}`];
  if (isHttps(event)) parts.push("Secure");
  return parts.join("; ");
}

function sessionCookieHeader(event, token) {
  return `${SESSION_COOKIE}=${token}; HttpOnly; ${cookieSuffix(event, SESSION_TTL_SEC)}`;
}

function uiCookieHeader(event) {
  return `${UI_COOKIE}=1; ${cookieSuffix(event, SESSION_TTL_SEC)}`;
}

function clearSessionCookieHeader(event) {
  const secure = isHttps(event) ? "; Secure" : "";
  return `${SESSION_COOKIE}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0${secure}`;
}

function clearUiCookieHeader(event) {
  const secure = isHttps(event) ? "; Secure" : "";
  return `${UI_COOKIE}=; Path=/; SameSite=Lax; Max-Age=0${secure}`;
}

function siteUrl() {
  const raw = process.env.URL || process.env.DEPLOY_PRIME_URL || "https://magictablefinder.com";
  return String(raw).replace(/\/$/, "");
}

function magicLinkUrl(token) {
  return `${siteUrl()}/_api/auth/callback?token=${encodeURIComponent(token)}`;
}

function httpJson(method, url, headers, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const opts = {
      hostname: u.hostname,
      path: u.pathname + u.search,
      method,
      headers: { ...headers },
    };
    const buf = body ? Buffer.from(body) : null;
    if (buf) opts.headers["Content-Length"] = buf.length;
    const req = https.request(opts, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () =>
        resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() })
      );
    });
    req.on("error", reject);
    if (buf) req.write(buf);
    req.end();
  });
}

async function sendViaResend(email, url) {
  const key = String(process.env.RESEND_API_KEY || "").trim();
  const from = String(process.env.MAGIC_LINK_FROM || "").trim();
  if (!key || !from) return { sent: false, reason: "missing_resend" };
  const payload = JSON.stringify({
    from,
    to: [email],
    subject: "Sign in to Magic Table Finder",
    text:
      `Sign in to Magic Table Finder:\n${url}\n\n` +
      `This link expires in 15 minutes. If you did not ask for this, you can ignore the email.`,
  });
  await httpJson(
    "POST",
    "https://api.resend.com/emails",
    {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    payload
  );
  return { sent: true };
}

async function requestMagicLink(email) {
  const normalized = normalizeEmail(email);
  if (!isValidEmail(normalized) || !magicSecret()) {
    return { ok: true };
  }
  const minted = mintMagicToken(normalized);
  if (!minted) return { ok: true };
  const url = magicLinkUrl(minted.token);
  try {
    await _sender(normalized, url);
  } catch (err) {
    console.error("magic-link send failed:", err && err.message ? err.message : "send error");
  }
  return { ok: true };
}

async function consumeMagicToken(token) {
  const data = verifyMagicToken(token);
  if (!data) return { ok: false, reason: "invalid" };
  const claimed = await claimNonce(data.nonce);
  if (!claimed) return { ok: false, reason: "reused" };
  const user = await upsertByEmail(data.email);
  const session = mintSessionToken(user.id);
  if (!session) return { ok: false, reason: "invalid" };
  return { ok: true, user, session };
}

async function userFromSessionCookie(event, getById) {
  const cookies = parseCookies(event);
  const token = cookies[SESSION_COOKIE];
  const data = verifySessionToken(token);
  if (!data) return null;
  const user = await getById(data.uid);
  if (!user) return null;
  return { ...user, kind: "consumer" };
}

module.exports = {
  MAGIC_TTL_SEC,
  SESSION_TTL_SEC,
  SESSION_COOKIE,
  UI_COOKIE,
  setMagicLinkSender,
  signPayload,
  verifySigned,
  mintMagicToken,
  mintSessionToken,
  verifyMagicToken,
  verifySessionToken,
  parseCookies,
  isHttps,
  sessionCookieHeader,
  uiCookieHeader,
  clearSessionCookieHeader,
  clearUiCookieHeader,
  siteUrl,
  magicLinkUrl,
  isValidEmail,
  requestMagicLink,
  consumeMagicToken,
  userFromSessionCookie,
};
