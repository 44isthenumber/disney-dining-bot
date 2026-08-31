/**
 * Normalize consumer mobile numbers to E.164 for Twilio.
 * US is the default: 10 digits or 11 starting with 1 → +1XXXXXXXXXX.
 * A leading + with 8–15 digits is international E.164 unless the US path matched.
 */
function normalizePhone(raw) {
  const s = String(raw == null ? "" : raw).trim();
  if (!s) return { ok: true, phone: "" };
  if (/[A-Za-z]/.test(s)) {
    return { ok: false, detail: "Use a 10-digit US mobile number." };
  }
  const hasPlus = s[0] === "+";
  const digits = s.replace(/\D/g, "");
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

module.exports = { normalizePhone };
