#!/usr/bin/env node
const assert = require("assert");
const { findUser } = require("../netlify/functions/user_lookup");

const users = {
  craig: { id: "craig", name: "Craig" },
  Jessica: { id: "Jessica", name: "Jessica" },
};

assert.strictEqual(findUser(users, "craig").id, "craig");
assert.strictEqual(findUser(users, "Craig").id, "craig");
assert.strictEqual(findUser(users, "JESSICA").id, "Jessica");
assert.strictEqual(findUser(users, " jessica ").id, "Jessica");
assert.strictEqual(findUser(users, "nobody"), null);
assert.strictEqual(findUser(users, ""), null);
assert.strictEqual(findUser(users, "  "), null);
console.log("test_user_lookup ok");
