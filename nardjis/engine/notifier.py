"""Alerts: console + Telegram (staff group and manager)."""
import json
import threading
import urllib.request

MSG = {
    "fr": {
        "task_wait": "🔔 {table} : client en attente depuis {min} min → {staff}",
        "task_dirty": "🧹 {table} : table à nettoyer depuis {min} min → {staff}",
        "escalate_wait": "🚨 MANAGER — {table} : attente critique ({min} min)",
        "escalate_dirty": "🚨 MANAGER — {table} non nettoyée depuis {min} min",
        "left_unserved": "⚠️ {table} : client parti sans service après {min} min",
        "everyone": "tous",
    },
    "en": {
        "task_wait": "🔔 {table}: client waiting for {min} min → {staff}",
        "task_dirty": "🧹 {table}: table needs cleaning for {min} min → {staff}",
        "escalate_wait": "🚨 MANAGER — {table}: critical wait ({min} min)",
        "escalate_dirty": "🚨 MANAGER — {table} not cleaned for {min} min",
        "left_unserved": "⚠️ {table}: client left unserved after {min} min",
        "everyone": "everyone",
    },
    "ar": {
        "task_wait": "🔔 {table}: زبون ينتظر منذ {min} د ← {staff}",
        "task_dirty": "🧹 {table}: الطاولة تحتاج تنظيف منذ {min} د ← {staff}",
        "escalate_wait": "🚨 المدير — {table}: انتظار حرج ({min} د)",
        "escalate_dirty": "🚨 المدير — {table} غير منظفة منذ {min} د",
        "left_unserved": "⚠️ {table}: زبون غادر دون خدمة بعد {min} د",
        "everyone": "الجميع",
    },
}


def format_event(ev, lang="fr"):
    m = MSG.get(lang, MSG["fr"])
    tpl = m.get(ev["type"])
    if not tpl:
        return None
    return tpl.format(table=ev["table"], staff=ev["staff"] or m["everyone"], min=round(ev["seconds"] / 60, 1))


class Notifier:
    def __init__(self, cfg, lang="fr", name=""):
        self.lang = lang
        self.name = name  # shown in every alert: several restaurants can share one Telegram bot
        self.token = (cfg or {}).get("bot_token") or ""
        self.staff_chat = (cfg or {}).get("staff_chat_id") or ""
        self.manager_chat = (cfg or {}).get("manager_chat_id") or self.staff_chat

    def handle(self, ev):
        if not ev.get("notify"):
            return
        text = format_event(ev, self.lang)
        if not text:
            return
        if self.name:
            text = f"[{self.name}] {text}"
        print(f"[ALERT] {text}", flush=True)
        chat = self.manager_chat if ev["notify"] == "manager" else self.staff_chat
        if self.token and chat:
            threading.Thread(target=self._telegram, args=(chat, text), daemon=True).start()

    def _telegram(self, chat, text):
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data=json.dumps({"chat_id": chat, "text": text}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:  # never crash the engine because of a network error
            print(f"[telegram] {e}", flush=True)
