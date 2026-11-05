#!/usr/bin/env node
/**
 * Import blob-export JSON into Cloudflare KV (MTF_USERS namespace).
 *
 * Usage:
 *   node scripts/import-to-kv.mjs --file ./blob-export.json --store mtf-users
 *
 * Uses wrangler kv bulk put. Requires wrangler auth (CLOUDFLARE_API_TOKEN or wrangler login).
 */

import fs from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

function parseArgs(argv) {
  let file = "netlify-blobs-export.json";
  let store = "mtf-users";
  for (let i = 2; i < argv.length; i++) {
    if (argv[i] === "--file" && argv[i + 1]) file = argv[++i];
    else if (argv[i] === "--store" && argv[i + 1]) store = argv[++i];
  }
  return { file, store };
}

async function main() {
  const { file, store } = parseArgs(process.argv);
  const raw = await fs.readFile(file, "utf8");
  const doc = JSON.parse(raw);
  const blobStore = doc.stores && doc.stores[store];
  if (!blobStore || !blobStore.entries) {
    console.error(`Store ${store} not found in ${file}`);
    process.exit(1);
  }
  const bulk = [];
  for (const [key, value] of Object.entries(blobStore.entries)) {
    if (value == null) continue;
    bulk.push({ key, value: String(value) });
  }
  if (!bulk.length) {
    console.error("No entries to import");
    process.exit(1);
  }
  const dir = await mkdtemp(path.join(tmpdir(), "mtf-kv-import-"));
  const ndjson = path.join(dir, "bulk.ndjson");
  await writeFile(
    ndjson,
    bulk.map((row) => JSON.stringify(row)).join("\n") + "\n"
  );
  console.error(`Importing ${bulk.length} keys into KV binding MTF_USERS via wrangler…`);
  const result = spawnSync(
    "npx",
    ["wrangler", "kv", "bulk", "put", "--binding", "MTF_USERS", ndjson],
    { stdio: "inherit", cwd: path.resolve(path.dirname(new URL(import.meta.url).pathname), "..") }
  );
  await rm(dir, { recursive: true, force: true });
  if (result.status !== 0) process.exit(result.status || 1);
  console.log(`Imported ${bulk.length} keys from store ${store}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
