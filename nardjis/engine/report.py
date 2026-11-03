"""Daily owner report (text, FR/EN/AR) built from the SQLite log."""
import time

L = {
    "fr": dict(title="📊 Nardjis Solutions — Rapport du jour", served="Clients servis", avg="Attente moyenne",
               longest="Plus longue attente", lost="Clients partis sans service", clean="Tables nettoyées",
               dirty="Temps moyen avant nettoyage", alerts="Alertes envoyées", top="Meilleur effort",
               none="aucune donnée", unit="min"),
    "en": dict(title="📊 Nardjis Solutions — Daily report", served="Clients served", avg="Average wait",
               longest="Longest wait", lost="Clients who left unserved", clean="Tables cleaned",
               dirty="Average time before cleaning", alerts="Alerts sent", top="Top effort",
               none="no data", unit="min"),
    "ar": dict(title="📊 Nardjis Solutions — تقرير اليوم", served="زبائن تمت خدمتهم", avg="متوسط الانتظار",
               longest="أطول انتظار", lost="زبائن غادروا دون خدمة", clean="طاولات تم تنظيفها",
               dirty="متوسط الوقت قبل التنظيف", alerts="التنبيهات المرسلة", top="أفضل مجهود",
               none="لا توجد بيانات", unit="د"),
}


def build_report(store, state, lang="fr"):
    t = L.get(lang, L["fr"])
    now = time.localtime()
    midnight = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1))
    ev = store.since(midnight)
    served = [e for e in ev if e["type"] == "served"]
    cleaned = [e for e in ev if e["type"] == "cleaned"]
    lost = [e for e in ev if e["type"] == "left_unserved"]
    alerts = [e for e in ev if e["type"].startswith(("task_", "escalate_"))]
    mn = lambda s: f"{s / 60:.1f} {t['unit']}"
    lines = [t["title"], ""]
    lines.append(f"{t['served']}: {len(served)}")
    lines.append(f"{t['avg']}: {mn(sum(e['seconds'] for e in served) / len(served)) if served else t['none']}")
    if served:
        w = max(served, key=lambda e: e["seconds"])
        lines.append(f"{t['longest']}: {mn(w['seconds'])} ({w['table']})")
    lines.append(f"{t['lost']}: {len(lost)}")
    lines.append(f"{t['clean']}: {len(cleaned)}")
    if cleaned:
        lines.append(f"{t['dirty']}: {mn(sum(e['seconds'] for e in cleaned) / len(cleaned))}")
    lines.append(f"{t['alerts']}: {len(alerts)}")
    staff = (state or {}).get("staff") or []
    if staff and staff[0]["effort"] > 0:
        lines.append(f"{t['top']}: {staff[0]['name']} ⭐")
    return "\n".join(lines)
