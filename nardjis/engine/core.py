"""Nardjis Solutions - decision engine.

Pure logic, no computer-vision dependency. It receives detections in
normalized coordinates (0..1) and decides what is happening in the room:

  * table state (free / occupied / waiting / dirty)
  * client waiting time + Patience Meter (warn -> critical -> manager)
  * dirty-table timers with reminders and escalation
  * Smart Dispatch: only the best employee is alerted, not everybody
  * Fair Effort Score per employee (weighted by table difficulty)

Detections format passed to Engine.update(ts, det):
  {"clients": [(id, x, y), ...],
   "staff":   [(id, x, y), ...],
   "items":   [(x, y), ...]}      # plates / glasses / bottles left on tables
"""
from __future__ import annotations

import math
from collections import deque

DEFAULTS = {
    "debounce": 3,            # s a change must persist before it is trusted
    "visit_seconds": 6,       # s a staff member must stay at a table = a visit
    "grace": 2,               # s tolerance when a detection flickers
    "patience_limit": 600,    # s a client may wait before it is critical
    "warn_ratio": 0.5,        # patience ratio that triggers the first alert
    "dirty_after": 120,       # s an abandoned table may stay dirty
    "remind_every": 180,      # s between dirty-table reminders
    "revisit_after": 900,     # s without a visit before a client "waits again"
    "assign_cooldown": 60,    # s before the same employee gets a new task
    "away_after": 60,         # s without detection = employee is away
    "meters_per_unit": 12,    # room width in meters (normalized 1.0 = this)
}


def point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


def centroid(poly):
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


class Table:
    def __init__(self, cfg):
        self.id = str(cfg["id"])
        self.name = cfg.get("name", self.id)
        self.poly = [tuple(p) for p in cfg["polygon"]]
        self.weight = float(cfg.get("weight", 1.0))  # difficulty of the table
        self.center = centroid(self.poly)
        self.clients_n = 0
        self.items_n = 0
        self.has_clients = False
        self.has_items = False
        self._obs = (False, False)
        self._obs_since = 0.0
        self.seated_since = None
        self.waiting_since = None
        self.dirty_since = None
        self.last_visit = None
        self.last_visitor = None
        self.last_dirty_alert = None
        self.dirty_alerts = 0
        self.flags = set()


class Staff:
    def __init__(self, sid, name):
        self.id = sid
        self.name = name
        self.pos = None
        self.last_seen = None
        self.distance = 0.0     # normalized units
        self.active = 0.0       # seconds
        self.idle = 0.0
        self.visits = 0
        self.tasks_done = 0
        self.waits_served = []  # seconds clients waited before this person came
        self.effort = 0.0
        self.last_assigned = -1e9
        self.open_tasks = 0


class Engine:
    def __init__(self, tables, cfg=None, staff_names=None, on_event=None):
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self.tables = [Table(t) for t in tables]
        self.names = {str(k): v for k, v in (staff_names or {}).items()}
        self.staff = {}
        self.on_event = on_event
        self.events = deque(maxlen=200)
        self.waits = deque(maxlen=100)
        self.tasks = {}
        self._dwell = {}
        self.alerts = 0
        self.now = 0.0

    # ------------------------------------------------------------------ main
    def update(self, ts, det):
        dt = ts - self.now if self.now else 0.0
        self.now = ts
        self._update_staff(ts, dt, det.get("staff", []))
        staff_pos = [(str(s[0]), s[1], s[2]) for s in det.get("staff", [])]
        for t in self.tables:
            t.clients_n = sum(point_in_poly(x, y, t.poly) for _, x, y in det.get("clients", []))
            t.items_n = sum(point_in_poly(x, y, t.poly) for x, y in det.get("items", []))
            self._debounce(t, ts)
            self._visits(t, ts, staff_pos)
            self._timers(t, ts)

    # ----------------------------------------------------------------- staff
    def _update_staff(self, ts, dt, lst):
        for sid, x, y in lst:
            sid = str(sid)
            s = self.staff.get(sid)
            if s is None:
                s = self.staff[sid] = Staff(sid, self.names.get(sid, f"Staff {sid}"))
            if s.pos is not None and dt > 0:
                d = math.hypot(x - s.pos[0], y - s.pos[1])
                if d > 0.003:  # ignore detection jitter
                    s.distance += d
                in_work_zone = any(
                    point_in_poly(x, y, t.poly) and (t.has_clients or t.dirty_since is not None)
                    for t in self.tables
                )
                if d / dt > 0.004 or in_work_zone:
                    s.active += min(dt, 5)
                else:
                    s.idle += min(dt, 5)
            s.pos = (x, y)
            s.last_seen = ts

    def _is_away(self, s, ts):
        return s.last_seen is None or ts - s.last_seen > self.cfg["away_after"]

    # --------------------------------------------------------- state changes
    def _debounce(self, t, ts):
        obs = (t.clients_n > 0, t.items_n > 0)
        if obs != t._obs:
            t._obs, t._obs_since = obs, ts
        if obs != (t.has_clients, t.has_items) and ts - t._obs_since >= self.cfg["debounce"]:
            old_c, old_i = t.has_clients, t.has_items
            t.has_clients, t.has_items = obs
            if obs[0] != old_c:
                self._seated(t, ts) if obs[0] else self._left(t, ts)
            elif not obs[0] and obs[1] != old_i:
                if obs[1]:
                    t.dirty_since = ts
                    t.dirty_alerts, t.last_dirty_alert = 0, None
                else:
                    self._cleaned(t, ts)

    def _seated(self, t, ts):
        t.seated_since = t.waiting_since = ts
        t.last_visit = None
        t.dirty_since = None
        t.flags = set()
        self._close_task(t, "dirty")
        self._emit(ts, "seated", t)

    def _left(self, t, ts):
        if t.waiting_since is not None:
            w = ts - t.waiting_since
            self.waits.append({"table": t.name, "seconds": w, "kind": "abandoned", "staff": None, "ts": ts})
            self._emit(ts, "left_unserved", t, seconds=w, notify="manager")
        else:
            self._emit(ts, "left", t)
        self._close_task(t, "wait")
        t.waiting_since = t.seated_since = None
        t.flags = set()
        t.dirty_alerts, t.last_dirty_alert = 0, None
        t.dirty_since = ts if t.has_items else None

    def _cleaned(self, t, ts):
        dur = ts - t.dirty_since if t.dirty_since is not None else 0.0
        who = t.last_visitor if t.last_visit is not None and ts - t.last_visit <= 120 else None
        task = self.tasks.get((t.id, "dirty"))
        who = who or (task["staff"] if task else None)
        if who in self.staff:
            s = self.staff[who]
            s.tasks_done += 1
            s.effort += 4 * t.weight
        self._close_task(t, "dirty")
        t.dirty_since = None
        t.dirty_alerts, t.last_dirty_alert = 0, None
        self._emit(ts, "cleaned", t, staff=who, seconds=dur)

    # ---------------------------------------------------------------- visits
    def _visits(self, t, ts, staff_pos):
        present = {sid for sid, x, y in staff_pos if point_in_poly(x, y, t.poly)}
        for sid in present:
            d = self._dwell.setdefault((t.id, sid), {"start": ts, "seen": ts, "done": False})
            d["seen"] = ts
            if not d["done"] and ts - d["start"] >= self.cfg["visit_seconds"]:
                d["done"] = True
                if t.has_clients or t.dirty_since is not None:  # ignore walking through
                    self._visit(t, sid, ts)
        for k in [k for k, d in self._dwell.items() if k[0] == t.id and ts - d["seen"] > self.cfg["grace"]]:
            del self._dwell[k]

    def _visit(self, t, sid, ts):
        s = self.staff[sid]
        s.visits += 1
        s.effort += 2 * t.weight
        t.last_visit, t.last_visitor = ts, sid
        if t.has_clients and t.waiting_since is not None:
            w = ts - t.waiting_since
            self.waits.append({"table": t.name, "seconds": w, "kind": "served", "staff": s.name, "ts": ts})
            s.waits_served.append(w)
            s.tasks_done += 1
            s.effort += 5 * t.weight
            t.waiting_since = None
            t.flags -= {"warn", "crit"}
            self._close_task(t, "wait")
            self._emit(ts, "served", t, staff=sid, seconds=w)

    # ---------------------------------------------------------------- timers
    def _timers(self, t, ts):
        c = self.cfg
        if t.has_clients and t.waiting_since is not None:
            ratio = (ts - t.waiting_since) / c["patience_limit"]
            if ratio >= c["warn_ratio"] and "warn" not in t.flags:
                t.flags.add("warn")
                self._dispatch(t, "wait", ts, ts - t.waiting_since)
            if ratio >= 1 and "crit" not in t.flags:
                t.flags.add("crit")
                self._emit(ts, "escalate_wait", t, seconds=ts - t.waiting_since, notify="manager")
        elif (t.has_clients and t.waiting_since is None and t.last_visit is not None
              and ts - t.last_visit >= c["revisit_after"]):
            t.waiting_since = ts
            t.flags -= {"warn", "crit"}
            self._emit(ts, "revisit", t)
        if not t.has_clients and t.dirty_since is not None:
            el = ts - t.dirty_since
            if el >= c["dirty_after"]:
                due = t.last_dirty_alert is None or ts - t.last_dirty_alert >= c["remind_every"]
                if due:
                    t.dirty_alerts += 1
                    t.last_dirty_alert = ts
                    if t.dirty_alerts >= 3:
                        self._emit(ts, "escalate_dirty", t, seconds=el, notify="manager")
                    else:
                        self._dispatch(t, "dirty", ts, el)

    # -------------------------------------------------------- smart dispatch
    def _pick(self, t, ts):
        cand = [s for s in self.staff.values() if not self._is_away(s, ts)]
        if not cand:
            return None
        free = [s for s in cand if s.open_tasks == 0 and ts - s.last_assigned >= self.cfg["assign_cooldown"]]
        pool = free or cand
        m = self.cfg["meters_per_unit"]

        def score(s):
            dist = math.hypot(s.pos[0] - t.center[0], s.pos[1] - t.center[1]) * m
            return dist + 3 * s.open_tasks + 0.02 * s.effort  # near + not overloaded + fair share

        return min(pool, key=score).id

    def _dispatch(self, t, kind, ts, elapsed):
        self._close_task(t, kind)
        sid = self._pick(t, ts)
        if sid:
            self.tasks[(t.id, kind)] = {"staff": sid, "created": ts}
            s = self.staff[sid]
            s.open_tasks += 1
            s.last_assigned = ts
        self._emit(ts, f"task_{kind}", t, staff=sid, seconds=elapsed, notify="staff")

    def _close_task(self, t, kind):
        task = self.tasks.pop((t.id, kind), None)
        if task and task["staff"] in self.staff:
            s = self.staff[task["staff"]]
            s.open_tasks = max(0, s.open_tasks - 1)

    # ---------------------------------------------------------------- events
    def _emit(self, ts, typ, t, staff=None, seconds=0.0, notify=None):
        s = self.staff.get(staff) if staff else None
        ev = {
            "ts": ts, "type": typ, "table_id": t.id, "table": t.name,
            "staff_id": staff, "staff": s.name if s else None,
            "seconds": round(seconds, 1), "notify": notify,
        }
        if notify:
            self.alerts += 1
        self.events.append(ev)
        if self.on_event:
            self.on_event(ev)

    # -------------------------------------------------------------- snapshot
    def snapshot(self, ts=None):
        ts = ts if ts is not None else self.now
        c = self.cfg
        tables = []
        for t in self.tables:
            wait = dirty = 0.0
            if t.has_clients:
                state = "waiting" if t.waiting_since is not None else "occupied"
                if state == "waiting":
                    wait = ts - t.waiting_since
            elif t.dirty_since is not None:
                state, dirty = "dirty", ts - t.dirty_since
            else:
                state = "free"
            ratio = wait / c["patience_limit"] if state == "waiting" else 0.0
            if state == "waiting":
                level = "ok" if ratio < c["warn_ratio"] else "warn" if ratio < 1 else "critical"
            elif state == "dirty":
                level = "ok" if dirty < c["dirty_after"] else "warn" if dirty < 2 * c["dirty_after"] else "critical"
            else:
                level = "ok"
            tables.append({
                "id": t.id, "name": t.name, "state": state, "level": level,
                "clients": t.clients_n if t.has_clients else 0,
                "wait": round(wait, 1), "patience": round(ratio, 3), "dirty": round(dirty, 1),
                "seated": round(ts - t.seated_since, 1) if t.seated_since is not None else 0,
                "center": t.center, "polygon": t.poly,
            })
        staff = []
        for s in self.staff.values():
            away = self._is_away(s, ts)
            tot = s.active + s.idle
            staff.append({
                "id": s.id, "name": s.name, "pos": s.pos,
                "status": "away" if away else ("active" if s.open_tasks else "ready"),
                "visits": s.visits, "tasks_done": s.tasks_done,
                "distance_m": round(s.distance * c["meters_per_unit"], 1),
                "active_pct": round(100 * s.active / tot) if tot else 0,
                "avg_response": round(sum(s.waits_served) / len(s.waits_served), 1) if s.waits_served else None,
                "effort": round(s.effort, 1), "open_tasks": s.open_tasks,
            })
        staff.sort(key=lambda s: -s["effort"])
        served = [w["seconds"] for w in self.waits if w["kind"] == "served"]
        return {
            "now": ts,
            "tables": tables,
            "staff": staff,
            "waits": list(self.waits)[-30:],
            "events": list(self.events)[-40:],
            "kpi": {
                "attention": sum(1 for t in tables if t["level"] != "ok"),
                "longest_wait_now": max([t["wait"] for t in tables] + [0]),
                "avg_wait": round(sum(served) / len(served), 1) if served else None,
                "abandoned": sum(1 for w in self.waits if w["kind"] == "abandoned"),
                "alerts": self.alerts,
                "served": len(served),
            },
        }
