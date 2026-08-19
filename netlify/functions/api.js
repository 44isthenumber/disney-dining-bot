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
const crypto = require("crypto");
const { createMemoryStore, createUserStore, publicUser } = require("./lib/user-store");
const { resolveSessionSecret } = require("./lib/session");
const {
  ensureSeeded,
  handleSignup,
  handleLogin,
  handleLogout,
  requireUser,
} = require("./lib/identity");

// ── env ───────────────────────────────────────────────────────────────────────

const GIST_ID = process.env.GITHUB_GIST_ID || "";
const GH_TOKEN = process.env.GITHUB_TOKEN || "";
const DEFAULT_OWNER_ID = process.env.DEFAULT_OWNER_ID || "craig";

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
  if (parts.length === 4) return { ownerId: parts[0], facilityId: parts[1], partySize: parseInt(parts[2], 10), date: parts[3] };
  if (parts.length === 3) return { ownerId: DEFAULT_OWNER_ID, facilityId: parts[0], partySize: parseInt(parts[1], 10), date: parts[2] };
  return null;
}

// People identity lives in Netlify Blobs (see lib/user-store.js).
// WATCH_USERS is only a one-time seed source for craig / Jessica.

function watchRecordId(ownerId, facilityId, partySize, date) {
  return `${ownerId}__${facilityId}__${partySize}__${date}`;
}

function newWatchId() {
  return `watch_${crypto.randomBytes(8).toString("hex")}`;
}

function normalizeWatch(raw, userFallback = null) {
  const ownerId = raw.owner_id || raw.ownerId || (userFallback && userFallback.id) || DEFAULT_OWNER_ID;
  const partySize = parseInt(raw.party_size || raw.partySize || 2, 10);
  const date = raw.date;
  const existingPhone = raw.recipient_phone;
  return {
    watch_id: raw.watch_id || raw.watchId || newWatchId(),
    owner_id: ownerId,
    facility_id: raw.facility_id,
    name: raw.name || raw.restaurant_name || raw.facility_id,
    slug: raw.slug || raw.facility_id,
    party_size: partySize,
    meal_periods: raw.meal_periods || ["ALL"],
    booking_type: raw.booking_type === "scheduled_activity" ? "scheduled_activity" : "dining",
    date,
    time_from: raw.time_from || null,
    time_to: raw.time_to || null,
    recipient_phone: existingPhone == null ? "" : existingPhone,
    created_at: raw.created_at || new Date().toISOString(),
  };
}

async function loadWatches() {
  const stored = await readJson("watches.json");
  if (stored && Array.isArray(stored.watches)) {
    return stored.watches.filter((w) => w.facility_id && w.date).map((w) => normalizeWatch(w));
  }
  if (Array.isArray(stored)) {
    return stored.filter((w) => w.facility_id && w.date).map((w) => normalizeWatch(w));
  }

  // Backward-compatible migration from config.yaml.
  const cfg = await loadConfig();
  const watches = [];
  for (const entry of cfg.restaurants || []) {
    for (const d of entry.dates || []) {
      watches.push(normalizeWatch({
        owner_id: DEFAULT_OWNER_ID,
        facility_id: entry.facility_id,
        name: entry.name,
        slug: entry.slug,
        party_size: entry.party_size || 2,
        meal_periods: entry.meal_periods || ["ALL"],
        date: d,
      }));
    }
  }
  return watches;
}

async function saveWatches(watches) {
  await writeText("watches.json", JSON.stringify({
    schema_version: 1,
    updated_at: new Date().toISOString(),
    watches: watches.map((w) => normalizeWatch(w)),
  }, null, 2));
}

function publicWatch(watch) {
  const { recipient_phone, ...safe } = watch;
  return safe;
}

function todayIsoInParkTime() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function isActiveWatch(watch, today = todayIsoInParkTime()) {
  return typeof watch.date === "string" && watch.date >= today;
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

function isPublicPath(method, apiPath) {
  if (apiPath === "/health") return true;
  if (method === "POST" && (apiPath === "/signup" || apiPath === "/login" || apiPath === "/logout")) {
    return true;
  }
  return false;
}

// ── response helper ───────────────────────────────────────────────────────────

function response(status, body, extraHeaders = {}) {
  return {
    statusCode: status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
      ...extraHeaders,
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  };
}

// ── endpoint handlers ─────────────────────────────────────────────────────────

// Health endpoint for external uptime monitors. Returns 200 OK iff the worker
// has successfully polled Disney within HEALTH_STALE_MINUTES (default 30).
// Returns 503 with a small JSON body when stale or when no successful poll has
// ever been recorded. No auth, no sensitive data leaked.
async function handleHealth() {
  const STALE_MIN = parseInt(process.env.HEALTH_STALE_MINUTES || "30", 10);
  let state = null;
  try {
    state = await readJson("bot_state.json", {});
  } catch (err) {
    return response(503, { ok: false, reason: `state read failed: ${err.message}` });
  }
  state = state || {};
  const lastSuccess = state.last_successful_poll_at;
  if (!lastSuccess) {
    return response(503, { ok: false, reason: "no successful poll recorded yet" });
  }
  const lastMs = Date.parse(lastSuccess);
  if (isNaN(lastMs)) {
    return response(503, { ok: false, reason: `unparseable last_successful_poll_at: ${lastSuccess}` });
  }
  const ageMin = Math.round((Date.now() - lastMs) / 60000);
  if (ageMin > STALE_MIN) {
    return response(503, {
      ok: false,
      reason: `last successful poll was ${ageMin} min ago (threshold ${STALE_MIN})`,
      last_successful_poll_at: lastSuccess,
    });
  }
  return response(200, {
    ok: true,
    last_successful_poll_at: lastSuccess,
    age_minutes: ageMin,
  });
}

async function handleStatus(user, loadAllWatches = loadWatches) {
  let tokenStatus = "browser-session";
  let tokenExpiresInMinutes = null;

  const botState = (await readJson("bot_state.json")) || {};

  let restaurantsIndexed = 0;
  try {
    restaurantsIndexed = require("./restaurants.json").count || 0;
  } catch {}

  const watches = await loadAllWatches();
  const activeWatches = watches.filter((w) => isActiveWatch(w));
  const userWatches = activeWatches.filter((w) => w.owner_id === user.id);
  const userExpiredWatches = watches.filter((w) => w.owner_id === user.id && !isActiveWatch(w));

  return response(200, {
    profile: publicUser(user),
    token_status: tokenStatus,
    token_expires_in_minutes: tokenExpiresInMinutes,
    last_poll_at: botState.last_poll_at || null,
    last_successful_poll_at: botState.last_successful_poll_at || null,
    last_sms_sent_at: botState.last_sms_sent_at || null,
    session_status: botState.session_status || "unknown",
    auth_status: botState.auth_status || (botState.session_status === "ok" ? "ok" : "unknown"),
    auth_required_since: botState.auth_required_since || null,
    last_auth_ok_at: botState.last_auth_ok_at || null,
    last_errors: botState.last_errors || [],
    slots_found_last_poll: botState.slots_found_last_poll ?? null,
    watches_count: userWatches.length,
    expired_watches_count: userExpiredWatches.length,
    total_watches_count: activeWatches.length,
    restaurants_indexed: restaurantsIndexed,
  });
}

async function handleRestaurants(event, user, loadAllWatches = loadWatches) {
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

  const watched = {};
  const watches = (await loadAllWatches()).filter((w) => w.owner_id === user.id && isActiveWatch(w));
  for (const entry of watches) {
    const key = `${entry.facility_id}__${entry.party_size}`;
    if (!watched[key]) watched[key] = { party_size: entry.party_size || 2, dates: [] };
    watched[key].dates.push(entry.date);
  }

  for (const r of results) {
    const matching = Object.entries(watched)
      .filter(([key]) => key.startsWith(`${r.facility_id}__`))
      .map(([, value]) => value);
    const w = matching[0];
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

async function handleGetWatches(user, loadAllWatches = loadWatches) {
  const watches = (await loadAllWatches())
    .filter((w) => w.owner_id === user.id)
    .filter((w) => isActiveWatch(w))
    .map(publicWatch);
  return response(200, { owner_id: user.id, watches });
}

async function handlePostWatch(event, user, loadAllWatches = loadWatches, saveAllWatches = saveWatches) {
  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return response(400, { detail: "Invalid JSON body" });
  }

  if (!user.phone) {
    return response(422, { detail: "Add a mobile number to your account before creating a watch." });
  }

  const {
    facility_id,
    name,
    slug,
    party_size = 2,
    meal_periods = ["ALL"],
    dates = [],
    time_from = null,
    time_to = null,
    booking_type = "dining",
  } = body;

  const errors = [];
  const facilityId = typeof facility_id === "string" ? facility_id.trim() : String(facility_id || "").trim();
  const rawPartySize = typeof party_size === "string" ? party_size.trim() : party_size;
  const partySize = Number(rawPartySize);
  let normalizedDates = [];
  let normalizedMealPeriods = ["ALL"];
  const timeFrom = typeof time_from === "string" && time_from.trim() ? time_from.trim() : null;
  const timeTo = typeof time_to === "string" && time_to.trim() ? time_to.trim() : null;

  const bookingType = booking_type === "scheduled_activity" ? "scheduled_activity" : "dining";
  let facilityRecord = null;
  try {
    facilityRecord = (require("./restaurants.json").restaurants || [])
      .find((r) => r.facility_id === facilityId) || null;
  } catch {
    facilityRecord = null;
  }

  if (!facilityId) {
    errors.push("Choose a restaurant first.");
  }

  if (!Number.isInteger(partySize) || partySize < 1 || partySize > 20) {
    errors.push("Party size must be a whole number between 1 and 20.");
  } else if (facilityRecord && facilityRecord.max_party_size && partySize > facilityRecord.max_party_size) {
    errors.push(`${facilityRecord.name} allows up to ${facilityRecord.max_party_size} guests per reservation.`);
  }

  if (!Array.isArray(dates) || dates.length === 0) {
    errors.push("Add at least one date.");
  } else {
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    for (const rawDate of dates) {
      const date = typeof rawDate === "string" ? rawDate.trim() : String(rawDate || "").trim();
      if (!dateRegex.test(date)) {
        errors.push(`Use YYYY-MM-DD dates. Invalid date: ${date || "(blank)"}.`);
        break;
      }
      const [year, month, day] = date.split("-").map(Number);
      const parsed = new Date(Date.UTC(year, month - 1, day));
      if (
        parsed.getUTCFullYear() !== year ||
        parsed.getUTCMonth() !== month - 1 ||
        parsed.getUTCDate() !== day
      ) {
        errors.push(`That date is not valid: ${date}.`);
        break;
      }
      normalizedDates.push(date);
    }
    normalizedDates = [...new Set(normalizedDates)].sort();
  }

  const validMealPeriods = ["ALL", "BREAKFAST", "LUNCH", "DINNER"];
  if (meal_periods && !Array.isArray(meal_periods)) {
    errors.push("Meal periods must be a list.");
  } else if (bookingType === "scheduled_activity") {
    normalizedMealPeriods = meal_periods && meal_periods.length > 0
      ? meal_periods.map((period) => String(period || "").trim().toUpperCase()).filter(Boolean)
      : ["ALL"];
    if (normalizedMealPeriods.length !== 1 || normalizedMealPeriods[0] !== "ALL") {
      errors.push("This experience uses the time window, not meal periods.");
    }
  } else {
    normalizedMealPeriods = meal_periods && meal_periods.length > 0
      ? meal_periods.map((period) => String(period || "").trim().toUpperCase()).filter(Boolean)
      : ["ALL"];
    for (const period of normalizedMealPeriods) {
      if (!validMealPeriods.includes(period)) {
        errors.push("Meal period must be Any meal, Breakfast, Lunch, or Dinner.");
        break;
      }
    }
    if (normalizedMealPeriods.includes("ALL") && normalizedMealPeriods.length > 1) {
      errors.push("Choose either Any meal or specific meal periods.");
    }
  }

  const timeRegex = /^([01]\d|2[0-3]):([0-5]\d)$/;
  if (timeFrom && !timeRegex.test(timeFrom)) {
    errors.push("Earliest time must be HH:MM.");
  }
  if (timeTo && !timeRegex.test(timeTo)) {
    errors.push("Latest time must be HH:MM.");
  }
  if (timeFrom && timeTo && timeFrom > timeTo) {
    errors.push("Earliest time must be before latest time.");
  }

  if (errors.length > 0) {
    return response(422, { detail: errors.join(" ") });
  }

  const watches = await loadAllWatches();
  const byId = new Map(watches.map((w) => [w.watch_id, w]));
  const added = [];
  for (const date of normalizedDates) {
    const wid = newWatchId();
    byId.set(wid, normalizeWatch({
      watch_id: wid,
      owner_id: user.id,
      facility_id: facilityId,
      name: name || facilityId,
      slug: slug || facilityId,
      party_size: partySize,
      meal_periods: normalizedMealPeriods,
      booking_type: bookingType,
      date,
      time_from: timeFrom,
      time_to: timeTo,
      recipient_phone: user.phone,
    }, user));
    added.push(wid);
  }
  await saveAllWatches([...byId.values()]);
  return response(201, { added });
}

async function handleDeleteWatch(watchIdStr, user, loadAllWatches = loadWatches, saveAllWatches = saveWatches) {
  const watches = await loadAllWatches();
  const remaining = watches.filter((w) => !(w.watch_id === watchIdStr && w.owner_id === user.id));
  if (remaining.length === watches.length) return response(404, { detail: "Watch not found" });
  await saveAllWatches(remaining);
  return { statusCode: 204, headers: { "Access-Control-Allow-Origin": "*" }, body: "" };
}

// ── router ────────────────────────────────────────────────────────────────────

function createHandler(deps = {}) {
  const nowFn = deps.now || (() => Date.now());
  const secret = resolveSessionSecret(deps.sessionSecret);
  const injectedStore = deps.store || null;
  const allowMemory = Boolean(deps.allowMemory);
  const watchesState = deps.watchesState || null;

  async function loadAllWatches() {
    if (watchesState) return (watchesState.watches || []).map((w) => normalizeWatch(w));
    return loadWatches();
  }
  async function saveAllWatches(watches) {
    if (watchesState) {
      watchesState.watches = watches.map((w) => normalizeWatch(w));
      return;
    }
    return saveWatches(watches);
  }

  return async function handler(event, context) {
    if (event.httpMethod === "OPTIONS") {
      return response(204, "", {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
      });
    }

    let p = event.path || "/";
    p = p.replace(/^\/.netlify\/functions\/api/, "").replace(/^\/_api/, "") || "/";
    if (!p.startsWith("/")) p = "/" + p;

    const method = event.httpMethod;
    const nowMs = nowFn();
    const jsonResponse = response;

    try {
      if (method === "GET" && p === "/health") return await handleHealth();
      if (method === "GET" && p === "/profiles") {
        return response(404, { detail: "Not found" });
      }

      let store = injectedStore;
      if (!store) {
        store = createUserStore({ context, allowMemory });
      }
      await ensureSeeded(store);

      if (method === "POST" && p === "/signup") {
        return await handleSignup(event, store, { secret, nowMs, jsonResponse });
      }
      if (method === "POST" && p === "/login") {
        return await handleLogin(event, store, { secret, nowMs, jsonResponse });
      }
      if (method === "POST" && p === "/logout") {
        return handleLogout(event, { jsonResponse });
      }

      if (!isPublicPath(method, p)) {
        const resolved = await requireUser(event, store, { secret, nowMs, jsonResponse });
        if (resolved.error) return resolved.error;
        const user = resolved.user;

        if (method === "GET" && p === "/me") return response(200, { profile: publicUser(user) });
        if (method === "GET" && p === "/status") return await handleStatus(user, loadAllWatches);
        if (method === "GET" && p === "/restaurants") return await handleRestaurants(event, user, loadAllWatches);
        if (method === "GET" && p.startsWith("/calendar/")) {
          return await handleCalendar(p.slice("/calendar/".length));
        }
        if (method === "GET" && p === "/watches") return await handleGetWatches(user, loadAllWatches);
        if (method === "POST" && p === "/watches") {
          return await handlePostWatch(event, user, loadAllWatches, saveAllWatches);
        }
        if (method === "DELETE" && p.startsWith("/watches/")) {
          return await handleDeleteWatch(
            decodeURIComponent(p.slice("/watches/".length)),
            user,
            loadAllWatches,
            saveAllWatches
          );
        }
      }

      return response(404, { detail: `Not found: ${method} ${p}` });
    } catch (err) {
      console.error("Handler error:", err && err.message ? err.message : "Internal server error");
      return response(500, { detail: "Internal server error" });
    }
  };
}

exports.createHandler = createHandler;
exports.createMemoryStore = createMemoryStore;
exports.handler = createHandler();
exports.normalizeWatch = normalizeWatch;
