"""Config loader: one file, many restaurants.

New format  -> top-level shared defaults + a `restaurants:` list (each can override).
Old format  -> a single restaurant described at top level (still supported).
"""
import os
import re

import yaml

SHARED = ("language", "thresholds", "privacy", "staff_uniform", "camera", "telegram")


def _merge(a, b):
    out = dict(a or {})
    out.update(b or {})
    return out


def load_config(path):
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    rests = raw.get("restaurants")
    if not rests:  # legacy single-restaurant file
        rests = [{"id": raw.get("id", "main"), "name": raw.get("restaurant_name", "Restaurant"),
                  "tables": raw.get("tables"), "staff_names": raw.get("staff_names"), "demo": raw.get("demo")}]
    out, seen = [], set()
    for r in rests:
        rid = re.sub(r"[^a-z0-9_-]+", "-", str(r["id"]).lower()).strip("-")
        if not rid or rid in seen:
            raise ValueError(f"restaurant id missing or duplicated: {r.get('id')!r}")
        if not r.get("tables"):
            raise ValueError(f"restaurant {rid}: no tables defined")
        seen.add(rid)
        res = {"id": rid, "name": r.get("name", rid), "tables": r["tables"],
               "staff_names": r.get("staff_names") or raw.get("staff_names") or {},
               "demo": r.get("demo") or {}}
        for k in SHARED:
            base, own = raw.get(k), r.get(k)
            if isinstance(base, dict) or isinstance(own, dict):
                res[k] = _merge(base, own)
            else:
                res[k] = own if own is not None else base
        res["camera"] = res.get("camera") or {}
        res["language"] = res.get("language") or "fr"
        out.append(res)
    return {
        "restaurants": out,
        "gemini": raw.get("gemini") or {},
        "access_code": str(os.environ.get("NARDJIS_ACCESS_CODE") or raw.get("access_code") or ""),
    }
