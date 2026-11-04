"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { cleanPricing } = require("../lib/brand");

test("pricing: strips markup, caps plans and keeps one highlight", () => {
  const p = cleanPricing({ currency: "XXX", plans: [
    { name: "<b>Pro", monthly: "49.9", yearly: 490, features: ["a", "", " b "], featured: true },
    { name: "Max", featured: true }, { name: "" }, { name: "C" }, { name: "D" }, { name: "E" }] });
  assert.equal(p.currency, "DZD");
  assert.equal(p.plans.length, 4);
  assert.equal(p.plans[0].name, "bPro");
  assert.deepEqual(p.plans[0].features, ["a", "b"]);
  assert.equal(p.plans.filter((x) => x.featured).length, 1);
});
test("pricing: bad input gives an empty list", () => {
  assert.deepEqual(cleanPricing(null), { currency: "DZD", plans: [] });
});
