#!/usr/bin/env node
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const {
  digitsOnly,
  looksLikePhone,
  formatUsPhoneDisplay,
  normalizePhone,
} = require("../netlify/functions/phone");

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

// Craig repro: raw 10-digit US number typed in checkout.
assert.deepStrictEqual(normalizePhone("2564252474"), { ok: true, phone: "+12564252474" });
assert.deepStrictEqual(normalizePhone("(256) 425-2474"), { ok: true, phone: "+12564252474" });
assert.deepStrictEqual(normalizePhone("+1 256 425 2474"), { ok: true, phone: "+12564252474" });
assert.deepStrictEqual(normalizePhone("1-256-425-2474"), { ok: true, phone: "+12564252474" });
assert.strictEqual(looksLikePhone("2564252474"), true);
assert.strictEqual(looksLikePhone("(256) 425-2474"), true);
assert.strictEqual(looksLikePhone("+12564252474"), true);
assert.strictEqual(looksLikePhone(""), false);
assert.strictEqual(looksLikePhone("2564252"), false);
assert.strictEqual(looksLikePhone("abc"), false);
assert.strictEqual(digitsOnly("(256) 425-2474"), "2564252474");

assert.strictEqual(formatUsPhoneDisplay("2564252474"), "(256) 425-2474");
assert.strictEqual(formatUsPhoneDisplay("256425247"), "(256) 425-247");
assert.strictEqual(formatUsPhoneDisplay("2564"), "(256) 4");
assert.strictEqual(formatUsPhoneDisplay("256"), "256");
assert.strictEqual(formatUsPhoneDisplay("+12564252474"), "(256) 425-2474");
assert.strictEqual(formatUsPhoneDisplay("1 (256) 425-2474"), "(256) 425-2474");
assert.strictEqual(formatUsPhoneDisplay("+447700900000"), "+447700900000");
assert.strictEqual(formatUsPhoneDisplay(""), "");

function extractFunction(source, name) {
  const start = source.indexOf("function " + name + "(");
  assert.ok(start >= 0, "missing function " + name);
  let i = source.indexOf("{", start);
  assert.ok(i >= 0, "missing body for " + name);
  let depth = 0;
  for (; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error("unclosed function " + name);
}

const html = fs.readFileSync(path.join(__dirname, "../public/index.html"), "utf8");
const frontendLooksLikePhone = new Function("return " + extractFunction(html, "looksLikePhone"))();
const frontendFormat = new Function("return " + extractFunction(html, "formatUsPhoneDisplay"))();
const cases = [
  "2564252474",
  "(256) 425-2474",
  "+1 256-425-2474",
  "12564252474",
  "+447700900000",
  "",
  "2564",
  "abc",
];
for (const value of cases) {
  assert.strictEqual(frontendLooksLikePhone(value), looksLikePhone(value), "looksLikePhone " + value);
  assert.strictEqual(frontendFormat(value), formatUsPhoneDisplay(value), "formatUsPhoneDisplay " + value);
}

console.log("test_phone ok");
