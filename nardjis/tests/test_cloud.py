"""Engine -> Supabase publisher, tested against the fake PostgREST."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine.cloud import Cloud  # noqa: E402
from engine.core import Engine  # noqa: E402
from fake_supabase import FakeSupabase  # noqa: E402

TABLES = [{"id": "A", "name": "A", "polygon": [[0, 0], [.2, 0], [.2, .2], [0, .2]]}]


def snap():
    e = Engine(TABLES, {}, {})
    e.update(1, {"clients": [(1, .1, .1)], "staff": [], "items": []})
    s = e.snapshot()
    s["meta"] = {"mode": "demo", "speed": 20, "patience_limit": 600, "generated_at": time.time()}
    return s


def wait_for(cond, t=6):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_register_state_and_events_reach_supabase():
    fake = FakeSupabase(key="sb_secret_abc")
    try:
        c = Cloud(fake.url, "sb_secret_abc", interval=0.3)
        assert c.register("r1", "Oran Centre")
        c.push_state("r1", "Oran Centre", snap())
        c.push_state("r1", "Oran Centre", snap())          # only the latest is kept per restaurant
        c.push_event("r1", {"type": "task_dirty", "table": "T2", "staff": "Amine", "seconds": 130.0, "notify": "staff"})
        assert wait_for(lambda: fake.tables["nj_state"] and fake.tables["nj_events"])
        st = fake.tables["nj_state"][0]
        assert st["restaurant_id"] == "r1" and st["state"]["tables"][0]["name"] == "A"
        assert st["summary"]["name"] == "Oran Centre" and "health" in st["summary"]
        ev = fake.tables["nj_events"][0]
        assert (ev["restaurant_id"], ev["type"], ev["table_name"], ev["staff"]) == ("r1", "task_dirty", "T2", "Amine")
        # PostgREST upsert contract
        up = [r for r in fake.requests if "on_conflict=restaurant_id" in r[1]][0]
        assert "resolution=merge-duplicates" in up[2]["Prefer"]
        # new-style secret keys are NOT sent as a Bearer token; legacy JWT keys are
        assert "Authorization" not in up[2]
    finally:
        fake.close()


def test_legacy_jwt_key_is_also_sent_as_bearer():
    key = "eyJhbGciOi.fake.jwt"
    fake = FakeSupabase(key=key)
    try:
        c = Cloud(fake.url, key, interval=0.3)
        assert c.register("r1", "R")
        assert fake.requests[0][2]["Authorization"] == f"Bearer {key}"
    finally:
        fake.close()


def test_wrong_key_or_dead_server_never_raises_and_events_are_retried():
    fake = FakeSupabase(key="right")
    try:
        c = Cloud(fake.url, "wrong", interval=0.2)
        assert c.register("r1", "R") is False               # visible at startup, no crash
        c.push_event("r1", {"type": "cleaned", "table": "T", "staff": None, "seconds": 5, "notify": None})
        time.sleep(1.2)                                     # worker keeps running despite 401s
        assert c.sent_events == 0
        c.key = "right"                                     # fixed -> the queued event is delivered
        fake.tables["nj_restaurants"].append({"id": "r1", "name": "R"})
        assert wait_for(lambda: fake.tables["nj_events"])
    finally:
        fake.close()
