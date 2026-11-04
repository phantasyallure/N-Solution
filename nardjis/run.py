"""Nardjis Solutions - entry point (one process, one or many restaurants).

  python run.py --demo                 # 3 simulated restaurants, no camera needed
  python run.py                        # live cameras from config.yaml
  python run.py --only oran-centre --source http://192.168.1.25:8080/video   # test one restaurant with a phone

Cloud: put SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment or in a .env file and the numbers are
also pushed to Supabase, so a dashboard on Vercel can show them. Add --headless on the restaurant computer
if you do not need the local dashboard.
"""
import argparse
import os
import threading
from pathlib import Path

from engine.config import load_config
from engine.core import Engine
from engine.notifier import Notifier
from engine.runner import restaurant_dir, run_demo, run_live
from engine.storage import Store

ROOT = Path(__file__).resolve().parent


def load_env(path):
    """Tiny .env reader (KEY=value per line). Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def start_restaurant(r, demo, speed, stop, cloud=None):
    d = restaurant_dir(r["id"])
    store = Store(str(d / "nardjis.db"))
    notifier = Notifier(r.get("telegram"), r["language"], r["name"])
    hooks = []

    def on_event(ev):
        store.add(ev)
        notifier.handle(ev)
        if cloud:
            cloud.push_event(r["id"], ev)
        for h in hooks:
            h(ev)

    engine = Engine(r["tables"], r.get("thresholds"), r["staff_names"], on_event)
    meta = {"id": r["id"], "restaurant": r["name"], "mode": "demo" if demo else "live",
            "speed": speed if demo else 1, "language": r["language"],
            "patience_limit": engine.cfg["patience_limit"], "dirty_after": engine.cfg["dirty_after"]}
    state_path = d / "state.json"
    sink = (lambda snap: cloud.push_state(r["id"], r["name"], snap)) if cloud else None
    if demo:
        from engine.demo import Sim
        dm = r["demo"]
        sim = Sim(engine, seed=dm.get("seed", 7), attention=dm.get("attention", 1.0))
        hooks.append(sim.on_event)
        target = lambda: run_demo(engine, sim, meta, stop, speed, state_path, sink)
    else:
        from engine.vision import Vision
        vision = Vision(r)
        target = lambda: run_live(engine, vision, r["camera"], meta, stop, state_path, d / "live.jpg", sink)
    threading.Thread(target=target, daemon=True, name=r["id"]).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--demo", action="store_true", help="run with simulated restaurants")
    ap.add_argument("--speed", type=int, default=20, help="demo time acceleration")
    ap.add_argument("--only", help="run only this restaurant id")
    ap.add_argument("--source", help="camera source override (use with --only)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--headless", action="store_true", help="no local dashboard (engine only, e.g. cloud mode)")
    a = ap.parse_args()

    load_env(ROOT / ".env")
    cfg = load_config(a.config)
    rests = [r for r in cfg["restaurants"] if not a.only or r["id"] == a.only]
    if not rests:
        raise SystemExit(f"no restaurant with id {a.only!r}")
    if a.source:
        if len(rests) != 1:
            raise SystemExit("--source needs --only <restaurant id>")
        rests[0]["camera"]["source"] = int(a.source) if a.source.isdigit() else a.source

    cloud = None
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
        from engine.cloud import Cloud
        cloud = Cloud.from_env()
        print(f"  cloud: publishing to {cloud.url}", flush=True)
    os.environ["NARDJIS_CONFIG"] = a.config
    stop = threading.Event()
    for r in rests:
        if cloud and not cloud.register(r["id"], r["name"]):
            print("  ! check SUPABASE_URL / SUPABASE_SERVICE_KEY and that vercel/supabase.sql was run", flush=True)
        start_restaurant(r, a.demo, a.speed, stop, cloud)
        print(f"  started: {r['name']} ({r['id']})", flush=True)

    if a.headless:
        print("\n  Nardjis engine running (headless). Ctrl+C to stop.\n", flush=True)
        try:
            stop.wait()
        except KeyboardInterrupt:
            pass
        return
    import uvicorn
    if not cfg["access_code"]:
        print("  ! no access_code set: anyone on your network can open the dashboard", flush=True)
    print(f"\n  Nardjis Solutions -> http://localhost:{a.port}\n", flush=True)
    uvicorn.run("dashboard.app:app", host=a.host, port=a.port, log_level="warning")
    stop.set()


if __name__ == "__main__":
    main()
