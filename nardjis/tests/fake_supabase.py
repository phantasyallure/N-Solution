"""Minimal in-memory stand-in for Supabase's PostgREST, enough to test the whole chain without internet.
It implements only what Nardjis uses: upsert (on_conflict), insert, and select with eq./gte. filters.

Run standalone:  python tests/fake_supabase.py 54321
"""
import json
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PK = {"nj_restaurants": "id", "nj_state": "restaurant_id"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class FakeSupabase:
    def __init__(self, port=0, key="test-key"):
        self.tables = {"nj_restaurants": [], "nj_state": [], "nj_events": []}
        self.key = key
        self.requests = []   # (method, path, headers, body) for assertions
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=b"", ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _auth(self):
                if self.headers.get("apikey") != fake.key:
                    self._send(401, b'{"message":"Invalid API key"}')
                    return False
                return True

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"[]")
                u = urlparse(self.path)
                fake.requests.append(("POST", self.path, dict(self.headers), body))
                if not self._auth():
                    return
                table = u.path.rsplit("/", 1)[-1]
                if table not in fake.tables:
                    return self._send(404, b'{"message":"relation does not exist"}')
                q = parse_qs(u.query)
                rows = body if isinstance(body, list) else [body]
                with fake.lock:
                    for r in rows:
                        r = dict(r)
                        if "on_conflict" in q:
                            pk = q["on_conflict"][0]
                            old = next((x for x in fake.tables[table] if x[pk] == r[pk]), None)
                            if old:
                                old.update(r)
                                if table == "nj_state":
                                    old["updated_at"] = now_iso()   # the SQL trigger
                                continue
                        if table == "nj_restaurants":
                            r.setdefault("created_at", now_iso())
                        if table == "nj_state":
                            r.setdefault("updated_at", now_iso())
                        if table == "nj_events":
                            r.setdefault("ts", now_iso())
                            r["id"] = len(fake.tables[table]) + 1
                        fake.tables[table].append(r)
                self._send(201)

            def do_GET(self):
                u = urlparse(self.path)
                fake.requests.append(("GET", self.path, dict(self.headers), None))
                if not self._auth():
                    return
                table = u.path.rsplit("/", 1)[-1]
                if table not in fake.tables:
                    return self._send(404, b'{"message":"relation does not exist"}')
                q = parse_qs(u.query)
                with fake.lock:
                    rows = [dict(r) for r in fake.tables[table]]
                for col, vals in q.items():
                    if col in ("select", "order", "limit"):
                        continue
                    op, _, val = vals[0].partition(".")
                    if op == "eq":
                        rows = [r for r in rows if str(r.get(col)) == val]
                    elif op == "gte":
                        rows = [r for r in rows if str(r.get(col)) >= val.replace("Z", "+00:00")[:19]]
                if "order" in q:
                    rows.sort(key=lambda r: str(r.get(q["order"][0].split(".")[0])))
                if "select" in q and q["select"][0] != "*":
                    cols = q["select"][0].split(",")
                    rows = [{c: r.get(c) for c in cols} for r in rows]
                self._send(200, json.dumps(rows).encode())

        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", port), H)
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


if __name__ == "__main__":
    f = FakeSupabase(int(sys.argv[1]) if len(sys.argv) > 1 else 54321)
    print("fake supabase on", f.url, flush=True)
    while True:
        time.sleep(3600)
