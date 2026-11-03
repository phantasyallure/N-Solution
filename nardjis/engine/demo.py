"""Restaurant simulator so the whole system can be tried without a camera."""
import math
import random

from .core import centroid

# fast / medium / slow employee, to make the effort ranking meaningful
PROFILES = [
    {"id": 1, "home": (0.30, 0.95), "speed": 0.10, "p": 1 / 120, "delay": 1.0},
    {"id": 2, "home": (0.55, 0.95), "speed": 0.08, "p": 1 / 240, "delay": 2.0},
    {"id": 3, "home": (0.80, 0.95), "speed": 0.06, "p": 1 / 700, "delay": 8.0},
]


class Sim:
    def __init__(self, engine, seed=7, attention=1.0):
        # attention > 1 = a more reactive team, < 1 = a team that struggles (varies the demo restaurants)
        self.rng = random.Random(seed)
        self.e = engine
        self.t = 0.0
        self.tables = []
        for t in engine.tables:
            xs, ys = [p[0] for p in t.poly], [p[1] for p in t.poly]
            self.tables.append({
                "obj": t, "bbox": (min(xs), min(ys), max(xs), max(ys)), "phase": "free",
                "next": self.rng.uniform(5, 60), "seats": [], "served": False, "items": [], "leave_at": 0,
            })
        self.staff = [{**p, "p": p["p"] * attention, "delay": p["delay"] / attention,
                       "pos": list(p["home"]), "target": None, "dwell": 0.0, "ready_at": 0.0}
                      for p in PROFILES]
        self.queue = {}  # staff id -> (table id, ready_at)

    # called by the engine for each event: dispatched employee goes to the table
    def on_event(self, ev):
        if ev["type"] in ("task_wait", "task_dirty") and ev["staff_id"]:
            sid = int(ev["staff_id"])
            prof = next(s for s in self.staff if s["id"] == sid)
            self.queue[sid] = (ev["table_id"], self.t + self.rng.uniform(3, 25) * prof["delay"])

    def _pts(self, tb, n):
        x0, y0, x1, y1 = tb["bbox"]
        return [(self.rng.uniform(x0 + 0.03, x1 - 0.03), self.rng.uniform(y0 + 0.03, y1 - 0.03)) for _ in range(n)]

    def _needs(self, tb):
        return (tb["phase"] == "seated" and not tb["served"]) or tb["phase"] == "dirty"

    def step(self, dt=1.0):
        self.t += dt
        rng = self.rng
        for tb in self.tables:
            if tb["phase"] == "free" and self.t >= tb["next"]:
                tb.update(phase="seated", served=False, items=[], seats=self._pts(tb, rng.randint(1, 4)))
            elif tb["phase"] == "seated" and tb["served"] and self.t >= tb["leave_at"]:
                tb.update(phase="dirty", seats=[])
        targeted = {s["target"] for s in self.staff if s["target"]}
        for s in self.staff:
            if s["target"] is None and self.t >= s["ready_at"]:
                q = self.queue.get(s["id"])
                if q and self.t >= q[1]:
                    tb = next(x for x in self.tables if x["obj"].id == q[0])
                    del self.queue[s["id"]]
                    if self._needs(tb):
                        s["target"] = q[0]
                elif not q and rng.random() < s["p"]:
                    opts = [x["obj"].id for x in self.tables if self._needs(x) and x["obj"].id not in targeted]
                    if opts:
                        s["target"] = rng.choice(opts)
                        targeted.add(s["target"])
            tgt = next((x for x in self.tables if x["obj"].id == s["target"]), None)
            goal = centroid(tgt["obj"].poly) if tgt else s["home"]
            d = math.hypot(goal[0] - s["pos"][0], goal[1] - s["pos"][1])
            step = s["speed"] * dt
            if d > 0.02:
                k = min(step, d) / d
                s["pos"][0] += (goal[0] - s["pos"][0]) * k
                s["pos"][1] += (goal[1] - s["pos"][1]) * k
            elif tgt:
                s["dwell"] += dt
                need = 10 if tgt["phase"] == "seated" else 14
                if s["dwell"] >= need:
                    if tgt["phase"] == "seated":
                        tgt["served"] = True
                        tgt["items"] = self._pts(tgt, len(tgt["seats"]) + 1)
                        tgt["leave_at"] = self.t + rng.uniform(240, 480)
                    elif tgt["phase"] == "dirty":
                        tgt.update(phase="free", items=[], next=self.t + rng.uniform(30, 120))
                    s["target"], s["dwell"], s["ready_at"] = None, 0.0, self.t + 5

    def detections(self):
        n = lambda: self.rng.uniform(-0.002, 0.002)
        clients, items = [], []
        for i, tb in enumerate(self.tables):
            for k, (x, y) in enumerate(tb["seats"]):
                clients.append((i * 10 + k, x + n(), y + n()))
            if tb["phase"] in ("seated", "dirty"):
                items += [(x + n(), y + n()) for x, y in tb["items"]]
        staff = [(s["id"], s["pos"][0] + n(), s["pos"][1] + n()) for s in self.staff]
        return {"clients": clients, "staff": staff, "items": items}
