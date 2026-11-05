"use strict";
let handler, loadError;
try {
  const { createHandler } = require("../lib/core");
  const { withBrand } = require("../lib/brand");
  handler = withBrand(createHandler({ env: process.env, fetch: globalThis.fetch }), process.env, globalThis.fetch);
} catch (e) { loadError = e; }

module.exports = async (req, res) => {
  const fail = (label, e) => { res.statusCode = 500; res.setHeader("Content-Type", "text/plain"); res.end(label + ": " + (e && e.stack || e)); };
  if (loadError) return fail("LOAD ERROR", loadError);
  try { return await handler(req, res); } catch (e) { return fail("RUNTIME ERROR", e); }
};
