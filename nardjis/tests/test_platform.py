"""Multi-restaurant config, Gemini assistant (mocked network) and API/auth."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.assistant import Assistant, AssistantError, build_context  # noqa: E402
from engine.config import load_config  # noqa: E402
from engine.core import Engine  # noqa: E402

TABLES = [{"id": "A", "name": "A", "polygon": [[0, 0], [.2, 0], [.2, .2], [0, .2]]}]


def test_config_multi_and_shared_defaults(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("""
language: ar
thresholds: {patience_limit: 300}
telegram: {bot_token: TOK}
restaurants:
  - {id: "Oran Centre", name: One, tables: [{id: A, polygon: [[0,0],[1,0],[1,1]]}], telegram: {staff_chat_id: "1"}}
  - {id: two, name: Two, language: fr, tables: [{id: A, polygon: [[0,0],[1,0],[1,1]]}]}
""")
    c = load_config(str(p))
    a, b = c["restaurants"]
    assert a["id"] == "oran-centre" and a["language"] == "ar" and b["language"] == "fr"
    assert a["telegram"] == {"bot_token": "TOK", "staff_chat_id": "1"}   # shared token + own chat
    assert b["thresholds"]["patience_limit"] == 300


def test_config_legacy_single_restaurant(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("restaurant_name: Solo\ntables: [{id: A, polygon: [[0,0],[1,0],[1,1]]}]\n")
    assert load_config(str(p))["restaurants"][0]["name"] == "Solo"


def test_config_rejects_duplicate_ids(tmp_path):
    p = tmp_path / "c.yaml"
    t = "tables: [{id: A, polygon: [[0,0],[1,0],[1,1]]}]"
    p.write_text(f"restaurants:\n  - {{id: x, {t}}}\n  - {{id: x, {t}}}\n")
    with pytest.raises(ValueError):
        load_config(str(p))


def _state():
    e = Engine(TABLES, {}, {})
    e.update(1, {"clients": [(1, .1, .1)], "staff": [], "items": []})
    s = e.snapshot()
    s["meta"] = {"mode": "demo", "patience_limit": 600}
    return s


def test_context_contains_numbers_but_no_images_or_coordinates():
    ctx = build_context([("Oran", _state())])
    d = json.loads(ctx)[0]
    assert d["restaurant"] == "Oran" and d["tables"][0]["name"] == "A"
    assert "polygon" not in ctx and "center" not in ctx


def test_gemini_request_shape_and_answer():
    calls = []

    def post(url, key, payload):
        calls.append((url, key, payload))
        return 200, {"candidates": [{"content": {"parts": [{"text": "Table 3 attend le plus."}]}}]}

    ai = Assistant("KEY", ["m1"], post)
    out = ai.ask("Quelle table attend ?", "[]", "fr")
    url, key, payload = calls[0]
    assert out == "Table 3 attend le plus." and key == "KEY" and "KEY" not in url
    assert url.endswith("/models/m1:generateContent")
    assert "French" in payload["contents"][0]["parts"][0]["text"]
    assert payload["system_instruction"]["parts"][0]["text"]


def test_gemini_falls_back_to_next_model_then_reports_quota():
    seq = iter([(404, {}), (200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})])
    assert Assistant("K", ["old", "new"], lambda *a: next(seq)).ask("q", "[]") == "ok"
    with pytest.raises(AssistantError) as e:
        Assistant("K", ["a", "b"], lambda *a: (429, {})).ask("q", "[]")
    assert e.value.code == "quota"


def test_gemini_without_key_and_bad_key():
    with pytest.raises(AssistantError) as e:
        Assistant("", None, lambda *a: (200, {})).ask("q", "[]")
    assert e.value.code == "no_key"
    with pytest.raises(AssistantError) as e:
        Assistant("bad", ["m"], lambda *a: (400, {"error": {"message": "API key not valid"}})).ask("q", "[]")
    assert e.value.code == "no_key"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("access_code: s3cret\nrestaurants:\n  - {id: r1, name: R1, tables: "
                   "[{id: A, name: A, polygon: [[0,0],[.2,0],[.2,.2],[0,.2]]}]}\n")
    monkeypatch.setenv("NARDJIS_CONFIG", str(cfg))
    monkeypatch.setenv("NARDJIS_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    (tmp_path / "data" / "r1").mkdir(parents=True)
    s = _state()
    s["meta"]["generated_at"] = time.time()
    (tmp_path / "data" / "r1" / "state.json").write_text(json.dumps(s))
    for m in [m for m in sys.modules if m.startswith(("dashboard", "engine.runner"))]:
        del sys.modules[m]
    from fastapi.testclient import TestClient
    from dashboard.app import app
    return TestClient(app)


def test_api_requires_code_then_serves_overview(client):
    assert client.get("/api?op=overview").status_code == 401
    assert client.get("/api?op=auth").json() == {"required": True, "ok": False, "configured": True}
    assert client.post("/api?op=login", json={"code": "nope"}).status_code == 401
    assert client.post("/api?op=login", json={"code": "s3cret"}).status_code == 200
    ov = client.get("/api?op=overview").json()
    assert ov["restaurants"][0]["id"] == "r1" and ov["restaurants"][0]["online"] is True
    assert ov["group"]["count"] == 1 and ov["ai"] is False
    assert client.get("/api?op=state&id=zzz").status_code == 404
    r = client.post("/api?op=ask", json={"question": "hi", "restaurant": "r1"})
    assert r.status_code == 503 and r.json()["error"] == "no_key"   # no Gemini key configured


def test_login_is_rate_limited(client):
    codes = [client.post("/api?op=login", json={"code": "x"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_alert_names_the_restaurant(capsys):
    from engine.notifier import Notifier
    n = Notifier({}, "fr", "Es Sénia")
    n.handle({"type": "task_dirty", "table": "Table 2", "staff": "Karim", "seconds": 120, "notify": "staff"})
    assert "[Es Sénia] 🧹 Table 2" in capsys.readouterr().out
