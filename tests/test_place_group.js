#!/usr/bin/env node
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(path.join(__dirname, "../public/index.html"), "utf8");
const match = html.match(/function placeGroup\(r\) \{[\s\S]*?\n\}/);
assert.ok(match, "placeGroup function missing from public/index.html");
eval(match[0]);

assert.strictEqual(placeGroup({ park: "" }), "Other");
assert.strictEqual(placeGroup({ park: "ESPN Wide World of Sports Complex" }), "Other");
assert.strictEqual(placeGroup({ park: "Magic Kingdom Park" }), "Magic Kingdom");
assert.strictEqual(placeGroup({ park: "EPCOT" }), "EPCOT");
assert.strictEqual(placeGroup({ park: "EPCOT Resort Area" }), "Resorts");
assert.strictEqual(placeGroup({ park: "Disney's Hollywood Studios" }), "Hollywood Studios");
assert.strictEqual(placeGroup({ park: "Disney's Animal Kingdom Theme Park" }), "Animal Kingdom");
assert.strictEqual(placeGroup({ park: "Disney's Animal Kingdom Lodge" }), "Resorts");
assert.strictEqual(placeGroup({ park: "Disney's Animal Kingdom Resort Area" }), "Resorts");
assert.strictEqual(placeGroup({ park: "Disney Springs" }), "Disney Springs");
assert.strictEqual(placeGroup({ park: "Disney Springs Resort Area" }), "Disney Springs");
assert.strictEqual(placeGroup({ park: "Disney's Grand Floridian Resort & Spa" }), "Resorts");
assert.strictEqual(placeGroup({ park: "Disney's BoardWalk" }), "Resorts");
assert.strictEqual(placeGroup({ park: "Vero Beach Resort Area" }), "Resorts");

const restaurants = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../restaurants.json"), "utf8")
).restaurants;
const allowed = {
  "Magic Kingdom": true,
  EPCOT: true,
  "Hollywood Studios": true,
  "Animal Kingdom": true,
  "Disney Springs": true,
  Resorts: true,
  Other: true,
};
restaurants.forEach(function (r) {
  const g = placeGroup(r);
  assert.ok(allowed[g], "unexpected group " + g + " for park " + JSON.stringify(r.park));
});

console.log("test_place_group ok");
