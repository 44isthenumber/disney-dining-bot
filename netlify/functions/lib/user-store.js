/**
 * People-identity store. Production: Netlify Blobs. Tests: in-memory.
 * Do not silently fall back to memory in production — users would vanish
 * between Lambda invocations.
 */

const { hashPassword } = require("./password");

const STORE_NAME = "mtf-users";

function normalizeEmail(email) {
  return String(email || "").trim().toLowerCase();
}

function publicUser(user) {
  if (!user) return null;
  return {
    id: user.id,
    name: user.name || user.id,
    email: user.email || null,
    has_phone: Boolean(user.phone),
  };
}

function parseEnvUsers(env = process.env) {
  const users = {};

  function ingest(raw, { requirePassword }) {
    if (!raw || !String(raw).trim()) return;
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return;
    }
    if (!parsed || typeof parsed !== "object") return;
    for (const [id, value] of Object.entries(parsed)) {
      if (!value || typeof value !== "object") continue;
      const password = String(value.password || "").trim();
      if (requirePassword && !password) continue;
      users[id] = {
        id,
        name: String(value.name || id).trim(),
        password,
        phone: String(value.phone || "").trim(),
      };
    }
  }

  ingest(env.WATCH_USERS || env.DISNEY_USERS || "", { requirePassword: true });
  if (!Object.keys(users).length) {
    ingest(env.FALLBACK_USERS || "", { requirePassword: true });
  }
  return users;
}

function createMemoryStore() {
  const usersById = new Map();
  const idByEmail = new Map();
  const idByLookup = new Map();

  return {
    kind: "memory",
    async getById(id) {
      return usersById.get(id) || null;
    },
    async findByIdentifier(identifier) {
      const raw = String(identifier || "").trim();
      if (!raw) return null;
      const lower = raw.toLowerCase();
      if (raw.includes("@")) {
        const id = idByEmail.get(lower);
        return id ? usersById.get(id) || null : null;
      }
      const id = idByLookup.get(lower);
      return id ? usersById.get(id) || null : null;
    },
    async createUser(record) {
      const email = normalizeEmail(record.email);
      if (email && idByEmail.has(email)) return { ok: false, reason: "email_taken" };
      if (idByLookup.has(String(record.id).toLowerCase())) return { ok: false, reason: "id_taken" };
      if (email) idByEmail.set(email, record.id);
      idByLookup.set(String(record.id).toLowerCase(), record.id);
      usersById.set(record.id, { ...record, email });
      return { ok: true, user: usersById.get(record.id) };
    },
    async seedFromEnvUsers(envUsers) {
      const seeded = [];
      for (const [id, data] of Object.entries(envUsers || {})) {
        if (idByLookup.has(String(id).toLowerCase())) continue;
        if (!data.password) continue;
        const user = {
          id,
          name: data.name || id,
          email: "",
          phone: data.phone || "",
          password_hash: hashPassword(data.password),
          sms_consent_at: null,
          created_at: new Date().toISOString(),
          seeded: true,
        };
        const result = await this.createUser(user);
        if (result.ok) seeded.push(id);
      }
      return seeded;
    },
  };
}

function attachBlobsFromEvent(event) {
  const { connectLambda } = require("@netlify/blobs");
  if (event && event.blobs) {
    connectLambda(event);
  }
}

async function claimKey(store, key, value) {
  const existing = await store.get(key, { type: "json" });
  if (existing && existing.userId && existing.userId !== value.userId) return false;
  await store.setJSON(key, value);
  const confirm = await store.get(key, { type: "json" });
  return Boolean(confirm && confirm.userId === value.userId);
}

function createBlobsStore(event) {
  let getStore;
  try {
    attachBlobsFromEvent(event);
    ({ getStore } = require("@netlify/blobs"));
  } catch (err) {
    throw new Error("Netlify Blobs is not available; refusing memory fallback");
  }
  const store = getStore({ name: STORE_NAME, consistency: "strong" });

  return {
    kind: "blobs",
    async getById(id) {
      if (!id) return null;
      const user = await store.get(`user:${id}`, { type: "json" });
      return user || null;
    },
    async findByIdentifier(identifier) {
      const raw = String(identifier || "").trim();
      if (!raw) return null;
      const lower = raw.toLowerCase();
      if (raw.includes("@")) {
        const pointer = await store.get(`email:${lower}`, { type: "json" });
        if (!pointer || !pointer.userId) return null;
        return this.getById(pointer.userId);
      }
      const pointer = await store.get(`idlookup:${lower}`, { type: "json" });
      if (pointer && pointer.userId) return this.getById(pointer.userId);
      return this.getById(raw);
    },
    async createUser(record) {
      const email = normalizeEmail(record.email);
      const saved = { ...record, email };
      const lookupKey = `idlookup:${String(record.id).toLowerCase()}`;
      if (email) {
        const claimed = await claimKey(store, `email:${email}`, { userId: record.id });
        if (!claimed) return { ok: false, reason: "email_taken" };
      }
      const idClaimed = await claimKey(store, lookupKey, { userId: record.id });
      if (!idClaimed) return { ok: false, reason: "id_taken" };
      await store.setJSON(`user:${record.id}`, saved);
      if (email) {
        const stillOurs = await store.get(`email:${email}`, { type: "json" });
        if (!stillOurs || stillOurs.userId !== record.id) {
          await store.delete(`user:${record.id}`);
          await store.delete(lookupKey);
          return { ok: false, reason: "email_taken" };
        }
      }
      return { ok: true, user: saved };
    },
    async seedFromEnvUsers(envUsers) {
      const seeded = [];
      for (const [id, data] of Object.entries(envUsers || {})) {
        const existing = await this.findByIdentifier(id);
        if (existing) continue;
        if (!data.password) continue;
        const user = {
          id,
          name: data.name || id,
          email: "",
          phone: data.phone || "",
          password_hash: hashPassword(data.password),
          sms_consent_at: null,
          created_at: new Date().toISOString(),
          seeded: true,
        };
        const result = await this.createUser(user);
        if (result.ok) seeded.push(id);
      }
      return seeded;
    },
  };
}

function createUserStore({ event, allowMemory = false } = {}) {
  if (process.env.MTF_USER_STORE === "memory") {
    if (!allowMemory) {
      throw new Error("MTF_USER_STORE=memory is test-only");
    }
    return createMemoryStore();
  }
  return createBlobsStore(event);
}

module.exports = {
  STORE_NAME,
  normalizeEmail,
  publicUser,
  parseEnvUsers,
  attachBlobsFromEvent,
  claimKey,
  createMemoryStore,
  createBlobsStore,
  createUserStore,
};
