"""Draw table zones on your camera image with the mouse.

  python tools/zones.py --source 0

Left click = add a corner. Press N = finish this table and start the next.
Press S = print the YAML to paste into config.yaml. Q = quit.
"""
import argparse

import cv2

ap = argparse.ArgumentParser()
ap.add_argument("--source", default="0")
a = ap.parse_args()
src = int(a.source) if a.source.isdigit() else a.source
cap = cv2.VideoCapture(src)
ok, frame = cap.read()
assert ok, "cannot read the camera"
H, W = frame.shape[:2]
tables, cur = [], []


def click(ev, x, y, *_):
    if ev == cv2.EVENT_LBUTTONDOWN:
        cur.append((round(x / W, 3), round(y / H, 3)))


cv2.namedWindow("zones")
cv2.setMouseCallback("zones", click)
while True:
    v = frame.copy()
    for t in tables + [cur]:
        pts = [(int(x * W), int(y * H)) for x, y in t]
        for p in pts:
            cv2.circle(v, p, 4, (75, 50, 184), -1)
        if len(pts) > 1:
            cv2.polylines(v, [__import__("numpy").array(pts)], t is not cur, (75, 162, 201), 2)
    cv2.imshow("zones", v)
    k = cv2.waitKey(30) & 0xFF
    if k == ord("n") and len(cur) >= 3:
        tables.append(cur[:])
        cur.clear()
    elif k == ord("s"):
        for i, t in enumerate(tables, 1):
            print(f'  - {{id: T{i}, name: "Table {i}", weight: 1.0, polygon: {[list(p) for p in t]}}}')
    elif k == ord("q"):
        break
