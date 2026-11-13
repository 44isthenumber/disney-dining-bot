#!/usr/bin/env node
const assert = require("assert");

process.env.MTF_USER_STORE = "memory";
const { handler, _test } = require("../functions/lib/api");
const { contextToLambdaEvent, lambdaResultToResponse, handlePagesRequest } = require("../functions/lib/cf_adapter");

assert.strictEqual(_test.apiPath({ path: "/_api/status" }), "/status");
assert.strictEqual(_test.apiPath({ path: "/_api/billing/webhook" }), "/billing/webhook");

(async function main() {
  const event = await contextToLambdaEvent({
    request: new Request("https://preview.pages.dev/_api/health?x=1", { method: "GET" }),
  });
  assert.strictEqual(event.httpMethod, "GET");
  assert.strictEqual(event.path, "/_api/health");
  assert.strictEqual(event.queryStringParameters.x, "1");

  const res = await handlePagesRequest(
    {
      request: new Request("https://magictablefinder.com/_api/profiles", { method: "GET" }),
      env: {},
    },
    handler
  );
  assert.strictEqual(res.status, 200);
  const body = JSON.parse(await res.text());
  assert.ok(Array.isArray(body.profiles));

  const lambda = await handler({
    httpMethod: "GET",
    path: "/_api/profiles",
    headers: {},
  });
  const response = lambdaResultToResponse(lambda);
  assert.strictEqual(response.status, 200);

  console.log("test_cf_routing ok");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
