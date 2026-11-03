"""Local dashboard server. Speaks the same `/api?op=...` contract as the Vercel functions (vercel/api/index.js),
so dashboard/static/index.html works unchanged in both places."""
import hashlib
import hmac
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from engine.assistant import Assistant, AssistantError, build_context
from engine.config import load_config
from engine.report import build_report
from engine.runner import DATA
from engine.storage import Store
from engine.summary import summarize

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
CFG = load_config(os.environ.get("NARDJIS_CONFIG") or str(ROOT / "config.yaml"))
RESTS = {r["id"]: r for r in CFG["restaurants"]}
AI = Assistant.from_config(CFG["gemini"])
CODE = CFG["access_code"]
TOKEN = hmac.new(CODE.encode(), b"nardjis-session", hashlib.sha256).hexdigest() if CODE else ""
COOKIE = "nsess"
PUBLIC_OPS = ("auth", "login", "logout")

app = FastAPI(title="Nardjis Solutions")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_fails = defaultdict(deque)
_asks = deque()


def _authed(request: Request):
    return not CODE or hmac.compare_digest(request.cookies.get(COOKIE, ""), TOKEN)


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path == "/api" and request.query_params.get("op") not in PUBLIC_OPS and not _authed(request):
        return JSONResponse({"error": "auth"}, status_code=401)
    resp = await call_next(request)
    if request.url.path == "/api":
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ------------------------------------------------------------------ operations
def op_auth(request):
    return {"required": bool(CODE), "ok": _authed(request), "configured": True}


def op_login(code, request):
    ip = request.client.host if request.client else "?"
    q, now = _fails[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 5:
        raise HTTPException(429, "too many attempts")
    if not CODE or not hmac.compare_digest(code.encode(), CODE.encode()):
        q.append(now)
        raise HTTPException(401, "wrong code")
    r = JSONResponse({"ok": True})
    r.set_cookie(COOKIE, TOKEN, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return r


def op_logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r


def _state(rid):
    try:
        return json.loads((DATA / rid / "state.json").read_text())
    except Exception:
        return None


def _rest(rid):
    if rid not in RESTS:
        raise HTTPException(404, "unknown restaurant")
    return RESTS[rid]


def _summary(r):
    s = _state(r["id"])
    if not s:
        return {"id": r["id"], "name": r["name"], "online": False, "starting": True}
    return {**summarize(r["id"], r["name"], s), "online": time.time() - s["meta"]["generated_at"] < 20}


def op_overview():
    rs = [_summary(r) for r in CFG["restaurants"]]
    live = [x for x in rs if x.get("kpi")]
    served = sum(x["kpi"]["served"] for x in live)
    avg = (sum((x["kpi"]["avg_wait"] or 0) * x["kpi"]["served"] for x in live) / served) if served else None
    staff = sorted((p for x in live for p in x["staff"]), key=lambda p: -p["effort"])[:5]
    return {
        "restaurants": rs,
        "group": {
            "count": len(rs), "online": sum(1 for x in rs if x.get("online")),
            "attention": sum(x["kpi"]["attention"] for x in live),
            "alerts": sum(x["kpi"]["alerts"] for x in live),
            "abandoned": sum(x["kpi"]["abandoned"] for x in live),
            "avg_wait": avg, "top_staff": [p for p in staff if p["effort"] > 0],
        },
        "ai": AI.enabled,
    }


def op_state(rid):
    _rest(rid)
    s = _state(rid)
    return s if s else {"waiting": True}


def op_report(rid, lang):
    _rest(rid)
    return PlainTextResponse(build_report(Store(str(DATA / rid / "nardjis.db")), _state(rid), lang))


def op_live(rid):
    _rest(rid)
    p = DATA / rid / "live.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "no-store"})


def _context(scope):
    rs = list(RESTS.values()) if scope == "all" else [_rest(scope)]
    items = [(r["name"], s) for r in rs if (s := _state(r["id"]))]
    if not items:
        raise HTTPException(503, "no data yet")
    return build_context(items)


def _run_ai(fn):
    now = time.time()
    while _asks and now - _asks[0] > 60:
        _asks.popleft()
    if len(_asks) >= 15:
        return JSONResponse({"error": "busy"}, status_code=429)
    _asks.append(now)
    try:
        return {"answer": fn()}
    except AssistantError as e:
        return JSONResponse({"error": e.code}, status_code={"no_key": 503, "quota": 429}.get(e.code, 502))


# ---------------------------------------------------------------------- routes
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api")
def api_get(request: Request, op: str = "", id: str = "", lang: str = "fr"):
    if op == "auth":
        return op_auth(request)
    if op == "overview":
        return op_overview()
    if op == "state":
        return op_state(id)
    if op == "report":
        return op_report(id, lang)
    if op == "live":
        return op_live(id)
    raise HTTPException(404, "unknown op")


@app.post("/api")
async def api_post(request: Request, op: str = ""):
    try:
        body = await request.json()
        body = body if isinstance(body, dict) else {}
    except Exception:
        body = {}
    if op == "login":
        return op_login(str(body.get("code", "")), request)
    if op == "logout":
        return op_logout()
    if op in ("ask", "insights"):
        q, scope, lang = str(body.get("question", ""))[:600], str(body.get("restaurant", "all")), str(body.get("lang", "fr"))
        if op == "ask" and not q.strip():
            raise HTTPException(400, "empty question")
        ctx = await run_in_threadpool(_context, scope)
        call = (lambda: AI.ask(q, ctx, lang)) if op == "ask" else (lambda: AI.insights(ctx, lang))
        return await run_in_threadpool(_run_ai, call)
    raise HTTPException(404, "unknown op")
