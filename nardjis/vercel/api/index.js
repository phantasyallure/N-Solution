"use strict";
// Single serverless function: Vercel's free plan limits the number of functions, so everything goes through /api?op=...
const { createHandler } = require("../lib/core");

module.exports = createHandler({ env: process.env, fetch: globalThis.fetch });
