/**
 * Bridge Cloudflare Pages `onRequest` to the Lambda-shaped handler used in tests.
 */

const userStore = require("./user_store");

function syncEnvFromBindings(env) {
  if (!env || typeof env !== "object") return;
  for (const [key, value] of Object.entries(env)) {
    if (value == null) continue;
    if (typeof value === "string") {
      process.env[key] = value;
    }
  }
}

function syncUrlFromRequest(request) {
  if (process.env.URL) return;
  try {
    process.env.URL = new URL(request.url).origin;
  } catch {
    /* keep existing */
  }
}

async function contextToLambdaEvent(context) {
  const request = context.request;
  const url = new URL(request.url);
  const headers = {};
  request.headers.forEach((value, key) => {
    headers[key] = value;
  });
  let body = "";
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.text();
  }
  const queryStringParameters = {};
  url.searchParams.forEach((value, key) => {
    queryStringParameters[key] = value;
  });
  return {
    httpMethod: request.method,
    path: url.pathname,
    headers,
    body,
    queryStringParameters,
    rawQuery: url.search.replace(/^\?/, ""),
    isBase64Encoded: false,
  };
}

function lambdaResultToResponse(result) {
  const status = result.statusCode || 200;
  const headers = new Headers();
  const plain = result.headers || {};
  for (const [key, value] of Object.entries(plain)) {
    if (value != null) headers.set(key, String(value));
  }
  const multi = result.multiValueHeaders || {};
  for (const [key, values] of Object.entries(multi)) {
    const list = Array.isArray(values) ? values : [values];
    for (const value of list) {
      if (value != null) headers.append(key, String(value));
    }
  }
  const body = result.body == null ? "" : result.body;
  return new Response(body, { status, headers });
}

async function handlePagesRequest(context, handler) {
  syncEnvFromBindings(context.env);
  syncUrlFromRequest(context.request);
  userStore.connectKvFromEnv(context.env);
  const event = await contextToLambdaEvent(context);
  userStore.connectBlobsFromEvent(event);
  const result = await handler(event);
  return lambdaResultToResponse(result);
}

module.exports = {
  syncEnvFromBindings,
  syncUrlFromRequest,
  contextToLambdaEvent,
  lambdaResultToResponse,
  handlePagesRequest,
};
