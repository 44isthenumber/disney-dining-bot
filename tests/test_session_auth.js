#!/usr/bin/env node
const assert = require("assert");

process.env.MAGIC_LINK_SECRET = "test-secret-key-at-least-32-chars!!";
process.env.MTF_USER_STORE = "memory";
process.env.URL = "https://magictablefinder.com";

const store = require("../netlify/functions/user_store");
store.resetMemoryStore();

const auth = require("../netlify/functions/session_auth");

assert.strictEqual(auth.isValidEmail("a@b.com"), true);
assert.strictEqual(auth.isValidEmail("nope"), false);

const minted = auth.mintMagicToken("A@B.com");
assert.ok(minted.token.includes("."));
const verified = auth.verifyMagicToken(minted.token);
assert.strictEqual(verified.email, "a@b.com");
assert.strictEqual(verified.nonce, minted.nonce);

const expired = auth.signPayload(
  { email: "a@b.com", nonce: "x", exp: Math.floor(Date.now() / 1000) - 10 },
  process.env.MAGIC_LINK_SECRET
);
assert.strictEqual(auth.verifyMagicToken(expired), null);

const tampered = minted.token.slice(0, -2) + "ab";
assert.strictEqual(auth.verifyMagicToken(tampered), null);

const session = auth.mintSessionToken("u_test");
assert.ok(auth.verifySessionToken(session).uid === "u_test");

const httpsEvent = { headers: { "x-forwarded-proto": "https", cookie: "" } };
const cookie = auth.sessionCookieHeader(httpsEvent, session);
assert.ok(cookie.includes("HttpOnly"));
assert.ok(cookie.includes("Secure"));
assert.ok(cookie.includes("SameSite=Lax"));
assert.ok(auth.uiCookieHeader(httpsEvent).includes("mtf_ui=1"));
assert.ok(!auth.uiCookieHeader(httpsEvent).includes("HttpOnly"));

const httpEvent = { headers: { "x-forwarded-proto": "http" } };
assert.ok(!auth.sessionCookieHeader(httpEvent, session).includes("Secure"));

assert.ok(auth.magicLinkUrl("tok").includes("/_api/auth/callback?token="));
const mail = auth.magicLinkEmailPayload("https://magictablefinder.com/_api/auth/callback?token=abc");
assert.ok(mail.text.includes("https://magictablefinder.com/_api/auth/callback?token=abc"));
assert.ok(mail.html.includes('href="https://magictablefinder.com/_api/auth/callback?token=abc"'));
assert.ok(mail.html.includes("Sign in to Magic Table Finder"));
const sessionAuthSrc = require("fs").readFileSync(
  require("path").join(__dirname, "../netlify/functions/session_auth.js"),
  "utf8"
);
assert.ok(sessionAuthSrc.includes("html: mail.html"));

let sent = [];
auth.setMagicLinkSender(async (email, url) => {
  sent.push({ email, url });
});
(async function main() {
  const result = await auth.requestMagicLink("person@example.com");
  assert.deepStrictEqual(result, { ok: true });
  assert.strictEqual(sent.length, 1);
  assert.strictEqual(sent[0].email, "person@example.com");

  const invalid = await auth.requestMagicLink("not-an-email");
  assert.deepStrictEqual(invalid, { ok: true });
  assert.strictEqual(sent.length, 1);

  const consumed = await auth.consumeMagicToken(sent[0].url.split("token=")[1]);
  assert.strictEqual(consumed.ok, true);
  assert.ok(consumed.user.id.startsWith("u_"));
  const reused = await auth.consumeMagicToken(sent[0].url.split("token=")[1]);
  assert.strictEqual(reused.ok, false);

  const mintedRace = auth.mintMagicToken("race-token@example.com");
  const [c1, c2] = await Promise.all([
    auth.consumeMagicToken(mintedRace.token),
    auth.consumeMagicToken(mintedRace.token),
  ]);
  assert.strictEqual([c1, c2].filter((r) => r.ok).length, 1);
  assert.strictEqual([c1, c2].filter((r) => !r.ok).length, 1);

  const parsed = auth.parseCookies({
    headers: { cookie: `mtf_session=${consumed.session}; mtf_ui=1` },
  });
  assert.strictEqual(parsed.mtf_session, consumed.session);
  assert.strictEqual(minted.token.split(".").length, 2);

  console.log("test_session_auth ok");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
