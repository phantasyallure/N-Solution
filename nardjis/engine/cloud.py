"""Publishes the engine's numbers to Supabase (PostgREST), so a dashboard hosted elsewhere (Vercel) can show them.

Only numbers and events are sent - never camera images. Runs in a background thread: a slow or
broken connection never blocks detection.

Env: SUPABASE_URL, SUPABASE_SERVICE_KEY  (keep the service key on the restaurant computer / Vercel only).
"""
import json
import os
import queue
import threading
import time
import urllib.request

from .summary import summarize


class Cloud:
    def __init__(self, url, key, interval=2.0, post=None):
        self.url = url.rstrip("/")
        self.key = key
        self.interval = interval
        self._post = post or self._http
        self.events = queue.Queue(maxsize=2000)
        self._retry = []
        self._latest = {}
        self._lock = threading.Lock()
        self._last_warn = 0.0
        self.sent_states = 0
        self.sent_events = 0
        threading.Thread(target=self._loop, daemon=True, name="cloud").start()

    @classmethod
    def from_env(cls):
        url, key = os.environ.get("SUPABASE_URL", "").strip(), os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        return cls(url, key) if url and key else None

    # ------------------------------------------------------------------ http
    def _http(self, path, rows, prefer):
        headers = {"Content-Type": "application/json", "apikey": self.key, "Prefer": prefer}
        if self.key.startswith("eyJ"):  # legacy JWT keys also go in Authorization; new sb_secret_ keys must not
            headers["Authorization"] = f"Bearer {self.key}"
        req = urllib.request.Request(f"{self.url}/rest/v1/{path}", data=json.dumps(rows).encode(),
                                     headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=10).read()

    def _upsert(self, table, conflict, rows):
        self._post(f"{table}?on_conflict={conflict}", rows, "resolution=merge-duplicates,return=minimal")

    def _warn(self, msg):
        if time.time() - self._last_warn > 30:
            self._last_warn = time.time()
            print(f"[cloud] {msg}", flush=True)

    # ------------------------------------------------------------------- api
    def register(self, rid, name):
        """Synchronous, so a wrong URL/key is visible right at startup."""
        try:
            self._upsert("nj_restaurants", "id", [{"id": rid, "name": name}])
            return True
        except Exception as e:
            print(f"[cloud] cannot reach Supabase for {rid}: {e}", flush=True)
            return False

    def push_state(self, rid, name, snap):
        with self._lock:
            self._latest[rid] = (name, snap)

    def push_event(self, rid, ev):
        try:
            self.events.put_nowait({"restaurant_id": rid, "type": ev["type"], "table_name": ev["table"],
                                    "staff": ev["staff"], "seconds": ev["seconds"], "notify": ev["notify"]})
        except queue.Full:
            pass

    # ---------------------------------------------------------------- worker
    def _loop(self):
        last = 0.0
        while True:
            time.sleep(0.5)
            self._flush_events()
            if time.time() - last >= self.interval:
                last = time.time()
                self._flush_state()

    def _flush_events(self):
        batch, self._retry = self._retry, []
        while len(batch) < 200:
            try:
                batch.append(self.events.get_nowait())
            except queue.Empty:
                break
        if not batch:
            return
        try:
            self._post("nj_events", batch, "return=minimal")
            self.sent_events += len(batch)
        except Exception as e:
            self._retry = batch[:1000]
            self._warn(f"events not sent, will retry: {e}")

    def _flush_state(self):
        with self._lock:
            latest, self._latest = self._latest, {}
        if not latest:
            return
        rows = [{"restaurant_id": rid, "state": snap, "summary": summarize(rid, name, snap)}
                for rid, (name, snap) in latest.items()]
        try:
            self._upsert("nj_state", "restaurant_id", rows)
            self.sent_states += len(rows)
        except Exception as e:
            self._warn(f"state not sent: {e}")
