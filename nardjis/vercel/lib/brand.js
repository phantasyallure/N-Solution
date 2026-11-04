"use strict";
// Platform name shared by every page. Stored in Supabase (table nj_settings, key "brand").
//   GET  /api?op=brand      -> { name }            (public)
//   POST /api?op=brand_set  -> { ok, name }        (admin session only)
//   GET  /api?op=pricing      -> { currency, plans }  (public, shown on the homepage; key "pricing")
//   POST /api?op=pricing_set  -> { ok, ...pricing }   (admin session only)
const crypto = require("crypto");

const CURRENCIES = ["DZD", "EUR", "USD", "MAD", "TND"];
const txt = (v, n) => String(v == null ? "" : v).replace(/[<>"&]/g, "").replace(/\s+/g, " ").trim().slice(0, n);
const price = (v) => { const n = Math.round(Number(v) * 100) / 100; return Number.isFinite(n) && n >= 0 && n <= 1e9 ? n : 0; };
// Keeps only what the homepage can display: max 4 plans, 10 features each, plain text only.
function cleanPricing(b) {
  b = b && typeof b === "object" ? b : {};
  const plans = (Array.isArray(b.plans) ? b.plans : []).filter((p) => p && txt(p.name, 40)).slice(0, 4).map((p, i) => ({
    id: "p" + (i + 1), name: txt(p && p.name, 40), desc: txt(p && p.desc, 120),
    monthly: price(p && p.monthly), yearly: price(p && p.yearly),
    features: (Array.isArray(p && p.features) ? p.features : []).map((f) => txt(f, 90)).filter(Boolean).slice(0, 10),
    featured: !!(p && p.featured),
  }));
  let seen = false;   // only one highlighted plan
  plans.forEach((p) => { if (p.featured && seen) p.featured = false; seen = seen || p.featured; });
  return { currency: CURRENCIES.includes(b.currency) ? b.currency : "DZD", plans };
}

function withBrand(handler, env, fetchFn) {
  const DEFAULT = (env.PLATFORM_NAME || "Nardjis").trim() || "Nardjis";
  const code = env.ACCESS_CODE || "";
  const token = code ? crypto.createHmac("sha256", code).update("nardjis-session").digest("hex") : "";
  const sbUrl = (env.SUPABASE_URL || "").replace(/\/+$/, "");
  const sbKey = env.SUPABASE_SERVICE_KEY || "";
  let cache = { name: DEFAULT, at: 0 };

  const h256 = (x) => crypto.createHash("sha256").update(String(x)).digest();
  const same = (a, b) => crypto.timingSafeEqual(h256(a), h256(b));
  const authed = (req) => {
    const m = /(?:^|;\s*)nsess=([^;]*)/.exec(req.headers.cookie || "");
    return !!code && !!m && same(m[1], token);
  };
  const db = async (path, opt = {}) => {
    const headers = { apikey: sbKey, ...(opt.headers || {}) };
    if (sbKey.startsWith("eyJ")) headers.Authorization = `Bearer ${sbKey}`;
    const r = await fetchFn(`${sbUrl}/rest/v1/${path}`, { ...opt, headers });
    if (!r.ok) throw new Error(`db ${r.status}`);
    return r.status === 204 ? null : r.json();
  };
  async function getName() {
    if (Date.now() - cache.at < 15000) return cache.name;
    let name = DEFAULT;
    if (sbUrl && sbKey) {
      try {
        const rows = await db("nj_settings?select=value&key=eq.brand");
        const n = rows && rows[0] && rows[0].value && rows[0].value.name;
        if (typeof n === "string" && n.trim()) name = n.trim();
      } catch { /* table not created yet -> default name */ }
    }
    cache = { name, at: Date.now() };
    return name;
  }
  const json = (res, status, body) => {
    res.statusCode = status;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.setHeader("Cache-Control", "no-store");
    res.end(JSON.stringify(body));
  };
  const readBody = async (req) => {
    if (req.body !== undefined && req.body !== null) {
      if (typeof req.body === "string") { try { return JSON.parse(req.body); } catch { return {}; } }
      return typeof req.body === "object" ? req.body : {};
    }
    const chunks = [];
    for await (const c of req) chunks.push(c);
    try { return JSON.parse(Buffer.concat(chunks).toString() || "{}"); } catch { return {}; }
  };

  return async function (req, res) {
    try {
      const op = new URL(req.url, "http://x").searchParams.get("op") || "";
      if (op === "brand" && req.method !== "POST") return json(res, 200, { name: await getName() });
      if (op === "brand_set" && req.method === "POST") {
        if (!authed(req)) return json(res, 401, { error: "auth" });
        if (!sbUrl || !sbKey) return json(res, 503, { error: "supabase_not_configured" });
        const b = await readBody(req);
        const name = String(b.name || "").replace(/[<>"&]/g, "").replace(/\s+/g, " ").trim().slice(0, 40);
        if (!name) return json(res, 400, { error: "invalid" });
        try {
          await db("nj_settings?on_conflict=key", {
            method: "POST",
            headers: { "Content-Type": "application/json", Prefer: "resolution=merge-duplicates,return=minimal" },
            body: JSON.stringify({ key: "brand", value: { name } }),
          });
        } catch { return json(res, 500, { error: "setup" }); }   // nj_settings table missing
        cache = { name, at: Date.now() };
        return json(res, 200, { ok: true, name });
      }
      if (op === "pricing" && req.method !==
