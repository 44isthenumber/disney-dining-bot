/**
 * Consumer identity store. Never Gist, never WATCH_USERS.
 * Production: Netlify Blobs store `mtf-users`. Tests: in-memory.
 */

const crypto = require("crypto");

const RESERVED_IDS = new Set(["craig", "jessica"]);
const BLOB_STORE_NAME = "mtf-users";

function normalizeEmail(email) {
  return String(email || "").trim().toLowerCase();
}

function isReservedId(id) {
  return RESERVED_IDS.has(String(id || "").trim().toLowerCase());
}

function newConsumerId() {
  return `u_${crypto.randomBytes(8).toString("hex")}`;
}

function emptyRecord(overrides) {
  return {
    id: "",
    email: "",
    phone: "",
    created_at: new Date().toISOString(),
    kind: "consumer",
    stripe_customer_id: null,
    planner_status: "none",
    planner_subscription_id: null,
    planner_current_period_end: null,
    cancel_at_period_end: false,
    single_watch_count: 0,
    ...overrides,
  };
}

function memoryBackend() {
  const ids = new Map();
  const emails = new Map();
  const used = new Map();
  const checkouts = new Map();
  const stripeIndex = new Map();
  return {
    kind: "memory",
    async getById(id) {
      return ids.get(id) || null;
    },
    async getByEmail(email) {
      const uid = emails.get(normalizeEmail(email));
      if (!uid) return null;
      return ids.get(uid) || null;
    },
    async getByStripeCustomerId(customerId) {
      const uid = stripeIndex.get(String(customerId || ""));
      if (!uid) return null;
      return ids.get(uid) || null;
    },
    async put(record) {
      ids.set(record.id, record);
      emails.set(normalizeEmail(record.email), record.id);
      if (record.stripe_customer_id) {
        stripeIndex.set(String(record.stripe_customer_id), record.id);
      }
    },
    async putCheckout(sessionId, payload) {
      checkouts.set(String(sessionId), payload);
    },
    async getCheckout(sessionId) {
      return checkouts.get(String(sessionId)) || null;
    },
    async deleteCheckout(sessionId) {
      checkouts.delete(String(sessionId));
    },
    async markUsed(nonce) {
      used.set(String(nonce), "1");
    },
    async isUsed(nonce) {
      return used.has(String(nonce));
    },
    async claimNonce(nonce) {
      const key = String(nonce);
      if (used.has(key)) return false;
      used.set(key, "1");
      return true;
    },
    upsertByEmail(email, extra = {}) {
      const normalized = normalizeEmail(email);
      const existingId = emails.get(normalized);
      if (existingId) {
        const current = ids.get(existingId) || emptyRecord({ id: existingId, email: normalized });
        const merged = { ...current, ...extra, id: existingId, email: normalized, kind: "consumer" };
        ids.set(existingId, merged);
        return merged;
      }
      const id = newConsumerId();
      const rec = emptyRecord({ id, email: normalized, ...extra });
      emails.set(normalized, id);
      ids.set(id, rec);
      return rec;
    },
    _reset() {
      ids.clear();
      emails.clear();
      used.clear();
      checkouts.clear();
      stripeIndex.clear();
    },
  };
}

function blobWriteCreatedEntry(result) {
  return !(result && result.modified === false);
}

function blobBackend() {
  connectBlobsFromEvent(_blobsEvent);
  const { getStore } = _blobsModule || require("@netlify/blobs");
  const store = getStore({ name: BLOB_STORE_NAME });
  return {
    kind: "blobs",
    async getById(id) {
      const raw = await store.get(`id:${id}`);
      if (!raw) return null;
      return JSON.parse(raw);
    },
    async getByEmail(email) {
      const uid = await store.get(`email:${normalizeEmail(email)}`);
      if (!uid) return null;
      return this.getById(uid);
    },
    async getByStripeCustomerId(customerId) {
      if (!customerId) return null;
      const uid = await store.get(`stripe:${customerId}`);
      if (!uid) return null;
      return this.getById(uid);
    },
    async put(record) {
      await store.set(`id:${record.id}`, JSON.stringify(record));
      await store.set(`email:${normalizeEmail(record.email)}`, record.id);
      if (record.stripe_customer_id) {
        await store.set(`stripe:${record.stripe_customer_id}`, record.id);
      }
    },
    async putCheckout(sessionId, payload) {
      await store.set(`checkout:${sessionId}`, JSON.stringify(payload));
    },
    async getCheckout(sessionId) {
      const raw = await store.get(`checkout:${sessionId}`);
      if (!raw) return null;
      return typeof raw === "string" ? JSON.parse(raw) : raw;
    },
    async deleteCheckout(sessionId) {
      if (typeof store.delete === "function") {
        await store.delete(`checkout:${sessionId}`);
        return;
      }
      await store.set(`checkout:${sessionId}`, "");
    },
    async markUsed(nonce) {
      await store.set(`used:${nonce}`, "1");
    },
    async isUsed(nonce) {
      const raw = await store.get(`used:${nonce}`);
      return Boolean(raw);
    },
    async claimNonce(nonce) {
      const result = await store.set(`used:${nonce}`, "1", { onlyIfNew: true });
      return blobWriteCreatedEntry(result);
    },
    async upsertByEmail(email, extra = {}) {
      const normalized = normalizeEmail(email);
      const existing = await this.getByEmail(normalized);
      if (existing) {
        const merged = { ...existing, ...extra, id: existing.id, email: normalized, kind: "consumer" };
        await this.put(merged);
        return merged;
      }
      const id = newConsumerId();
      const rec = emptyRecord({ id, email: normalized, ...extra });
      const created = await store.set(`email:${normalized}`, id, { onlyIfNew: true });
      if (!blobWriteCreatedEntry(created)) {
        const raced = await this.getByEmail(normalized);
        if (raced) {
          const merged = { ...raced, ...extra, id: raced.id, email: normalized, kind: "consumer" };
          await this.put(merged);
          return merged;
        }
        throw new Error("blob upsertByEmail lost the race");
      }
      await store.set(`id:${id}`, JSON.stringify(rec));
      return rec;
    },
  };
}

let _backend = null;
let _blobFactory = blobBackend;
let _blobsModule = null;
let _blobsEvent = null;

function setBlobFactoryForTests(fn) {
  _blobFactory = typeof fn === "function" ? fn : blobBackend;
}

function setBlobsModuleForTests(mod) {
  _blobsModule = mod || null;
}

function clearBackendForTests() {
  _backend = null;
  _blobsEvent = null;
}

function connectBlobsFromEvent(event) {
  if (process.env.MTF_USER_STORE === "memory") return false;
  if (!event || !event.blobs) return false;
  _blobsEvent = event;
  const blobs = _blobsModule || require("@netlify/blobs");
  if (typeof blobs.connectLambda !== "function") return false;
  blobs.connectLambda(event);
  return true;
}

function getBackend() {
  if (_backend) return _backend;
  if (process.env.MTF_USER_STORE === "memory") {
    _backend = memoryBackend();
    return _backend;
  }
  _backend = _blobFactory();
  return _backend;
}

function resetMemoryStore() {
  _backend = memoryBackend();
  return _backend;
}

function setBackendForTests(backend) {
  _backend = backend;
}

async function getById(id) {
  if (!id) return null;
  return getBackend().getById(id);
}

async function getByEmail(email) {
  const normalized = normalizeEmail(email);
  if (!normalized) return null;
  return getBackend().getByEmail(normalized);
}

async function put(record) {
  if (!record || !record.id) throw new Error("user record requires id");
  if (isReservedId(record.id)) {
    throw new Error("refusing to store reserved internal id");
  }
  const stored = emptyRecord({
    ...record,
    email: normalizeEmail(record.email),
    kind: "consumer",
  });
  await getBackend().put(stored);
  return stored;
}

async function upsertByEmail(email, extra = {}) {
  const normalized = normalizeEmail(email);
  if (!normalized) throw new Error("email required");
  const backend = getBackend();
  if (typeof backend.upsertByEmail === "function") {
    return backend.upsertByEmail(normalized, extra);
  }
  const existing = await getByEmail(normalized);
  if (existing) {
    const merged = { ...existing, ...extra, id: existing.id, email: normalized, kind: "consumer" };
    return put(merged);
  }
  return put(
    emptyRecord({
      id: newConsumerId(),
      email: normalized,
      ...extra,
    })
  );
}

async function claimNonce(nonce) {
  const backend = getBackend();
  if (typeof backend.claimNonce === "function") {
    return backend.claimNonce(nonce);
  }
  if (await backend.isUsed(nonce)) return false;
  await backend.markUsed(nonce);
  return true;
}

async function markNonceUsed(nonce) {
  await getBackend().markUsed(nonce);
}

async function isNonceUsed(nonce) {
  return getBackend().isUsed(nonce);
}

async function getByStripeCustomerId(customerId) {
  if (!customerId) return null;
  const backend = getBackend();
  if (typeof backend.getByStripeCustomerId === "function") {
    return backend.getByStripeCustomerId(customerId);
  }
  return null;
}

async function putCheckout(sessionId, payload) {
  if (!sessionId) throw new Error("checkout session id required");
  return getBackend().putCheckout(sessionId, payload);
}

async function getCheckout(sessionId) {
  if (!sessionId) return null;
  return getBackend().getCheckout(sessionId);
}

async function deleteCheckout(sessionId) {
  if (!sessionId) return;
  return getBackend().deleteCheckout(sessionId);
}

module.exports = {
  BLOB_STORE_NAME,
  normalizeEmail,
  isReservedId,
  newConsumerId,
  getById,
  getByEmail,
  getByStripeCustomerId,
  put,
  upsertByEmail,
  putCheckout,
  getCheckout,
  deleteCheckout,
  claimNonce,
  markNonceUsed,
  isNonceUsed,
  resetMemoryStore,
  setBackendForTests,
  setBlobFactoryForTests,
  setBlobsModuleForTests,
  clearBackendForTests,
  connectBlobsFromEvent,
  getBackend,
  blobWriteCreatedEntry,
};
