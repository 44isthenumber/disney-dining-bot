#!/usr/bin/env node
/**
 * Export all Netlify Blobs stores for a site to JSON (for KV import).
 *
 * Usage:
 *   NETLIFY_AUTH_TOKEN=... NETLIFY_SITE_ID=b1f7efc5-da94-4159-ade0-568de33ed24f \
 *     node scripts/export-netlify-blobs.mjs --out ./blob-export.json
 *
 * Does not run automatically during migration — Craig runs once before cutover.
 */

import fs from "node:fs/promises";

const SITE_ID =
  process.env.NETLIFY_SITE_ID || process.env.NETLIFY_SITE_ID_OVERRIDE || "b1f7efc5-da94-4159-ade0-568de33ed24f";
const TOKEN = process.env.NETLIFY_AUTH_TOKEN || "";

function parseArgs(argv) {
  let out = "netlify-blobs-export.json";
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--out" && argv[i + 1]) {
      out = argv[++i];
    }
  }
  return { out };
}

async function netlifyFetch(path, init = {}) {
  const res = await fetch(`https://api.netlify.com${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`Netlify API ${path} failed: ${res.status} ${text.slice(0, 400)}`);
  }
  return text ? JSON.parse(text) : null;
}

async function listStores() {
  const data = await netlifyFetch(`/api/v1/blobs/${SITE_ID}`);
  return Array.isArray(data) ? data : data && data.stores ? data.stores : [];
}

async function listBlobKeys(storeName) {
  const keys = [];
  let cursor = null;
  for (;;) {
    const qs = new URLSearchParams({ limit: "1000" });
    if (cursor) qs.set("cursor", cursor);
    const data = await netlifyFetch(
      `/api/v1/blobs/${SITE_ID}/${encodeURIComponent(storeName)}?${qs.toString()}`
    );
    const batch = (data && data.blobs) || (data && data.keys) || [];
    for (const item of batch) {
      keys.push(typeof item === "string" ? item : item.key || item.name);
    }
    cursor = data && data.next_cursor ? data.next_cursor : null;
    if (!cursor) break;
  }
  return keys.filter(Boolean);
}

async function getBlob(storeName, key) {
  const res = await fetch(
    `https://api.netlify.com/api/v1/blobs/${SITE_ID}/${encodeURIComponent(storeName)}/${encodeURIComponent(key)}`,
    { headers: { Authorization: `Bearer ${TOKEN}` } }
  );
  if (res.status === 404) return null;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`blob get ${storeName}/${key}: ${res.status} ${text.slice(0, 200)}`);
  }
  return res.text();
}

async function main() {
  const { out } = parseArgs(process.argv);
  if (!TOKEN) {
    console.error("NETLIFY_AUTH_TOKEN is required");
    process.exit(1);
  }
  const stores = await listStores();
  const exportDoc = {
    exported_at: new Date().toISOString(),
    site_id: SITE_ID,
    stores: {},
  };
  for (const store of stores) {
    const name = store.name || store.store_name || store;
    if (!name || typeof name !== "string") continue;
    console.error(`Exporting store ${name}…`);
    const keys = await listBlobKeys(name);
    const entries = {};
    for (const key of keys) {
      entries[key] = await getBlob(name, key);
    }
    exportDoc.stores[name] = { keys: keys.length, entries };
  }
  await fs.writeFile(out, JSON.stringify(exportDoc, null, 2));
  console.log(`Wrote ${out} (${Object.keys(exportDoc.stores).length} stores)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
