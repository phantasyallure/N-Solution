"""Runs one restaurant (demo simulator or live camera) and publishes its state for the dashboard."""
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("NARDJIS_DATA") or ROOT / "data")


def restaurant_dir(rid):
    d = DATA / rid
    d.mkdir(parents=True, exist_ok=True)
    return d


def publish(engine, meta, path, sink=None):
    snap = engine.snapshot()
    snap["meta"] = {**meta, "generated_at": time.time()}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(snap))
    os.replace(tmp, path)
    if sink:  # e.g. Supabase publisher
        sink(snap)


def run_demo(engine, sim, meta, stop, speed, state_path, sink=None):
    base = time.time()
    last_pub = 0.0
    tick = 0.25
    per_tick = max(1, int(speed * tick))
    while not stop.is_set():
        for _ in range(per_tick):
            sim.step(1.0)
            engine.update(base + sim.t, sim.detections())
        if time.time() - last_pub >= 0.5:
            publish(engine, meta, state_path, sink)
            last_pub = time.time()
        time.sleep(tick)


def run_live(engine, vision, camera_cfg, meta, stop, state_path, live_path, sink=None):
    import cv2

    src = camera_cfg["source"]
    interval = camera_cfg.get("sample_interval", 1.0)
    is_file = isinstance(src, str) and Path(src).exists()
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    last = last_pub = 0.0
    while not stop.is_set():
        if not cap.grab():
            if is_file:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop test videos
            else:
                time.sleep(3)
                cap.release()
                cap = cv2.VideoCapture(src)  # reconnect (RTSP / phone stream)
            continue
        if is_file:
            time.sleep(1 / fps)
        now = time.time()
        if now - last < interval:
            continue
        last = now
        ok, frame = cap.retrieve()
        if not ok:
            continue
        det, view = vision.process(frame)
        engine.update(now, det)
        if now - last_pub >= 1.0:
            cv2.imwrite(str(live_path), view)  # only the blurred view is ever written
            publish(engine, meta, state_path, sink)
            last_pub = now
