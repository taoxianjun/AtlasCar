#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# recall_test.py  v1.0
# HSV-calibration quality report for the lane auto-labeling pipeline.
#
# Two metrics:
#   1) IMAGE-LEVEL recall (no ground truth needed)
#      fraction of data/images/*.jpg that still yield >= 2 lane lines with the
#      CURRENT hsv-data/hsv.txt -- i.e. frames that can still be auto-labeled.
#      Also reports the 0-line / 1-line / >=2-line histogram and the average
#      inRange pixel coverage (a sanity check for a too-loose / too-tight range).
#   2) PIXEL-LEVEL recall (needs GT masks, --gt-dir)
#      for each GT mask (white = human-confirmed yellow-line pixels, same
#      filename as the frame, .png), compute inRange coverage vs GT:
#          Recall    = TP / (TP + FN)     -- did we catch the real yellow?
#          Precision = TP / (TP + FP)     -- how much of what we caught is real?
#          IoU       = TP / (TP + FP + FN)
#      GT masks are produced inside auto_hsv.py with the 'm' key (saves the
#      confirmed effective mask to hsv-data/gt_masks/<image>.png).
#
# Usage:
#   python recall_test.py                   # image-level over data/images
#   python recall_test.py --limit 200       # first 200 frames (quick)
#   python recall_test.py --gt-dir hsv-data/gt_masks     # + pixel-level metrics
#   python recall_test.py --print-bad 5     # also print the 5 worst frames
import os
import sys
import argparse
import time
import cv2
import numpy as np

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
# cv2.imread fails on Chinese paths (e.g. 桌面) -> reuse auto_hsv.load_image
from auto_hsv import load_image
from utils.lane_util import (detect_edges, region_of_interest,
                             detect_line_segments, average_slope_intercept)


def load_hsv_range():
    path = os.path.join(HERE, "hsv-data", "hsv.txt")
    with open(path) as f:
        v = [int(x) for x in f.read().split()]
    if len(v) != 6:
        raise SystemExit(f"hsv.txt must contain 6 numbers, got {v}")
    return tuple(v)


def frame_list(limit=None):
    d = os.path.join(HERE, "data", "images")
    files = sorted(
        [f for f in os.listdir(d)
         if f.split(".")[0].isdigit() and int(f.split(".")[0]) > 0],
        key=lambda x: int(x.split(".")[0]),
    )
    if limit:
        files = files[:limit]
    return files


def image_level(files, bounds, print_bad=0):
    """Count how many frames pass the full lane pipeline with current hsv.txt."""
    total = passed = n0 = n1 = n2 = 0
    pix_ratios = []
    bad = []
    t0 = time.time()
    for i, f in enumerate(files, 1):
        frame = load_image(os.path.join(HERE, "data", "images", f))
        if frame is None:
            continue
        total += 1
        # pixel coverage ratio (tight/loose sanity): inRange fraction of frame
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        m = cv2.inRange(hsv, np.array(bounds[0::2]), np.array(bounds[1::2]))
        ratio = int((m > 0).sum()) / (frame.shape[0] * frame.shape[1])
        pix_ratios.append(ratio)
        # lane pipeline (same path as main.py / quick_check.py)
        edges = detect_edges(frame)
        cropped = region_of_interest(edges)
        segs = detect_line_segments(cropped)
        lines = average_slope_intercept(frame, segs)
        n = len(lines)
        if n == 0:
            n0 += 1
            if print_bad and len(bad) < print_bad:
                bad.append((f, n, ratio))
        elif n == 1:
            n1 += 1
        else:
            n2 += 1
            passed += 1
        if i % 200 == 0:
            print(f"  ... {i}/{len(files)} frames ({time.time()-t0:.0f}s)")
    recall = passed / total if total else 0.0
    print("=" * 60)
    print("[image-level recall]  (>=2 lines = auto-labelable)")
    print(f"  total={total}  recall(>=2)={passed}/{total} = {recall:.1%}")
    print(f"  histogram: 0-line={n0}  1-line={n1}  >=2-line={n2}")
    if pix_ratios:
        mean_ratio = float(np.mean(pix_ratios))
        print(f"  mean inRange pixel coverage = {mean_ratio:.2%} "
              f"(<5% tight / >20% likely too loose)")
    if bad:
        print("[worst frames (0 line)]")
        for f, n, r in bad:
            print(f"  {f}: lines={n}  coverage={r:.1%}")
    return recall


def pixel_level(files, bounds, gt_dir):
    """Recall/Precision/IoU of inRange vs human-confirmed GT masks."""
    recs, precs, ious = [], [], []
    used = 0
    for f in files:
        gt_path = os.path.join(gt_dir, os.path.splitext(f)[0] + ".png")
        if not os.path.exists(gt_path):
            continue
        frame = load_image(os.path.join(HERE, "data", "images", f))
        if frame is None:
            continue
        used += 1
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        pred = cv2.inRange(hsv, np.array(bounds[0::2]),
                           np.array(bounds[1::2])) > 0
        # GT masks live under the same Chinese path -> imdecode+fromfile too
        gt_data = np.fromfile(gt_path, dtype=np.uint8)
        gt_img = cv2.imdecode(gt_data, cv2.IMREAD_GRAYSCALE)
        if gt_img is None:
            continue
        gt = gt_img > 0
        tp = int((pred & gt).sum())
        fp = int((pred & ~gt).sum())
        fn = int((~pred & gt).sum())
        recs.append(tp / max(1, tp + fn))
        precs.append(tp / max(1, tp + fp))
        ious.append(tp / max(1, tp + fp + fn))
    if not used:
        print(f"[pixel-level] no GT masks found in {gt_dir} "
              "(use 'm' in auto_hsv.py to save them)")
        return None
    print("=" * 60)
    print(f"[pixel-level recall]  (GT frames used={used})")
    print(f"  Recall    = TP/(TP+FN) = {np.mean(recs):.1%}  (catches real yellow?)")
    print(f"  Precision = TP/(TP+FP) = {np.mean(precs):.1%}  (false-red pollution?)")
    print(f"  IoU       = TP/(TP+FP+FN) = {np.mean(ious):.1%}")
    return np.mean(recs)


def main():
    ap = argparse.ArgumentParser(description="HSV calibration recall test")
    ap.add_argument("--limit", type=int, default=None,
                    help="only test the first N frames (quick)")
    ap.add_argument("--gt-dir", default=None,
                    help="dir of GT masks for pixel-level recall")
    ap.add_argument("--print-bad", type=int, default=0,
                    help="print the N worst (0-line) frames")
    args = ap.parse_args()

    bounds = load_hsv_range()
    print(f"[hsv.txt] H[{bounds[0]},{bounds[1]}] "
          f"S[{bounds[2]},{bounds[3]}] V[{bounds[4]},{bounds[5]}]")
    files = frame_list(args.limit)
    print(f"[frames] {len(files)} images")

    image_level(files, bounds, args.print_bad)
    if args.gt_dir:
        pixel_level(files, bounds, args.gt_dir)

    print("=" * 60)
    print("done")


if __name__ == "__main__":
    main()
