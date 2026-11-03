"""Copy the dashboard page (single source: dashboard/static) into vercel/public.
Run after editing dashboard/static/index.html:  python tools/sync_vercel.py"""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
src, dst = root / "dashboard" / "static", root / "vercel" / "public"
shutil.rmtree(dst, ignore_errors=True)
(dst / "static").mkdir(parents=True)
shutil.copy(src / "index.html", dst / "index.html")
for f in src.iterdir():
    if f.name not in ("index.html", "live.jpg"):
        shutil.copy(f, dst / "static" / f.name)
print("synced ->", dst)
