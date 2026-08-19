"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { hashPassword, verifyPassword } = require("../netlify/functions/lib/password");
const { signSession, verifySession, COOKIE_NAME } = require("../netlify/functions/lib/session");
const { createMemoryStore, createUserStore, publicUser } = require("../netlify/functions/lib/user-store");
const { createHandler, normalizeWatch } = require("../netlify/functions/api");

const SECRET = "test-session-secret-not-for-production";
const NOW = Date.parse("2026-08-19T21:00:00.000Z");

const SEED_USERS = {
  craig: { name: "Craig", password: "craig-test-pass", phone: "+15551111111" },
  Jessica: { name: "Jessica", password: "jess-test-pass", phone: "+15552222222" },
};

function seedEnv() {
  process.env.WATCH_USERS = JSON.stringify(SEED_USERS);
  delete process.env.FALLBACK_USERS;
}

function makeApp(overrides = {}) {
  seedEnv();
  const store = overrides.store || createMemoryStore();
  const watchesState = overrides.watchesState || { watches: [] };
  const handler = createHandler({
    store,
    sessionSecret: SECRET,
    now: () => overrides.nowMs || NOW,
    watchesState,
    allowMemory: true,
  });
  return { handler, store, watchesState };
}

function event({ method, path, body, cookie, headers }) {
  return {
    httpMethod: method,
    path: `/_api${path}`,
    body: body == null ? "" : JSON.stringify(body),
    headers: {
      cookie: cookie || "",
      ...(headers || {}),
    },
  };
}

async function invoke(handler, opts) {
  const res = await handler(event(opts), {});
  let json = null;
  if (res.body) {
    try {
      json = JSON.parse(res.body);
    } catch {
      json = null;
    }
  }
  return { ...res, json };
}

function cookieFrom(res) {
  return res.headers && (res.headers["Set-Cookie"] || res.headers["set-cookie"]) || "";
}

function sessionCookie(res) {
  const header = cookieFrom(res);
  const match = String(header).match(new RegExp(`${COOKIE_NAME}=([^;]+)`));
  return match ? `${COOKIE_NAME}=${match[1]}` : "";
}

test("passwords are scrypt hashed and verified", () => {
  const stored = hashPassword("correct-horse");
  assert.match(stored, /^scrypt\$/);
  assert.equal(stored.includes("correct-horse"), false);
  assert.equal(verifyPassword("correct-horse", stored), true);
  assert.equal(verifyPassword("wrong-password", stored), false);
});

test("session tokens expire and reject bad signatures", () => {
  const token = signSession("craig", SECRET, NOW + 1000);
  assert.equal(verifySession(token, SECRET, NOW).uid, "craig");
  assert.equal(verifySession(token, SECRET, NOW + 2000), null);
  assert.equal(verifySession(token + "x", SECRET, NOW), null);
});

test("publicUser never includes phone or password", () => {
  const pub = publicUser({
    id: "craig",
    name: "Craig",
    email: null,
    phone: "+15551111111",
    password_hash: "scrypt$x",
  });
  assert.equal(pub.has_phone, true);
  assert.equal("phone" in pub, false);
  assert.equal("password" in pub, false);
  assert.equal("password_hash" in pub, false);
});

test("signup creates user_* id, httpOnly cookie, and hides phone", async () => {
  const { handler, store } = makeApp();
  const res = await invoke(handler, {
    method: "POST",
    path: "/signup",
    body: {
      email: "sam@example.com",
      password: "longenough",
      phone: "+15553333333",
      name: "Sam",
      sms_consent: true,
    },
  });
  assert.equal(res.statusCode, 201);
  assert.match(res.json.profile.id, /^user_[a-f0-9]{16}$/);
  assert.equal(res.json.profile.has_phone, true);
  assert.equal(res.json.profile.phone, undefined);
  const setCookie = cookieFrom(res);
  assert.match(setCookie, /HttpOnly/);
  assert.match(setCookie, new RegExp(`${COOKIE_NAME}=`));
  const saved = await store.getById(res.json.profile.id);
  assert.match(saved.password_hash, /^scrypt\$/);
  assert.equal(saved.password_hash.includes("longenough"), false);
});

test("signup rejects missing consent, short password, bad email, duplicate email", async () => {
  const { handler } = makeApp();
  const good = {
    email: "sam@example.com",
    password: "longenough",
    phone: "+15553333333",
    sms_consent: true,
  };
  const noConsent = await invoke(handler, { method: "POST", path: "/signup", body: { ...good, sms_consent: false } });
  assert.equal(noConsent.statusCode, 400);
  assert.equal(cookieFrom(noConsent).includes(`${COOKIE_NAME}=`), false);

  const short = await invoke(handler, { method: "POST", path: "/signup", body: { ...good, password: "short" } });
  assert.equal(short.statusCode, 400);

  const badEmail = await invoke(handler, { method: "POST", path: "/signup", body: { ...good, email: "not-an-email" } });
  assert.equal(badEmail.statusCode, 400);

  const first = await invoke(handler, { method: "POST", path: "/signup", body: good });
  assert.equal(first.statusCode, 201);
  const dup = await invoke(handler, { method: "POST", path: "/signup", body: good });
  assert.equal(dup.statusCode, 409);
});

test("login succeeds with email and fails with generic detail", async () => {
  const { handler } = makeApp();
  await invoke(handler, {
    method: "POST",
    path: "/signup",
    body: {
      email: "sam@example.com",
      password: "longenough",
      phone: "+15553333333",
      sms_consent: true,
    },
  });
  const ok = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "sam@example.com", password: "longenough" },
  });
  assert.equal(ok.statusCode, 200);
  assert.match(cookieFrom(ok), /HttpOnly/);

  const bad = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "sam@example.com", password: "nope-nope" },
  });
  assert.equal(bad.statusCode, 401);
  assert.equal(bad.json.detail, "Incorrect email or password");

  const unknown = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "nobody@example.com", password: "longenough" },
  });
  assert.equal(unknown.statusCode, 401);
  assert.equal(unknown.json.detail, "Incorrect email or password");
});

test("WATCH_USERS seeds craig and Jessica without renaming ids", async () => {
  const { handler, store } = makeApp();
  const craig = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "craig", password: "craig-test-pass" },
  });
  assert.equal(craig.statusCode, 200);
  assert.equal(craig.json.profile.id, "craig");

  const jessicaLower = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "jessica", password: "jess-test-pass" },
  });
  assert.equal(jessicaLower.statusCode, 200);
  assert.equal(jessicaLower.json.profile.id, "Jessica");

  const craigRow = await store.getById("craig");
  const jessicaRow = await store.getById("Jessica");
  assert.equal(craigRow.email, "");
  assert.equal(jessicaRow.email, "");
  assert.equal(await store.findByIdentifier(""), null);
});

test("protected routes require a cookie and ignore legacy headers", async () => {
  const { handler } = makeApp();
  const noAuth = await invoke(handler, { method: "GET", path: "/status" });
  assert.equal(noAuth.statusCode, 401);

  const headersOnly = await invoke(handler, {
    method: "GET",
    path: "/status",
    headers: { "X-User-Id": "craig", "X-API-Secret": "craig-test-pass" },
  });
  assert.equal(headersOnly.statusCode, 401);

  const login = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "craig", password: "craig-test-pass" },
  });
  const me = await invoke(handler, { method: "GET", path: "/me", cookie: sessionCookie(login) });
  assert.equal(me.statusCode, 200);
  assert.equal(me.json.profile.id, "craig");
  assert.equal(me.json.profile.phone, undefined);
});

test("watches are owner-scoped and ignore body owner_id / recipient_phone", async () => {
  const existingJessicaWatch = {
    watch_id: "watch_jessica_existing",
    owner_id: "Jessica",
    facility_id: "90002686",
    name: "Existing Jessica Watch",
    slug: "existing",
    party_size: 2,
    meal_periods: ["DINNER"],
    date: "2099-02-02",
    recipient_phone: "+15552222222",
  };
  const { handler, watchesState } = makeApp({
    watchesState: { watches: [existingJessicaWatch] },
  });

  const craigLogin = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "craig", password: "craig-test-pass" },
  });
  const craigCookie = sessionCookie(craigLogin);

  const created = await invoke(handler, {
    method: "POST",
    path: "/watches",
    cookie: craigCookie,
    body: {
      facility_id: "90002686",
      name: "Smoke Test Restaurant",
      slug: "smoke-test-restaurant",
      party_size: 2,
      dates: ["2099-01-01"],
      meal_periods: ["DINNER"],
      owner_id: "Jessica",
      recipient_phone: "+19999999999",
    },
  });
  assert.equal(created.statusCode, 201);
  assert.equal(created.json.added.length, 1);
  const stored = watchesState.watches.find((w) => w.watch_id === created.json.added[0]);
  assert.equal(stored.owner_id, "craig");
  assert.equal(stored.recipient_phone, "+15551111111");

  const craigWatches = await invoke(handler, { method: "GET", path: "/watches", cookie: craigCookie });
  assert.equal(craigWatches.statusCode, 200);
  assert.equal(craigWatches.json.watches.every((w) => w.owner_id === "craig"), true);
  assert.equal(craigWatches.json.watches.some((w) => w.watch_id === "watch_jessica_existing"), false);
  assert.equal(craigWatches.json.watches[0].recipient_phone, undefined);

  const jessicaLogin = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "jessica", password: "jess-test-pass" },
  });
  const jessicaWatches = await invoke(handler, {
    method: "GET",
    path: "/watches",
    cookie: sessionCookie(jessicaLogin),
  });
  assert.equal(jessicaWatches.json.watches.some((w) => w.watch_id === "watch_jessica_existing"), true);
  assert.equal(jessicaWatches.json.watches.some((w) => w.watch_id === created.json.added[0]), false);
});

test("new signup watches use user_* owner_id and signup phone", async () => {
  const { handler, watchesState } = makeApp();
  const signup = await invoke(handler, {
    method: "POST",
    path: "/signup",
    body: {
      email: "sam@example.com",
      password: "longenough",
      phone: "+15553333333",
      sms_consent: true,
    },
  });
  const created = await invoke(handler, {
    method: "POST",
    path: "/watches",
    cookie: sessionCookie(signup),
    body: {
      facility_id: "90002686",
      name: "Smoke Test Restaurant",
      slug: "smoke-test-restaurant",
      party_size: 2,
      dates: ["2099-01-01"],
      meal_periods: ["DINNER"],
    },
  });
  assert.equal(created.statusCode, 201);
  const stored = watchesState.watches.find((w) => w.watch_id === created.json.added[0]);
  assert.equal(stored.owner_id, signup.json.profile.id);
  assert.equal(stored.recipient_phone, "+15553333333");
});

test("watch create is rejected when the account has no phone", async () => {
  const store = createMemoryStore();
  await store.createUser({
    id: "nophone",
    name: "No Phone",
    email: "nophone@example.com",
    phone: "",
    password_hash: hashPassword("longenough"),
    sms_consent_at: null,
    created_at: new Date(NOW).toISOString(),
    seeded: false,
  });
  const { handler } = makeApp({ store });
  const login = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "nophone@example.com", password: "longenough" },
  });
  const created = await invoke(handler, {
    method: "POST",
    path: "/watches",
    cookie: sessionCookie(login),
    body: {
      facility_id: "90002686",
      name: "Smoke Test Restaurant",
      slug: "smoke-test-restaurant",
      party_size: 2,
      dates: ["2099-01-01"],
    },
  });
  assert.equal(created.statusCode, 422);
});

test("GET /profiles is not a public directory", async () => {
  const { handler } = makeApp();
  const res = await invoke(handler, { method: "GET", path: "/profiles" });
  assert.equal(res.statusCode, 404);
  assert.equal(res.json.profiles, undefined);
});

test("production user store refuses silent memory fallback", () => {
  const previous = process.env.MTF_USER_STORE;
  process.env.MTF_USER_STORE = "memory";
  assert.throws(() => createUserStore({ allowMemory: false }), /test-only/);
  delete process.env.MTF_USER_STORE;
  try {
    const store = createUserStore({ allowMemory: false });
    assert.equal(store.kind, "blobs");
  } catch (err) {
    assert.match(String(err.message || err), /Blobs|not available|Netlify/i);
  }
  if (previous === undefined) delete process.env.MTF_USER_STORE;
  else process.env.MTF_USER_STORE = previous;
});

test("normalizeWatch preserves an existing recipient_phone", () => {
  const kept = normalizeWatch({
    owner_id: "user_abc",
    facility_id: "90002686",
    date: "2099-01-01",
    recipient_phone: "+15553333333",
  });
  assert.equal(kept.recipient_phone, "+15553333333");
  const empty = normalizeWatch({
    owner_id: "user_abc",
    facility_id: "90002686",
    date: "2099-01-01",
  });
  assert.equal(empty.recipient_phone, "");
});

test("logout clears the session cookie", async () => {
  const { handler } = makeApp();
  const login = await invoke(handler, {
    method: "POST",
    path: "/login",
    body: { identifier: "craig", password: "craig-test-pass" },
  });
  const out = await invoke(handler, {
    method: "POST",
    path: "/logout",
    cookie: sessionCookie(login),
  });
  assert.equal(out.statusCode, 204);
  assert.match(cookieFrom(out), /Max-Age=0/);
  const me = await invoke(handler, { method: "GET", path: "/me" });
  assert.equal(me.statusCode, 401);
});
