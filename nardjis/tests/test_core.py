import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.core import Engine  # noqa: E402

T = [
    {"id": "A", "name": "A", "polygon": [[0, 0], [.2, 0], [.2, .2], [0, .2]]},
    {"id": "B", "name": "B", "polygon": [[.5, 0], [.7, 0], [.7, .2], [.5, .2]]},
]
CFG = {"patience_limit": 100, "dirty_after": 20, "remind_every": 30, "visit_seconds": 4}


def run(e, t0, t1, det, step=1):
    for t in range(t0, t1, step):
        e.update(t, det(t) if callable(det) else det)


def test_wait_alert_goes_to_nearest_free_employee_and_serve_logs_wait():
    ev = []
    e = Engine(T, CFG, {1: "Near", 2: "Far"}, ev.append)
    near, far = (1, .55, .3), (2, .95, .95)
    client = [(10, .1, .1)]
    run(e, 0, 60, {"clients": client, "staff": [near, far], "items": []})
    tasks = [x for x in ev if x["type"] == "task_wait"]
    assert len(tasks) == 1 and tasks[0]["staff"] == "Near"      # at 50% of patience, nearest staff only
    assert tasks[0]["table"] == "A"
    # nearest staff walks to the table and stays
    at = (1, .1, .1)
    run(e, 60, 70, {"clients": client, "staff": [at, far], "items": []})
    served = [x for x in ev if x["type"] == "served"]
    assert len(served) == 1 and 55 <= served[0]["seconds"] <= 66
    assert e.snapshot()["tables"][0]["state"] == "occupied"


def test_critical_wait_escalates_to_manager():
    ev = []
    e = Engine(T, CFG, {}, ev.append)
    run(e, 0, 110, {"clients": [(1, .1, .1)], "staff": [(1, .9, .9)], "items": []})
    assert any(x["type"] == "escalate_wait" and x["notify"] == "manager" for x in ev)


def test_dirty_table_alert_then_cleaned():
    ev = []
    e = Engine(T, CFG, {1: "S"}, ev.append)
    seated = {"clients": [(1, .1, .1)], "staff": [(1, .9, .9)], "items": [(.1, .1)]}
    run(e, 0, 10, seated)
    left = {"clients": [], "staff": [(1, .9, .9)], "items": [(.1, .1)]}
    run(e, 10, 50, left)
    assert any(x["type"] == "left_unserved" for x in ev)       # client left without any visit
    assert any(x["type"] == "task_dirty" for x in ev)
    assert e.snapshot()["tables"][0]["state"] == "dirty"
    clean = {"clients": [], "staff": [(1, .1, .1)], "items": []}
    run(e, 50, 70, clean)
    assert any(x["type"] == "cleaned" and x["staff"] == "S" for x in ev)
    assert e.snapshot()["tables"][0]["state"] == "free"


def test_walking_through_a_table_is_not_a_visit():
    e = Engine(T, CFG, {})
    client = [(1, .1, .1)]
    for t in range(0, 10):
        pos = (1, .05 + .01 * t, .1) if t < 2 else (1, .9, .9)  # 2 seconds in the zone only
        e.update(t, {"clients": client, "staff": [pos], "items": []})
    assert e.staff["1"].visits == 0


def test_effort_score_ranks_hard_worker_first():
    e = Engine(T, CFG, {1: "Busy", 2: "Idle"})
    client = [(1, .1, .1)]
    for t in range(0, 40):
        e.update(t, {"clients": client, "staff": [(1, .1, .1) if t > 10 else (1, .9, .9), (2, .9, .9)], "items": []})
    s = e.snapshot()["staff"]
    assert s[0]["name"] == "Busy" and s[0]["effort"] > s[1]["effort"]
