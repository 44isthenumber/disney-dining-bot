#!/usr/bin/env node
const assert = require("assert");
const { normalizePhone } = require("../netlify/functions/phone");

assert.deepStrictEqual(normalizePhone(""), { ok: true, phone: "" });
assert.deepStrictEqual(normalizePhone("   "), { ok: true, phone: "" });
assert.deepStrictEqual(normalizePhone("5551234567"), { ok: true, phone: "+15551234567" });
assert.deepStrictEqual(normalizePhone("(555) 123-4567"), { ok: true, phone: "+15551234567" });
assert.deepStrictEqual(normalizePhone("555-123-4567"), { ok: true, phone: "+15551234567" });
assert.deepStrictEqual(normalizePhone("+15551234567"), { ok: true, phone: "+15551234567" });
assert.deepStrictEqual(normalizePhone("15551234567"), { ok: true, phone: "+15551234567" });
assert.strictEqual(normalizePhone("abc").ok, false);
assert.strictEqual(normalizePhone("abc").detail, "Use a 10-digit US mobile number.");
assert.strictEqual(normalizePhone("12345").ok, false);
assert.strictEqual(normalizePhone("555abc1234567").ok, false);
assert.strictEqual(normalizePhone("+12abc345678").ok, false);

const intl = normalizePhone("+447700900000");
assert.strictEqual(intl.ok, true);
assert.strictEqual(intl.phone, "+447700900000");

console.log("test_phone ok");
