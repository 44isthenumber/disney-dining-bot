/**
 * Normalize consumer mobile numbers to E.164 for Twilio.
 * US is the default: 10 digits or 11 starting with 1 → +1XXXXXXXXXX.
 * A leading + with 8–15 digits is international E.164 unless the US path matched.
 *
 * Display helpers live here too so the checkout field and the API agree:
 * strip non-digits for validation; format US numbers as (XXX) XXX-XXXX.
 */
function digitsOnly(raw) {
  return String(raw == null ? "" : raw).replace(/\D/g, "");
}

function looksLikePhone(raw) {
  const s = String(raw == null ? "" : raw).trim();
  if (!s || /[A-Za-z]/.test(s)) return false;
  const digits = digitsOnly(s);
  if (digits.length === 10) return true;
  if (digits.length === 11 && digits[0] === "1") return true;
  return s[0] === "+" && digits.length >= 8 && digits.length <= 15;
}

function formatUsPhoneDisplay(raw) {
  const s = String(raw == null ? "" : raw);
  const trimmed = s.trim();
  if (!trimmed) return "";
  if (trimmed.charAt(0) === "+" && !/^\+1/.test(trimmed)) return trimmed;
  let digits = digitsOnly(trimmed);
  if (digits.length >= 11 && digits.charAt(0) === "1") digits = digits.slice(1);
  digits = digits.slice(0, 10);
  if (!digits) return trimmed.charAt(0) === "+" ? "+" : "";
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

function normalizePhone(raw) {
  const s = String(raw == null ? "" : raw).trim();
  if (!s) return { ok: true, phone: "" };
  if (/[A-Za-z]/.test(s)) {
    return { ok: false, detail: "Use a 10-digit US mobile number." };
  }
  const hasPlus = s[0] === "+";
  const digits = digitsOnly(s);
  if (!digits) {
    return { ok: false, detail: "Use a 10-digit US mobile number." };
  }
  if (digits.length === 10) {
    return { ok: true, phone: "+1" + digits };
  }
  if (digits.length === 11 && digits[0] === "1") {
    return { ok: true, phone: "+" + digits };
  }
  if (hasPlus && digits.length >= 8 && digits.length <= 15) {
    return { ok: true, phone: "+" + digits };
  }
  return { ok: false, detail: "Use a 10-digit US mobile number." };
}

module.exports = { digitsOnly, looksLikePhone, formatUsPhoneDisplay, normalizePhone };
