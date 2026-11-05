"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { createHandler, groupOverview, buildContext, buildReport, midnightISO, gemini } = require("../lib/core");

const KPI = { attention: 1, longest_wait_now: 120, avg_wait: 180, served: 10, abandoned: 1, alerts: 4 };
const summary = (name, extra = {}) => ({
  id: name, name, mode: "demo", speed: 20, health: 80, kpi: KPI, tables: [{ state: "free", level: "ok" }],
  top: { name: "Amine", effort: 50 }, staff: [{ name: "Amine", effort: 50, restaurant: name }], ...extra,
});
const STATE = {
  meta: { mode: "demo", patience_limit: 600 }, kpi: KPI,
  tables: [{ name: "T1", state: "waiting", level: "warn", clients: 2, wait: 300, dirty: 0, polygon: [[0, 0]], center: [0, 0] }],
  staff: [{ name: "Amine", status: "ready", visits: 3, tasks_done: 3, distance_m: 12, active_pct: 40, avg_response: 90, effort: 50 }],
  waits: [{ table: "T1", seconds: 240, kind: "served", staff: "Amine" }], events: [{ type: "served" }, { type: "served" }],
};

function fakeFetch(routes) {
  const calls = [];
  const f = async (url, opt = {}) => {
    calls.push({ url: String(url), opt });
    for (const [needle, reply] of routes) {
      if (String(url).includes(needle)) {
        const [status, body] = typeof reply === "function" ? reply(url, opt) : reply;
        return { ok: status < 300, status, json: async () => body };
      }
    }
    return { ok: false, status: 404, json: async () => ({}) };
  };
  f.calls = calls;
  return f;
}
const mkRes = () => ({ headers: {}, setHeader(k, v) { this.headers[k] = v; }, end(b) { this.body = b; } });
async function call(handler, { method = "GET", url, body, cookie } = {}) {
  const res = mkRes();
  await handler({ method, url, headers: { cookie: cookie || "", "x-forwarded-for": "1.2.3.4" }, body }, res);
  let json = null;
  try { json = JSON.parse(res.body); } catch {}
  return { status: res.statusCode, json, text: res.body, headers: res.headers };
}
const ENV = { ACCESS_CODE: "s3cret", SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_KEY: "sb_secret_k", GEMINI_API_KEY: "G" };

test("group overview aggregates restaurants (weighted average wait, top staff)", () => {
  const a = summary("A", { kpi: { ...KPI, served: 10, avg_wait: 100 } });
  const b = summary("B", { kpi: { ...KPI, served: 30, avg_wait: 200 }, online: true, staff: [{ name: "Nour", effort: 90, restaurant: "B" }] });
  const g = groupOverview([{ ...a, online: true }, b, { id: "C", name: "C", online: false, starting: true }], true);
  assert.equal(g.group.count, 3); assert.equal(g.group.online, 2);
  assert.equal(g.group.avg_wait, 175); assert.equal(g.group.alerts, 8);
  assert.equal(g.group.top_staff[0].name, "Nour"); assert.equal(g.ai, true);
});

test("context sent to Gemini has numbers but no coordinates", () => {
  const c = buildContext([["Oran", STATE]]);
  assert.match(c, /"restaurant":"Oran"/); assert.doesNotMatch(c, /polygon|center/);
  assert.equal(JSON.parse(c)[0].kpi.avg_wait_min, 3);
});

test("daily report", () => {
  const ev = [
    { type: "served", table_name: "T1", seconds: 120 }, { type: "served", table_name: "T3", seconds: 300 },
    { type: "cleaned", table_name: "T1", seconds: 60 }, { type: "left_unserved", table_name: "T2", seconds: 900 },
    { type: "task_wait", table_name: "T3", seconds: 300 }, { type: "escalate_wait", table_name: "T3", seconds: 600 },
  ];
  const r = buildReport(ev, STATE, "en");
  assert.match(r, /Clients served: 2/); assert.match(r, /Average wait: 3\.5 min/);
  assert.match(r, /Longest wait: 5\.0 min \(T3\)/); assert.match(r, /left unserved: 1/); assert.match(r, /Alerts sent: 2/);
  assert.match(r, /Top effort: Amine/);
  assert.match(buildReport([], null, "fr"), /Clients servis: 0/);
});

test("midnight is computed in the restaurant timezone", () => {
  const now = new Date("2026-11-03T12:30:15.250Z");           // 13:30:15 in Algiers (UTC+1)
  assert.equal(midnightISO("Africa/Algiers", now), "2026-11-02T23:00:00.000Z");
});

test("fails closed without ACCESS_CODE and never touches the database", async () => {
  const f = fakeFetch([]);
  const h = createHandler({ env: { ...ENV, ACCESS_CODE: "" }, fetch: f });
  assert.deepEqual((await call(h, { url: "/api?op=auth" })).json, { required: true, ok: false, configured: false });
  assert.equal((await call(h, { url: "/api?op=overview" })).status, 503);
  assert.equal(f.calls.length, 0);
});

test("login, cookie, rate limit and protected ops", async () => {
  const h = createHandler({ env: ENV, fetch: fakeFetch([]) });
  assert.equal((await call(h, { url: "/api?op=overview" })).status, 401);
  const bad = await call(h, { method: "POST", url: "/api?op=login", body: { code: "nope" } });
  assert.equal(bad.status, 401);
  const ok = await call(h, { method: "POST", url: "/api?op=login", body: { code: "s3cret" } });
  assert.equal(ok.status, 200);
  const cookie = ok.headers["Set-Cookie"].split(";")[0];
  assert.match(ok.headers["Set-Cookie"], /HttpOnly/);
  assert.deepEqual((await call(h, { url: "/api?op=auth", cookie })).json, { required: true, ok: true, configured: true });
  assert.equal((await call(h, { url: "/api?op=auth", cookie: "nsess=forged" })).json.ok, false);
  for (let i = 0; i < 4; i++) await call(h, { method: "POST", url: "/api?op=login", body: { code: "x" } });
  assert.equal((await call(h, { method: "POST", url: "/api?op=login", body: { code: "x" } })).status, 429);
});

async function loggedIn(routes, env = ENV) {
  const f = fakeFetch(routes);
  const h = createHandler({ env, fetch: f });
  const r = await call(h, { method: "POST", url: "/api?op=login", body: { code: "s3cret" } });
  return { h, f, cookie: r.headers["Set-Cookie"].split(";")[0] };
}

test("overview reads small summaries, marks old rows offline, uses apikey only for sb_secret keys", async () => {
  const fresh = new Date().toISOString(), old = new Date(Date.now() - 120000).toISOString();
  const { h, f, cookie } = await loggedIn([
    ["nj_restaurants", [200, [{ id: "a", name: "A" }, { id: "b", name: "B" }, { id: "c", name: "C" }]]],
    ["nj_state", [200, [{ restaurant_id: "a", updated_at: fresh, summary: summary("zzz") }, { restaurant_id: "b", updated_at: old, summary: summary("b") }]]],
  ]);
  const r = await call(h, { url: "/api?op=overview", cookie });
  assert.equal(r.status, 200);
  const [a, b, c] = r.json.restaurants;
  assert.equal(a.name, "A"); assert.equal(a.online, true);       // name comes from nj_restaurants
  assert.equal(b.online, false); assert.equal(c.starting, true);
  assert.equal(r.json.ai, true);
  const sbCall = f.calls.find((c) => c.url.includes("nj_state"));
  assert.ok(sbCall.url.includes("summary") && !sbCall.url.includes("select=*"));
  assert.equal(sbCall.opt.headers.apikey, "sb_secret_k"); assert.equal(sbCall.opt.headers.Authorization, undefined);
});

test("state: validates id, returns waiting when nothing pushed yet", async () => {
  const { h, cookie } = await loggedIn([["nj_state", (u) => [200, u.includes("restaurant_id=eq.a") ? [{ state: STATE }] : []]]]);
  assert.equal((await call(h, { url: "/api?op=state&id=a", cookie })).json.kpi.served, 10);
  assert.deepEqual((await call(h, { url: "/api?op=state&id=b", cookie })).json, { waiting: true });
  assert.equal((await call(h, { url: "/api?op=state&id=" + encodeURIComponent("a&select=*"), cookie })).status, 404);
});

test("database errors become a clean 502, not a crash", async () => {
  const { h, cookie } = await loggedIn([["nj_", [500, {}]]]);
  assert.equal((await call(h, { url: "/api?op=overview", cookie })).status, 502);
});

test("ask: sends restaurant data + question to Gemini, key in header only; falls back across models", async () => {
  const seen = [];
  const { h, cookie } = await loggedIn([
    ["nj_state", [200, [{ restaurant_id: "a", state: STATE }]]],
    ["nj_restaurants", [200, [{ id: "a", name: "Oran Centre" }]]],
    ["gemini-2.5-flash:", [404, {}]],
    ["gemini-2.5-flash-lite:", (u, o) => { seen.push([u, o]); return [200, { candidates: [{ content: { parts: [{ text: "Table T1 attend le plus." }] } }] }]; }],
  ]);
  const r = await call(h, { method: "POST", url: "/api?op=ask", cookie, body: { question: "Quelle table attend ?", restaurant: "a", lang: "fr" } });
  assert.equal(r.status, 200); assert.equal(r.json.answer, "Table T1 attend le plus.");
  const [url, opt] = seen[0];
  assert.ok(!url.includes("key=") && !url.includes("G"));
  assert.equal(opt.headers["x-goog-api-key"], "G");
  const sent = JSON.parse(opt.body).contents[0].parts[0].text;
  assert.match(sent, /Oran Centre/); assert.match(sent, /French/); assert.match(sent, /Quelle table attend/);
});

test("ask: errors are mapped (no key, quota, empty question)", async () => {
  const noKey = await loggedIn([["nj_state", [200, [{ restaurant_id: "a", state: STATE }]]], ["nj_restaurants", [200, []]]], { ...ENV, GEMINI_API_KEY: "" });
  assert.deepEqual((await call(noKey.h, { method: "POST", url: "/api?op=insights", cookie: noKey.cookie, body: { restaurant: "all" } })).json, { error: "no_key" });
  const quota = await loggedIn([["nj_state", [200, [{ restaurant_id: "a", state: STATE }]]], ["nj_restaurants", [200, []]], ["generativelanguage", [429, {}]]]);
  const q = await call(quota.h, { method: "POST", url: "/api?op=ask", cookie: quota.cookie, body: { question: "x", restaurant: "all" } });
  assert.equal(q.status, 429); assert.equal(q.json.error, "quota");
  assert.equal((await call(quota.h, { method: "POST", url: "/api?op=ask", cookie: quota.cookie, body: { question: "  " } })).status, 400);
});

test("report is plain text built from today's events", async () => {
  const { h, f, cookie } = await loggedIn([
    ["nj_events", [200, [{ type: "served", table_name: "T1", staff: "A", seconds: 90 }]]],
    ["nj_state", [200, [{ state: STATE }]]],
  ]);
  const r = await call(h, { url: "/api?op=report&id=a&lang=en", cookie });
  assert.equal(r.status, 200); assert.match(r.text, /Clients served: 1/);
  assert.match(r.headers["Content-Type"], /text\/plain/);
  assert.ok(f.calls.some((c) => c.url.includes("nj_events") && c.url.includes("ts=gte.")));
});

test("gemini(): bad key reports no_key", async () => {
  const f = fakeFetch([["generativelanguage", [400, { error: { message: "API key not valid" } }]]]);
  await assert.rejects(gemini(f, "bad", ["m"], "p"), (e) => e.code === "no_key");
});
