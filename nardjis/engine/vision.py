"""Camera -> detections. YOLO (Ultralytics, free) + ByteTrack + privacy blur.

Privacy-first: faces are always blurred (upper part of every person box) BEFORE
anything is drawn or saved. No face recognition, no identity: staff are told
apart from clients only by uniform colour.
"""
import cv2
import numpy as np
from ultralytics import YOLO

PERSON = 0
ITEM_CLASSES = [39, 40, 41, 42, 43, 44, 45]  # bottle, wine glass, cup, fork, knife, spoon, bowl


class Vision:
    """One instance per camera (the tracker keeps per-camera state)."""

    def __init__(self, restaurant):
        cam = restaurant.get("camera") or {}
        self.model = YOLO(cam.get("model", "yolo11n.pt"))
        self.conf = cam.get("confidence", 0.4)
        u = restaurant.get("staff_uniform") or {}
        self.ranges = [(np.array(lo, np.uint8), np.array(hi, np.uint8)) for lo, hi in u.get("ranges", [])]
        self.min_ratio = u.get("min_ratio", 0.25)
        self.blur = (restaurant.get("privacy") or {}).get("blur_faces", True)
        self.tables = restaurant["tables"]

    def _is_staff(self, frame, box):
        if not self.ranges:
            return False
        x1, y1, x2, y2 = [int(v) for v in box]
        h, w = y2 - y1, x2 - x1
        torso = frame[max(0, y1 + int(.25 * h)):max(1, y1 + int(.65 * h)), max(0, x1 + int(.2 * w)):max(1, x2 - int(.2 * w))]
        if torso.size == 0:
            return False
        hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in self.ranges:
            mask |= cv2.inRange(hsv, lo, hi)
        return mask.mean() / 255 >= self.min_ratio

    def process(self, frame):
        H, W = frame.shape[:2]
        res = self.model.track(frame, persist=True, tracker="bytetrack.yaml", conf=self.conf,
                               classes=[PERSON] + ITEM_CLASSES, verbose=False)[0]
        det = {"clients": [], "staff": [], "items": []}
        view = frame.copy()
        for b in res.boxes:
            cls = int(b.cls[0])
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            cx, cy = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H
            if cls == PERSON:
                tid = int(b.id[0]) if b.id is not None else -1
                staff = self._is_staff(frame, (x1, y1, x2, y2))
                (det["staff"] if staff else det["clients"]).append((tid, cx, cy))
                if self.blur:  # blur head area before drawing anything
                    hy2 = int(y1 + 0.3 * (y2 - y1))
                    roi = view[max(0, int(y1)):hy2, max(0, int(x1)):int(x2)]
                    if roi.size:
                        view[max(0, int(y1)):hy2, max(0, int(x1)):int(x2)] = cv2.GaussianBlur(roi, (51, 51), 0)
                color = (219, 163, 31) if staff else (75, 50, 184)  # BGR: cyan-ish staff / rose client
                cv2.rectangle(view, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            else:
                det["items"].append((cx, cy))
        for t in self.tables:
            pts = np.array([[int(x * W), int(y * H)] for x, y in t["polygon"]], np.int32)
            cv2.polylines(view, [pts], True, (75, 162, 201), 2)
            cv2.putText(view, t.get("name", t["id"]), tuple(int(v) for v in pts[0]), cv2.FONT_HERSHEY_SIMPLEX, .6, (75, 162, 201), 2)
        return det, view
