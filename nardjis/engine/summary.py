"""Small per-restaurant summary (home screen cards). Shared by the local server and the cloud publisher."""


def health(s):
    """0-100 score of how well the room is running right now."""
    k, lim = s["kpi"], s["meta"].get("patience_limit", 600)
    crit = sum(t["level"] == "critical" for t in s["tables"])
    warn = sum(t["level"] == "warn" for t in s["tables"])
    score = 100 - 18 * crit - 8 * warn - 6 * min(k["abandoned"], 5)
    if k["avg_wait"]:
        score -= min(20, 20 * k["avg_wait"] / lim)
    return max(0, min(100, round(score)))


def summarize(rid, name, s):
    top = s["staff"][0] if s["staff"] and s["staff"][0]["effort"] > 0 else None
    return {
        "id": rid, "name": name, "mode": s["meta"]["mode"], "speed": s["meta"].get("speed", 1),
        "health": health(s), "kpi": s["kpi"],
        "tables": [{"state": t["state"], "level": t["level"]} for t in s["tables"]],
        "top": {"name": top["name"], "effort": top["effort"]} if top else None,
        "staff": [{"name": p["name"], "effort": p["effort"], "restaurant": name} for p in s["staff"]],
    }
