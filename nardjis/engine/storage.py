"""SQLite event log (history, daily report)."""
import sqlite3
import threading
import time


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wall REAL, type TEXT, table_id TEXT, table_name TEXT,
                staff TEXT, seconds REAL, notify TEXT)"""
        )
        self.db.commit()

    def add(self, ev):
        with self.lock:
            self.db.execute(
                "INSERT INTO events(wall,type,table_id,table_name,staff,seconds,notify) VALUES(?,?,?,?,?,?,?)",
                (time.time(), ev["type"], ev["table_id"], ev["table"], ev["staff"], ev["seconds"], ev["notify"]),
            )
            self.db.commit()

    def since(self, wall):
        with self.lock:
            cur = self.db.execute(
                "SELECT wall,type,table_name,staff,seconds FROM events WHERE wall>=? ORDER BY wall", (wall,)
            )
            return [dict(zip(("wall", "type", "table", "staff", "seconds"), r)) for r in cur.fetchall()]
