#!/usr/bin/env node
const assert = require("assert");

process.env.MTF_USER_STORE = "memory";
process.env.MAGIC_LINK_SECRET = "test-secret-key-at-least-32-chars!!";
process.env.WATCH_USERS = JSON.stringify({
  craig: { name: "Craig", password: "craig-secret", phone: "sms:+15550001" },
  Jessica: { name: "Jessica", password: "jess-secret", phone: "sms:+15550002" },
});
process.env.API_SECRET = "legacy-secret";
process.env.URL = "https://magictablefinder.com";
delete process.env.GITHUB_GIST_ID;
delete process.env.GITHUB_TOKEN;
delete process.env.RESEND_API_KEY;

const store = require("../netlify/functions/user_store");
store.resetMemoryStore();
const sessionAuth = require("../netlify/functions/session_auth");
const { handler, _test } = require("../netlify/functions/api");

assert.ok(_test.PUBLIC_PATHS.has("/auth/magic-link"));
assert.ok(_test.PUBLIC_PATHS.has("/auth/callback"));

function ev(method, path, extra = {}) {
  return {
    httpMethod: method,
    path,
    headers: extra.headers || {},
    body: extra.body ? JSON.stringify(extra.body) : extra.rawBody || "",
    queryStringParameters: extra.query || {},
  };
}

function parse(res) {
  let body = res.body;
  try {
    body = res.body ? JSON.parse(res.body) : null;
  } catch {
    body = res.body;
  }
  return { status: res.statusCode, body, headers: res.headers || {}, multi: res.multiValueHeaders || {} };
}

function cookieHeaderFrom(res) {
  const many = (res.multi && res.multi["Set-Cookie"]) || [];
  const one = res.headers["Set-Cookie"] ? [res.headers["Set-Cookie"]] : [];
  const all = many.length ? many : one;
  return all
    .map((c) => String(c).split(";")[0])
    .filter(Boolean)
    .join("; ");
}

(async function main() {
  const profiles = parse(await handler(ev("GET", "/_api/profiles")));
  assert.strictEqual(profiles.status, 200);
  const ids = profiles.body.profiles.map((p) => p.id);
  assert.ok(ids.includes("craig"));
  assert.ok(ids.includes("Jessica"));

  let captured = [];
  sessionAuth.setMagicLinkSender(async (email, url) => {
    captured.push({ email, url });
  });

  const magic = parse(
    await handler(ev("POST", "/_api/auth/magic-link", { body: { email: "guest@example.com" } }))
  );
  assert.strictEqual(magic.status, 200);
  assert.deepStrictEqual(magic.body, { ok: true });
  assert.strictEqual(captured.length, 1);

  const alwaysOk = parse(
    await handler(ev("POST", "/_api/auth/magic-link", { body: { email: "not-an-email" } }))
  );
  assert.strictEqual(alwaysOk.status, 200);
  assert.deepStrictEqual(alwaysOk.body, { ok: true });

  const token = captured[0].url.split("token=")[1];
  const cb = await handler(
    ev("GET", "/_api/auth/callback", {
      query: { token },
      headers: { "x-forwarded-proto": "https" },
    })
  );
  assert.strictEqual(cb.statusCode, 302);
  assert.strictEqual(cb.headers.Location, "/?signin=ok");
  const parsedCb = parse(cb);
  assert.ok(String(parsedCb.headers["Set-Cookie"] || "").includes("mtf_session="));
  const multiCookies = parsedCb.multi["Set-Cookie"] || [];
  assert.ok(multiCookies.some((c) => String(c).includes("mtf_session=")));
  assert.ok(multiCookies.some((c) => String(c).includes("mtf_ui=1")));
  const cookie = cookieHeaderFrom(parsedCb);
  assert.ok(cookie.includes("mtf_session="));
  assert.ok(cookie.includes("mtf_ui=1"));

  const me = parse(
    await handler(
      ev("GET", "/_api/auth/me", {
        headers: { cookie, "x-forwarded-proto": "https" },
      })
    )
  );
  assert.strictEqual(me.status, 200);
  assert.strictEqual(me.body.user.kind, "consumer");
  assert.strictEqual(me.body.user.can_create_watch, false);
  assert.ok(me.body.user.id.startsWith("u_"));
  assert.notStrictEqual(me.body.user.id, "craig");

  const status = parse(
    await handler(
      ev("GET", "/_api/status", {
        headers: { cookie, "x-forwarded-proto": "https" },
      })
    )
  );
  assert.strictEqual(status.status, 200);
  assert.strictEqual(status.body.profile.id, me.body.user.id);
  assert.strictEqual(status.body.total_watches_count, status.body.watches_count);

  const watches = parse(
    await handler(
      ev("GET", "/_api/watches", {
        headers: { cookie, "x-forwarded-proto": "https" },
      })
    )
  );
  assert.strictEqual(watches.status, 200);
  assert.strictEqual(watches.body.owner_id, me.body.user.id);
  for (const w of watches.body.watches || []) {
    assert.notStrictEqual(w.owner_id, "craig");
    assert.notStrictEqual(w.owner_id, "Jessica");
  }

  const created = parse(
    await handler(
      ev("POST", "/_api/watches", {
        headers: { cookie, "x-forwarded-proto": "https", "content-type": "application/json" },
        body: {
          facility_id: "90002686",
          name: "Test",
          slug: "test",
          party_size: 2,
          dates: ["2099-01-01"],
          meal_periods: ["DINNER"],
        },
      })
    )
  );
  assert.strictEqual(created.status, 402);
  assert.strictEqual(created.body.code, "billing_required");
  assert.strictEqual(created.body.can_create_watch, false);
  assert.ok(String(created.body.detail).includes("Paid watches are next"));

  const reused = await handler(
    ev("GET", "/_api/auth/callback", {
      query: { token },
      headers: { "x-forwarded-proto": "https" },
    })
  );
  assert.strictEqual(reused.statusCode, 302);
  assert.strictEqual(reused.headers.Location, "/?signin=invalid");
  assert.ok(!String((reused.headers && reused.headers["Set-Cookie"]) || "").includes("mtf_session="));

  captured.length = 0;
  await handler(ev("POST", "/_api/auth/magic-link", { body: { email: "rawquery@example.com" } }));
  const rawToken = captured[0].url.split("token=")[1];
  const rawCb = await handler({
    httpMethod: "GET",
    path: "/_api/auth/callback",
    headers: { "x-forwarded-proto": "https" },
    queryStringParameters: {},
    rawQuery: "token=" + rawToken,
  });
  assert.strictEqual(rawCb.statusCode, 302);
  assert.strictEqual(rawCb.headers.Location, "/?signin=ok");

  const apiSrc = require("fs").readFileSync(
    require("path").join(__dirname, "../netlify/functions/api.js"),
    "utf8"
  );
  assert.ok(apiSrc.includes("connectBlobsFromEvent(event)"));
  assert.ok(apiSrc.includes('redirect("/?signin=error")'));

  const origConsume = sessionAuth.consumeMagicToken;
  sessionAuth.consumeMagicToken = async () => {
    throw new Error(
      "The environment has not been configured to use Netlify Blobs. To use it manually, supply the following properties when creating a store: siteID, token"
    );
  };
  try {
    const boom = await handler(
      ev("GET", "/_api/auth/callback", {
        query: { token: "x" },
        headers: { "x-forwarded-proto": "https" },
      })
    );
    assert.strictEqual(boom.statusCode, 302);
    assert.strictEqual(boom.headers.Location, "/?signin=error");
    assert.ok(!String((boom.headers && boom.headers["Set-Cookie"]) || "").includes("mtf_session="));
    assert.ok(!String(boom.body || "").includes("siteID"));
  } finally {
    sessionAuth.consumeMagicToken = origConsume;
  }

  const origConnect = store.connectBlobsFromEvent;
  store.connectBlobsFromEvent = () => {
    throw new Error(
      "The environment has not been configured to use Netlify Blobs. To use it manually, supply the following properties when creating a store: siteID, token"
    );
  };
  try {
    const connectBoom = await handler(
      ev("GET", "/_api/auth/callback", {
        query: { token: "x" },
        headers: { "x-forwarded-proto": "https" },
      })
    );
    assert.strictEqual(connectBoom.statusCode, 302);
    assert.strictEqual(connectBoom.headers.Location, "/?signin=error");
    assert.ok(!String(connectBoom.body || "").includes("siteID"));
  } finally {
    store.connectBlobsFromEvent = origConnect;
  }

  const bad = await handler(
    ev("GET", "/_api/auth/callback", {
      query: { token: "nope" },
      headers: { "x-forwarded-proto": "https" },
    })
  );
  assert.strictEqual(bad.headers.Location, "/?signin=invalid");

  const unauth = parse(await handler(ev("GET", "/_api/status")));
  assert.strictEqual(unauth.status, 401);

  const emptySecret = parse(
    await handler(
      ev("GET", "/_api/status", {
        headers: { "x-user-id": "craig", "x-api-secret": "" },
      })
    )
  );
  assert.strictEqual(emptySecret.status, 401);

  const internal = parse(
    await handler(
      ev("GET", "/_api/status", {
        headers: { "X-User-Id": "craig", "X-API-Secret": "craig-secret" },
      })
    )
  );
  assert.strictEqual(internal.status, 200);
  assert.strictEqual(internal.body.profile.id, "craig");

  const internalMe = parse(
    await handler(
      ev("GET", "/_api/auth/me", {
        headers: { "X-User-Id": "Jessica", "X-API-Secret": "jess-secret" },
      })
    )
  );
  assert.strictEqual(internalMe.status, 200);
  assert.strictEqual(internalMe.body.user.kind, "internal");
  assert.strictEqual(internalMe.body.user.can_create_watch, true);

  const internalPost = parse(
    await handler(
      ev("POST", "/_api/watches", {
        headers: { "X-User-Id": "craig", "X-API-Secret": "craig-secret" },
        body: {
          facility_id: "90002686",
          name: "Test",
          slug: "test",
          party_size: 2,
          dates: ["2099-01-01"],
          meal_periods: ["DINNER"],
        },
      })
    )
  );
  assert.notStrictEqual(internalPost.status, 402);
  assert.ok(internalPost.status === 201 || internalPost.status === 500);

  const patchConsumer = parse(
    await handler(
      ev("PATCH", "/_api/me", {
        headers: { cookie, "content-type": "application/json" },
        body: { phone: "+15551234567" },
      })
    )
  );
  assert.strictEqual(patchConsumer.status, 200);
  assert.strictEqual(patchConsumer.body.user.has_phone, true);

  const patchInternal = parse(
    await handler(
      ev("PATCH", "/_api/me", {
        headers: { "X-User-Id": "craig", "X-API-Secret": "craig-secret" },
        body: { phone: "+1555" },
      })
    )
  );
  assert.strictEqual(patchInternal.status, 403);

  const logout = await handler(
    ev("POST", "/_api/auth/logout", { headers: { cookie, "x-forwarded-proto": "https" } })
  );
  assert.strictEqual(logout.statusCode, 204);

  console.log("test_consumer_auth_api ok");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
