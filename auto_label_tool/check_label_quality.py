#!/usr/bin/env python
# check_label_quality.py
# Spot-check annotation quality of the lane-following dataset ACROSS lighting levels.
#
# Why this exists (2026-08-26):
#   The dataset was captured at 4 lighting intensities (~600 each) but the images
#   are merged into one flat folder, and the labeler (auto_label_tool/land_follow.py)
#   ONLY writes a label when it detects 2 lane lines. At extreme lighting the yellow
#   line may fall outside hsv-data/hsv.txt, so detection silently drops frames ->
#   the "4-level coverage" at the dim/bright ends can be illusory.
#
# This tool re-runs the EXACT labeling detection pipeline (mirrored from
# utils/lane_util.py and utils/steeer_util.py) on every labeled image, groups
# images into brightness buckets (a proxy for the 4 lighting levels), and reports
# per-bucket: detection-failure rate, label-mismatch rate, mean stored angle.
# It also dumps a few overlay images per bucket for eyeballing.
#
# Run:
#   cd auto_label_tool
#   python check_label_quality.py                      # default dataset ../Lane-Follow-Train/dataset
#   python check_label_quality.py --dataset <dir> --levels 4 --sample 6
import argparse
import csv
import os
import sys
import cv2
import numpy as np

# ---------------------------------------------------------------------------
# MIRROR of auto_label_tool/utils/lane_util.py  (do not diverge)
# ---------------------------------------------------------------------------
def detect_edges(frame, hsv_txt_path, reject=True):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    with open(hsv_txt_path, 'r') as f:
        content = f.read()
    low_h, high_h, low_s, high_s, low_v, high_v = list(map(int, content.split("\n")))
    lower = np.array([low_h, low_s, low_v])
    upper = np.array([high_h, high_s, high_v])
    mask = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    erode = cv2.erode(mask, kernel, iterations=5)
    dilate = cv2.dilate(erode, kernel, iterations=2)
    close = cv2.morphologyEx(dilate, cv2.MORPH_CLOSE, kernel, iterations=15)
    close = cv2.morphologyEx(dilate, cv2.MORPH_CLOSE, kernel, iterations=15)
    # white-area / big-blob rejection (mirrors utils/lane_util.reject_non_lane)
    if reject:
        close = reject_non_lane(close, hsv)
    return close


def reject_non_lane(mask, hsv, min_frac=0.30, min_area=50,
                    min_aspect=2.0, max_border_touch=2, elong_exempt=8,
                    min_mean_s=0):
    # Mirrors utils/lane_util.reject_non_lane exactly (saturation gate disabled).
    if int((mask > 0).sum()) == 0:
        return mask
    H, W = mask.shape[:2]
    total = H * W
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros_like(mask)
    s_channel = hsv[:, :, 1]
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        if area / total >= min_frac:
            continue
        aspect = max(w, h) / max(1, min(w, h))
        touches = (1 if y <= 0 else 0) + (1 if y + h >= H - 1 else 0) + \
                  (1 if x <= 0 else 0) + (1 if x + w >= W - 1 else 0)
        if touches > max_border_touch and aspect < elong_exempt:
            continue
        if min_mean_s > 0:
            mean_s = float(s_channel[labels == i].mean())
            if mean_s < min_mean_s:
                continue
        keep[labels == i] = 1
    return keep


def region_of_interest(img):
    height, width = img.shape
    mask = np.zeros_like(img)
    polygon = np.array([[
        (height // 18, height // 2),
        (width, height // 2),
        (width, height),
        (height // 18, height),
    ]], np.int32)
    cv2.fillPoly(mask, polygon, 255)
    return cv2.bitwise_and(img, mask)


def detect_line_segments(cropped):
    segs = cv2.HoughLinesP(cropped, 1, np.pi / 180, 10, np.array([]), 10, 6)
    if segs is None:
        return None
    return np.array(segs).reshape(-1, 4)  # normalize (N,1,4) and (N,4) both -> (N,4)


def average_slope_intercept(frame, line_segments):
    lane_lines = []
    if line_segments is None:
        return lane_lines
    line_segments = np.array(line_segments).reshape(-1, 4)
    height, width, _ = frame.shape
    left_fit, right_fit = [], []
    boundary = 1 / 2
    left_b = width * (1 - boundary)
    right_b = width * boundary
    for x1, y1, x2, y2 in line_segments:
        if x1 == x2:
            continue
        fit = np.polyfit((x1, x2), (y1, y2), 1)
        slope, intercept = fit
        if slope < 0:
            if x1 < left_b and x2 < left_b:
                left_fit.append((slope, intercept))
        else:
            if x1 > right_b and x2 > right_b:
                right_fit.append((slope, intercept))
    if left_fit:
        lane_lines.append(_make_points(frame, np.average(left_fit, axis=0)))
    if right_fit:
        lane_lines.append(_make_points(frame, np.average(right_fit, axis=0)))
    return lane_lines


def _make_points(frame, line):
    height, width, _ = frame.shape
    slope, intercept = line
    y1 = height
    y2 = int(y1 * 1 / 2)
    x1 = max(-width, min(2 * width, int((y1 - intercept) / slope)))
    x2 = max(-width, min(2 * width, int((y2 - intercept) / slope)))
    return [[x1, y1, x2, y2]]


def compute_steering_angle(frame, lane_lines):
    if len(lane_lines) == 0:
        return -90  # scalar sentinel (mirrors steeer_util)
    height, width, _ = frame.shape
    if len(lane_lines) == 1:
        x1, _, x2, _ = lane_lines[0][0]
        x_offset = x2 - x1
    else:
        _, _, left_x2, _ = lane_lines[0][0]
        _, _, right_x2, _ = lane_lines[1][0]
        mid = int(width / 2)
        x_offset = (left_x2 + right_x2) / 2 - mid
    y_offset = int(height / 2)
    angle = int(np.arctan(x_offset / y_offset) * 180.0 / np.pi) + 90
    return x_offset + mid, y_offset, angle


def draw_heading(frame, angle, color, width=5):
    h, w, _ = frame.shape
    if angle is None:
        return frame
    rad = angle / 180.0 * np.pi
    x1, y1 = int(w / 2), h
    x2 = int(x1 - h / 2 / np.tan(rad)) if np.tan(rad) != 0 else x1
    y2 = int(h / 2)
    img = frame.copy()
    cv2.line(img, (x1, y1), (x2, y2), color, width)
    cv2.circle(img, (x2, y2), 12, (0, 255, 0), -1)
    return img


# ---------------------------------------------------------------------------
def imread_u(path):
    """Chinese-path-safe imread (cv2.imread returns None on Windows for non-ASCII paths)."""
    raw = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(raw, cv2.IMREAD_COLOR)


def brightness_of(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def process(dataset_dir, hsv_txt, levels, sample, mask_min):
    img_dir = os.path.join(dataset_dir, "images")
    label_file = os.path.join(dataset_dir, "label.txt")
    if not os.path.isfile(label_file):
        print(f"[ERR] no label.txt in {dataset_dir}")
        sys.exit(1)

    rows = []
    with open(label_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, angle = line.split(' ')
            rows.append((name, float(angle)))

    records = []
    for name, stored in rows:
        path = os.path.join(img_dir, name)
        frame = imread_u(path)   # FIX: cv2.imread fails on Chinese paths on Windows
        if frame is None:
            continue
        mask_raw = detect_edges(frame, hsv_txt, reject=False)
        mask = detect_edges(frame, hsv_txt, reject=True)
        total_px = frame.shape[0] * frame.shape[1]
        raw_frac = (mask_raw > 0).sum() / total_px   # true pixel coverage (0..1)
        mask_frac = (mask > 0).sum() / total_px
        roi = region_of_interest(mask)
        segs = detect_line_segments(roi)
        lanes = average_slope_intercept(frame, segs)
        # labeling writes a label ONLY when 2 lines are found
        detect_ok = (len(lanes) == 2)
        recomputed = None
        if detect_ok:
            res = compute_steering_angle(frame, lanes)
            if isinstance(res, tuple):
                recomputed = res[2]
        mismatch = (detect_ok and recomputed is not None
                    and abs(recomputed - stored) > 10)
        records.append({
            'name': name, 'stored': stored, 'bright': brightness_of(frame),
            'raw_frac': raw_frac, 'mask_frac': mask_frac,
            'rejected_frac': raw_frac - mask_frac,
            'detect_ok': detect_ok,
            'recomputed': recomputed, 'mismatch': mismatch,
            'frame': frame, 'mask': mask,
        })

    # bucket by brightness quantiles
    brights = np.array([r['bright'] for r in records])
    edges = np.quantile(brights, np.linspace(0, 1, levels + 1))
    for r in records:
        b = r['bright']
        lvl = np.searchsorted(edges[1:-1], b, side='left')
        r['level'] = int(lvl)

    print(f"\nTotal labeled images processed : {len(records)}")
    print(f"Brightness range (V mean)       : {brights.min():.1f} .. {brights.max():.1f}")
    print(f"Lighting buckets (by brightness): {levels}  "
          f"[edges: {', '.join(f'{e:.0f}' for e in edges)}]\n")
    hdr = (f"{'Lvl':>3} {'Vmean':>7} {'#img':>6} {'detectFail%':>12} {'mismatch%':>10} "
           f"{'rawMask%':>9} {'finMask%':>9} {'rej%':>7} {'meanAngle':>9}")
    print(hdr)
    print("-" * len(hdr))

    out_dir = "qc_output"
    os.makedirs(out_dir, exist_ok=True)
    summary = []
    for lvl in range(levels):
        grp = [r for r in records if r['level'] == lvl]
        if not grp:
            continue
        n = len(grp)
        fail = sum(1 for r in grp if not r['detect_ok'])
        mm = sum(1 for r in grp if r['mismatch'])
        mean_ang = np.mean([r['stored'] for r in grp])
        vmean = np.mean([r['bright'] for r in grp])
        raw_pct = 100 * np.mean([r['raw_frac'] for r in grp])
        fin_pct = 100 * np.mean([r['mask_frac'] for r in grp])
        rej_pct = 100 * np.mean([r['rejected_frac'] for r in grp])
        print(f"{lvl:>3} {vmean:>7.1f} {n:>6} {100*fail/n:>11.1f}% {100*mm/n:>9.1f}% "
              f"{raw_pct:>8.2f}% {fin_pct:>8.2f}% {rej_pct:>6.2f}% {mean_ang:>9.1f}")
        summary.append([lvl, round(vmean, 1), n, round(100*fail/n, 1), round(100*mm/n, 1),
                        round(raw_pct, 2), round(fin_pct, 2), round(rej_pct, 2), round(mean_ang, 1)])

        # dump a few overlays
        lvl_dir = os.path.join(out_dir, f"level_{lvl}")
        os.makedirs(lvl_dir, exist_ok=True)
        for r in grp[:sample]:
            vis = r['frame'].copy()
            m = r['mask']
            vis[m > 0] = (0, 0, 255)  # red overlay where yellow detected (after rejection)
            vis = draw_heading(vis, r['stored'], (0, 255, 0))       # green = stored label
            vis = draw_heading(vis, r['recomputed'], (255, 0, 0))   # blue  = recomputed
            txt = f"stored={r['stored']:.0f} recomp={r['recomputed']} det={'OK' if r['detect_ok'] else 'FAIL'}"
            cv2.putText(vis, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.imwrite(os.path.join(lvl_dir, r['name']), vis)

    with open(os.path.join(out_dir, "summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["level", "vmean", "n_images", "detect_fail_pct", "mismatch_pct",
                    "raw_mask_pct", "final_mask_pct", "rejected_pct", "mean_stored_angle"])
        w.writerows(summary)

    print(f"\nOverlays + summary.csv written to ./{out_dir}/")
    print("Green = stored label | Blue = recomputed-from-detection | Red = detected yellow mask (AFTER rejection).")
    print("rawMask%  = yellow-ish pixels BEFORE white-area rejection (includes false-yellow white floor).")
    print("finMask%  = yellow pixels AFTER  rejection (should be ~just the line, similar across levels).")
    print("rej%      = fraction of pixels the white-area rejection dropped (high in bright buckets = proof).")
    print("High 'detectFail%' at a bucket = that lighting level's labels are mostly missing/dropped.")
    return records


def main():
    here = os.path.dirname(os.path.realpath(__file__))
    default_ds = os.path.normpath(os.path.join(here, "..", "Lane-Follow-Train", "dataset"))
    default_hsv = os.path.join(here, "hsv-data", "hsv.txt")
    ap = argparse.ArgumentParser(description="Spot-check lane label quality per lighting level.")
    ap.add_argument("--dataset", default=default_ds, help="dataset dir with images/ + label.txt")
    ap.add_argument("--hsv", default=default_hsv, help="hsv.txt used at labeling time")
    ap.add_argument("--levels", type=int, default=4, help="number of brightness buckets (= lighting levels)")
    ap.add_argument("--sample", type=int, default=6, help="overlay images saved per bucket")
    ap.add_argument("--mask-min", type=float, default=0.005, help="min mask area fraction to count as 'line seen' (informational)")
    args = ap.parse_args()
    process(args.dataset, args.hsv, args.levels, args.sample, args.mask_min)


if __name__ == "__main__":
    main()
