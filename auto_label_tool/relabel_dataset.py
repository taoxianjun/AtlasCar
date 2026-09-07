#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relabel_dataset.py  v1.0  (2026-08-26)

Re-generate Lane-Follow-Train/dataset/label.txt using the CURRENT detection
pipeline (utils/lane_util.detect_edges, which now reads the tightened
hsv-data/hsv.txt + reject_non_lane) — i.e. the exact same logic land_follow.py
used to create the labels in the first place, but with the improved hsv range.

Why re-label (2026-08-26):
  The original 2180 labels were made with a WIDE hsv range (H_max=92). After
  tightening hsv (H_max=50, V_min=85) the detected steering angle drifts by
  >10 deg on 25-50% of the bright-lighting frames (see check_label_quality.py).
  Re-labeling under the new hsv makes the training labels self-consistent with
  the deployment detection domain, removing the old-hsv label bias. QC proved
  the detected mask is already just the lane line (~3% coverage at every
  lighting level) so this is a safe, label-only cleanup (no white-floor
  corruption was found).

Behavior mirrors land_follow.HandCodedLaneFollower.follow_lane:
  - LaneDetector(frame) -> lane_lines
  - write a label ONLY when len(lane_lines) >= 2  (matches ">1" in land_follow)
  - label value = compute_steering_angle(...)[2]  (the 0..180 angle)

Safety:
  - backs up the existing label.txt to label.txt.bak_relabel_<ts> BEFORE writing
  - never deletes images; only rewrites label.txt
  - reports kept / skipped counts so you can see how many frames dropped

Usage:
  cd auto_label_tool
  python relabel_dataset.py
  python relabel_dataset.py --dataset ../Lane-Follow-Train/dataset
  python relabel_dataset.py --hsv hsv-data/hsv_auto.txt   # re-label under auto range
"""
import argparse
import os
import sys
import time
import shutil
import cv2
import numpy as np

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from lane_detector import LaneDetector
from utils.steeer_util import compute_steering_angle


def imread_u(path):
    """Unicode/Chinese-path-safe imread.

    cv2.imread() on Windows fails on absolute paths that contain non-ASCII
    characters (e.g. D:\\桌面\\...). np.fromfile + cv2.imdecode reads the
    bytes directly and works for any path. check_label_quality.py only worked
    because it was passed a RELATIVE dataset path with no Chinese chars;
    this relabeler uses the absolute default, so it MUST use the safe reader.
    """
    raw = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(raw, cv2.IMREAD_COLOR)


def main():
    ap = argparse.ArgumentParser(description="Re-label the training dataset with the current hsv/detection pipeline.")
    default_ds = os.path.normpath(os.path.join(HERE, "..", "Lane-Follow-Train", "dataset"))
    default_hsv = os.path.normpath(os.path.join(HERE, "hsv-data", "hsv.txt"))
    ap.add_argument("--dataset", default=default_ds, help="dataset dir with images/ + label.txt")
    ap.add_argument("--hsv", default=default_hsv,
                    help="HSV range file (6 lines). default=hsv-data/hsv.txt; "
                         "pass hsv-data/hsv_auto.txt to re-label under the auto range.")
    args = ap.parse_args()

    img_dir = os.path.join(args.dataset, "images")
    label_path = os.path.join(args.dataset, "label.txt")
    if not os.path.isdir(img_dir) or not os.path.isfile(label_path):
        sys.exit(f"[ERR] need {img_dir}/ and {label_path}")
    hsv_src = os.path.normpath(args.hsv)
    if not os.path.isfile(hsv_src):
        sys.exit(f"[ERR] hsv file not found: {hsv_src}")

    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    backup = label_path + f".bak_relabel_{ts}"
    shutil.copy(label_path, backup)
    print(f"[OK] backed up old label.txt -> {backup}")

    imgs = sorted(f for f in os.listdir(img_dir) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    out, kept, skipped, err = [], 0, 0, 0
    for name in imgs:
        frame = imread_u(os.path.join(img_dir, name))
        if frame is None:
            err += 1
            continue
        lane_lines, _ = LaneDetector(frame, hsv_txt=hsv_src)()
        if len(lane_lines) >= 2:
            res = compute_steering_angle(frame, lane_lines)
            # res = (x_offset+mid, y_offset, steering_angle); keep the angle
            angle = res[2]
            if not (0.0 <= angle <= 180.0):
                skipped += 1
                continue
            out.append(f"{name} {angle}")
            kept += 1
        else:
            skipped += 1

    with open(label_path, "w") as f:
        f.write("\n".join(out) + ("\n" if out else ""))
    print(f"[OK] re-labeled: kept={kept}  skipped(no>=2 lines)={skipped}  unreadable={err}")
    print(f"     new label.txt -> {label_path}  ({len(out)} samples)")


if __name__ == "__main__":
    main()
