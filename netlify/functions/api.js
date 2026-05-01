/**
 * Netlify Function: Disney Dining Bot API
 *
 * Routes (mounted at /_api/* → /.netlify/functions/api/:splat):
 *   GET  /status
 *   GET  /restaurants?q=&park=&cuisine=
 *   GET  /calendar/:facilityId
 *   GET  /watches
 *   POST /watches
 *   DELETE /watches/:watchId
 */

const https = require("https");
const path = require("path");
const fs = require("fs");

// ── env ───────────────────────────────────────────────────────────────────────

const GIST_ID = process.env.GITHUB_GIST_ID || "";
const GH_TOKEN = process.env.GITHUB_TOKEN || "";
const API_SECRET = (process.env.API_SECRET || "").trim();

// ── http helper ───────────────────────────────────────────────────────────────

function httpRequest(method, url, headers, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const opts = {
      hostname: u.hostname,
      path: u.pathname + u.search,
      method,
      headers: { ...headers },
    };
    if (body) {
      const buf = Buffer.isBuffer(body) ? body : Buffer.from(body);
      opts.headers["Content-Length"] = buf.length;
    }
    const req = https.request(opts, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () =>
        resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() })
      );
    });
    req.on("error", reject);
    if (body) req.write(Buffer.isBuffer(body) ? body : Buffer.from(body));
    req.end();
  });
}

// ── gist storage ─────────────────────────────────────────────────────────────

let _gistCache = null;
let _gistCacheAt = 0;
const GIST_TTL = 10000; // 10 s within a single warm Lambda

async function _fetchGist() {
  const now = Date.now();
  if (_gistCache && now - _gistCacheAt < GIST_TTL) return _gistCache;
  const { status, body } = await httpRequest(
    "GET",
    `https://api.github.com/gists/${GIST_ID}`,
    {
      Authorization: `Bearer ${GH_TOKEN}`,
      Accept: "application/vnd.github.v3+json",
      "User-Agent": "disney-dining-bot",
    }
  );
  if (status !== 200) throw new Error(`Gist fetch failed: ${status} ${body.slice(0, 200)}`);
  _gistCache = JSON.parse(body);
  _gistCacheAt = now;
  return _gistCache;
}

async function readText(filename, def = "") {
  if (!GIST_ID || !GH_TOKEN) {
    try {
      return fs.readFileSync(path.join(__dirname, "..", "..", filename), "utf8");
    } catch {
      return def;
    }
  }
  const gist = await _fetchGist();
  return (gist.files[filename] || {}).content || def;
}

async function writeText(filename, content) {
  _gistCache = null; // invalidate cache
  const bodyStr = JSON.stringify({ files: { [filename]: { content } } });
  const { status, body } = await httpRequest(
    "PATCH",
    `https://api.github.com/gists/${GIST_ID}`,
    {
      Authorization: `Bearer ${GH_TOKEN}`,
      Accept: "application/vnd.github.v3+json",
      "User-Agent": "disney-dining-bot",
      "Content-Type": "application/json",
    },
    bodyStr
  );
  if (status < 200 || status >= 300)
    throw new Error(`Gist write failed: ${status} ${body.slice(0, 200)}`);
}

async function readJson(filename, def = null) {
  const text = await readText(filename, "");
  if (!text) return def;
  try {
    return JSON.parse(text);
  } catch {
    return def;
  }
}

// ── yaml parser (minimal subset — sequences of mappings) ─────────────────────

// Load js-yaml if present; otherwise fall back to a tiny inline parser.
let yaml;
try {
  yaml = require("js-yaml");
} catch {
  yaml = {
    load: (text) => parseSimpleYaml(text),
    dump: (obj) => dumpSimpleYaml(obj),
  };
}

/**
 * Minimal YAML parser that handles the config.yaml structure:
 *   restaurants:
 *     - facility_id: xxx
 *       name: ...
 *       dates:
 *         - 2025-01-01
 */
function parseSimpleYaml(text) {
  if (!text || !text.trim()) return {};
  const lines = text.split("\n");
  const result = {};
  let currentList = null;
  let currentObj = null;
  let currentListKey = null;
  let inDates = false;

  for (const raw of lines) {
    const line = raw.replace(/\r$/, "");
    if (!line.trim() || line.trim().startsWith("#")) continue;

    const indent = line.length - line.trimStart().length;

    if (indent === 0) {
      const m = line.match(/^(\w+):\s*(.*)$/);
      if (m) {
        const key = m[1];
        const val = m[2].trim();
        if (val === "" || val === null) {
          result[key] = [];
          currentList = result[key];
          currentListKey = key;
          currentObj = null;
          inDates = false;
        } else {
          result[key] = val;
        }
      }
    } else if (indent === 2 && line.trimStart().startsWith("- ")) {
      // list item start
      const content = line.trimStart().slice(2).trim();
      const m = content.match(/^(\w+):\s*(.*)$/);
      if (m) {
        currentObj = { [m[1]]: _coerce(m[2].trim()) };
        currentList.push(currentObj);
        inDates = false;
      }
    } else if (indent === 4 && currentObj) {
      if (line.trimStart().startsWith("- ")) {
        // nested list item
        if (inDates) {
          currentObj[Object.keys(currentObj).find((k) => Array.isArray(currentObj[k]) && k !== "meal_periods") || "dates"].push(
            line.trimStart().slice(2).trim()
          );
        }
      } else {
        const m = line.trimStart().match(/^(\w+):\s*(.*)$/);
        if (m) {
          const val = m[2].trim();
          if (val === "") {
            currentObj[m[1]] = [];
            inDates = true;
          } else if (m[1] === "meal_periods") {
            currentObj[m[1]] = val ? [val] : [];
            inDates = false;
          } else {
            currentObj[m[1]] = _coerce(val);
            inDates = false;
          }
        }
      }
    } else if (indent === 6 && currentObj && inDates) {
      const val = line.trimStart().replace(/^- /, "").trim();
      const lastKey = Object.keys(currentObj).slice(-1)[0];
      if (Array.isArray(currentObj[lastKey])) currentObj[lastKey].push(val);
    }
  }
  return result;
}

function _coerce(v) {
  if (v === "true") return true;
  if (v === "false") return false;
  if (v === "null" || v === "~") return null;
  if (/^\d+$/.test(v)) return parseInt(v, 10);
  // strip surrounding quotes
  if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'")))
    return v.slice(1, -1);
  return v;
}

function dumpSimpleYaml(obj) {
  const restaurants = (obj.restaurants || []);
  const lines = ["restaurants:"];
  for (const r of restaurants) {
    lines.push(`  - facility_id: ${r.facility_id}`);
    lines.push(`    name: ${r.name}`);
    lines.push(`    slug: ${r.slug || r.facility_id}`);
    lines.push(`    party_size: ${r.party_size || 2}`);
    if (r.meal_periods && r.meal_periods.length) {
      lines.push(`    meal_periods:`);
      for (const mp of r.meal_periods) lines.push(`      - ${mp}`);
    }
    if (r.dates && r.dates.length) {
      lines.push(`    dates:`);
      for (const d of r.dates) lines.push(`      - ${d}`);
    }
  }
  return lines.join("\n") + "\n";
}

// ── config helpers ────────────────────────────────────────────────────────────

async function loadConfig() {
  const text = await readText("config.yaml", "");
  if (!text) return { restaurants: [] };
  try {
    return yaml.load(text) || { restaurants: [] };
  } catch {
    return { restaurants: [] };
  }
}

async function saveConfig(cfg) {
  const content = yaml.dump ? yaml.dump(cfg, { lineWidth: -1 }) : dumpSimpleYaml(cfg);
  await writeText("config.yaml", content);
}

function watchId(facilityId, partySize, date) {
  return `${facilityId}__${partySize}__${date}`;
}

function parseWatchId(wid) {
  const parts = wid.split("__");
  if (parts.length !== 3) return null;
  return { facilityId: parts[0], partySize: parseInt(parts[1], 10), date: parts[2] };
}

// ── JWT expiry ────────────────────────────────────────────────────────────────

function jwtExp(token) {
  try {
    const payload = token.split(".")[1];
    const decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    return decoded.exp || null;
  } catch {
    return null;
  }
}

// ── auth ──────────────────────────────────────────────────────────────────────

function checkSecret(event) {
  if (!API_SECRET) return null;
  if (event.httpMethod === "OPTIONS") return null;
  const secret =
    event.headers["x-api-secret"] ||
    event.headers["X-Api-Secret"] ||
    event.headers["X-API-Secret"] ||
    "";
  if (secret !== API_SECRET) return response(401, { detail: "Invalid API secret" });
  return null;
}

// ── response helper ───────────────────────────────────────────────────────────

function response(status, body, extraHeaders = {}) {
  return {
    statusCode: status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, X-API-Secret",
      "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
      ...extraHeaders,
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  };
}

// ── endpoint handlers ─────────────────────────────────────────────────────────

async function handleStatus() {
  let tokenStatus = "ok";
  let tokenExpiresInMinutes = null;

  try {
    const tokens = await readJson("tokens.json");
    if (tokens && tokens.access_token) {
      const exp = jwtExp(tokens.access_token);
      if (exp) {
        tokenExpiresInMinutes = Math.floor((exp - Date.now() / 1000) / 60);
        if (tokenExpiresInMinutes < 0) tokenStatus = "expired";
      }
    } else {
      tokenStatus = "missing";
    }
  } catch (e) {
    tokenStatus = `error: ${e.message}`;
  }

  const botState = (await readJson("bot_state.json")) || {};

  let restaurantsIndexed = 0;
  try {
    restaurantsIndexed = require("./restaurants.json").count || 0;
  } catch {}

  const cfg = await loadConfig();
  const watchesCount = (cfg.restaurants || []).reduce(
    (s, r) => s + (r.dates || []).length,
    0
  );

  return response(200, {
    token_status: tokenStatus,
    token_expires_in_minutes: tokenExpiresInMinutes,
    last_poll_at: botState.last_poll_at || null,
    slots_found_last_poll: botState.slots_found_last_poll || null,
    watches_count: watchesCount,
    restaurants_indexed: restaurantsIndexed,
  });
}

async function handleRestaurants(event) {
  let data;
  try {
    // require() is traced by zip-it-and-ship-it so this file gets bundled.
    // Build step copies public/restaurants.json here before ZISI runs.
    data = require("./restaurants.json");
  } catch {
    return response(503, { detail: "restaurants.json not found" });
  }
  let results = data.restaurants || [];

  const qs = event.queryStringParameters || {};
  if (qs.q) {
    const q = qs.q.toLowerCase();
    results = results.filter((r) => r.name.toLowerCase().includes(q));
  }
  if (qs.park) {
    const pk = qs.park.toLowerCase();
    results = results.filter((r) => (r.park || "").toLowerCase().includes(pk));
  }
  if (qs.cuisine) {
    const cu = qs.cuisine.toLowerCase();
    results = results.filter((r) => (r.cuisine || "").toLowerCase().includes(cu));
  }

  const cfg = await loadConfig();
  const watched = {};
  for (const entry of cfg.restaurants || []) {
    watched[entry.facility_id] = {
      party_size: entry.party_size || 2,
      dates: entry.dates || [],
    };
  }

  for (const r of results) {
    const w = watched[r.facility_id];
    r.watched_dates = w ? w.dates : [];
    r.watched_party_size = w ? w.party_size : null;
  }

  return response(200, { restaurants: results, total: results.length });
}

async function handleCalendar(facilityId) {
  const cached = await readJson(`calendar_${facilityId}.json`);
  if (cached) {
    return response(200, {
      facility_id: facilityId,
      available_dates: cached.available_dates || [],
      cached_at: cached.cached_at || null,
    });
  }
  return response(200, { facility_id: facilityId, available_dates: [], cached_at: null });
}

async function handleGetWatches() {
  const cfg = await loadConfig();
  const watches = [];
  for (const entry of cfg.restaurants || []) {
    const fid = entry.facility_id;
    const ps = parseInt(entry.party_size || 2, 10);
    for (const d of entry.dates || []) {
      watches.push({
        watch_id: watchId(fid, ps, d),
        facility_id: fid,
        name: entry.name || fid,
        slug: entry.slug || fid,
        party_size: ps,
        meal_periods: entry.meal_periods || ["ALL"],
        date: d,
      });
    }
  }
  return response(200, { watches });
}

async function handlePostWatch(event) {
  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return response(400, { detail: "Invalid JSON body" });
  }

  const { facility_id, name, slug, party_size = 2, meal_periods = ["ALL"], dates = [] } = body;
  if (!facility_id || !dates.length) {
    return response(422, { detail: "facility_id and dates are required" });
  }

  const cfg = await loadConfig();
  const restaurants = cfg.restaurants || (cfg.restaurants = []);
  const existing = restaurants.find(
    (r) => r.facility_id === facility_id && parseInt(r.party_size || 2, 10) === party_size
  );

  if (existing) {
    const merged = new Set([...(existing.dates || []), ...dates]);
    existing.dates = [...merged].sort();
    existing.meal_periods = meal_periods;
    existing.name = name;
    existing.slug = slug;
  } else {
    restaurants.push({
      facility_id,
      name: name || facility_id,
      slug: slug || facility_id,
      party_size,
      meal_periods,
      dates: [...new Set(dates)].sort(),
    });
  }

  await saveConfig(cfg);
  return response(201, {
    added: dates.map((d) => watchId(facility_id, party_size, d)),
  });
}

async function handleDeleteWatch(watchIdStr) {
  const parsed = parseWatchId(watchIdStr);
  if (!parsed) return response(400, { detail: "Invalid watch_id format" });
  const { facilityId, partySize, date } = parsed;

  const cfg = await loadConfig();
  for (const entry of cfg.restaurants || []) {
    if (entry.facility_id === facilityId && parseInt(entry.party_size || 2, 10) === partySize) {
      entry.dates = (entry.dates || []).filter((d) => d !== date);
      break;
    }
  }
  cfg.restaurants = (cfg.restaurants || []).filter((r) => (r.dates || []).length > 0);
  await saveConfig(cfg);
  return { statusCode: 204, headers: { "Access-Control-Allow-Origin": "*" }, body: "" };
}

// ── router ────────────────────────────────────────────────────────────────────

exports.handler = async function (event) {
  // CORS preflight
  if (event.httpMethod === "OPTIONS") {
    return response(204, "", {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, X-API-Secret",
      "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    });
  }

  const authErr = checkSecret(event);
  if (authErr) return authErr;

  // Strip function prefix to get the API path:
  // event.path is like "/.netlify/functions/api/status" or "/_api/status"
  let p = event.path || "/";
  p = p.replace(/^\/.netlify\/functions\/api/, "").replace(/^\/_api/, "") || "/";
  if (!p.startsWith("/")) p = "/" + p;

  const method = event.httpMethod;

  try {
    if (method === "GET" && p === "/status") return await handleStatus();
    if (method === "GET" && p === "/restaurants") return await handleRestaurants(event);
    if (method === "GET" && p.startsWith("/calendar/")) {
      return await handleCalendar(p.slice("/calendar/".length));
    }
    if (method === "GET" && p === "/watches") return await handleGetWatches();
    if (method === "POST" && p === "/watches") return await handlePostWatch(event);
    if (method === "DELETE" && p.startsWith("/watches/")) {
      return await handleDeleteWatch(decodeURIComponent(p.slice("/watches/".length)));
    }

    return response(404, { detail: `Not found: ${method} ${p}` });
  } catch (err) {
    console.error("Handler error:", err);
    return response(500, { detail: err.message || "Internal server error" });
  }
};
