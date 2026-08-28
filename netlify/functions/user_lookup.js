/** Resolve a typed username to a configured user. No silent fallback. */

function findUser(users, requested) {
  if (!users || requested == null) return null;
  const key = String(requested).trim();
  if (!key) return null;
  if (users[key]) return users[key];
  const lower = key.toLowerCase();
  return Object.values(users).find(function (u) {
    if (!u) return false;
    if (String(u.id || "").toLowerCase() === lower) return true;
    if (String(u.name || "").toLowerCase() === lower) return true;
    return false;
  }) || null;
}

module.exports = { findUser };
