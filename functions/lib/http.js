/** Shared fetch-based HTTP helper (Node tests + Cloudflare Workers). */

async function httpRequest(method, url, headers, body) {
  const init = { method, headers: { ...headers } };
  if (body != null && method !== "GET" && method !== "HEAD") {
    init.body = Buffer.isBuffer(body) ? body : String(body);
  }
  const res = await fetch(url, init);
  const text = await res.text();
  return { status: res.status, body: text };
}

module.exports = { httpRequest };
