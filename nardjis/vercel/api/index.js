"use strict";
// Single serverless function: Vercel's free plan limits the number of functions, so everything goes through /api?op=...
const { createHandler } = require("../lib/core");
const { withBrand } = require("../lib/brand");

module.exports = withBrand(createHandler({ env: process.env, fetch: globalThis.fetch }), process.env, globalThis.fetch);
