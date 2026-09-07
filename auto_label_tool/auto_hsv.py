#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# auto_hsv.py  v2
# Automatic HSV-range calibration + interactive mask QA.
# Replaces the manual point-click step of check_hsv.py:
#   given a test image, it auto-detects yellow lane pixels, computes the
#   H/S/V min/max range, then shows a red overlay for manual QA:
#   The auto-detector requires SATURATED yellow (high S) + line-like connected
#   components, so a warm-lit DESATURATED pale floor is rejected (fixes the
#   'all-red' failure where floor/wall matched the yellow hue).
#     - L-click/drag a RED blob -> DELETE it (bounds tighten)
#     - R-click/drag a MISSED yellow line -> ADD it (bounds widen)
#   Enter/c writes hsv-data/hsv.txt (+ .bak backup) and hsv_auto.txt.
# It does NOT overwrite hsv-data/hsv.txt until you confirm & press Enter/c.
#
# Usage:
#   python auto_hsv.py                  # use imagepath from config/hsv_file_setting.ini
#   python auto_hsv.py --image foo.jpg  # use a specific image
#   python auto_hsv.py --autopick       # scan data/images, pick the one with most yellow px
#
# Output:
#   hsv-data/hsv_auto.txt               # 6 lines: h_min h_max s_min s_max v_min v_max
#   hsv-data/preview.png                # red overlay showing what was detected as yellow
import os
import glob
import argparse
import configparser
import shutil
import time
import cv2
import numpy as np

# Single-digit S guard. The previous floor of 40 was too high and rejected
# genuinely pale yellow lines (S ~ 20-60), so right-clicks on them did nothing.
# 10 only blocks true noise / dark background (S 0-9); pale lines (S >= 20)
# still widen the range and inRange can pick them up.
S_ABS_FLOOR = 10

# Lower-bound guards for H and V during interactive edits. The observed
# failure mode is NOT only S dropping to single digits, but the entire HSV
# ranges drifting downward:
#   * H_min drifting from ~22 down to 15 -- that's orange / yellow-green
#     territory, not yellow. Floor at 18 keeps us out of the orange regime.
#   * V_min drifting from ~82 down to 51 -- that's deep shadow / asphalt.
#     Floor at 80 keeps us out of dim ground territory. V=80 also matches
#     the nominal seed's v=(80,255) lower edge, so it doesn't reject any
#     legitimately-detected yellow pixel.
# These three floors together ensure no single dimension can drag the saved
# HSV range into non-yellow pixel space, no matter how the user clicks.
H_ABS_FLOOR = 20
V_ABS_FLOOR = 90


def load_image(imagepath):
    # cv2.imread fails on Chinese paths on Windows -> use imdecode + fromfile
    data = np.fromfile(imagepath, dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        raise SystemExit(f"cannot read image: {imagepath}")
    return frame


def seed_mask(hsv, h=(18, 42), s=(20, 255), v=(60, 255)):
    """Initial yellow guess mask (OpenCV HSV: H 0-179, S/V 0-255)."""
    return cv2.inRange(
        hsv,
        np.array([h[0], s[0], v[0]]),
        np.array([h[1], s[1], v[1]]),
    )


def detect_mask(hsv):
    """Try increasingly relaxed yellow seeds; for each, keep only LINE-LIKE
    connected components (see line_like_mask) before accepting. This prevents
    the calibration from locking onto floor/wall blobs that share the yellow hue
    under warm / low-contrast lighting (the 'all-red' failure).
    Handles mild light-shift (yellow -> orange/whiter) but NOT extreme
    color-temperature shift (yellow -> cyan), which still needs manual check."""
    schedules = [
        # S is THE discriminator between a saturated yellow line and a
        # yellow-tinted desaturated floor / crack. Keep S_min high so the ground
        # cracks (S ~ 60-100) don't pollute the line color range.
        dict(h=(15, 45), s=(110, 255), v=(80, 255)),  # nominal saturated yellow
        dict(h=(5, 55),   s=(70, 255), v=(50, 255)),  # relaxed (dimmer / less saturated)
        # No 'very relaxed' fallback: S_min=15 would re-admit desaturated ground
        # cracks and recreate the speckled / all-red failure. If both above fail
        # the gating, the image is not calibratable -> main() will print
        # 'too few yellow pixels' and you skip it.
    ]
    for sch in schedules:
        m = seed_mask(hsv, **sch)
        g = line_like_mask(m, hsv)         # gate: keep only line-like blobs
        if int((g > 0).sum()) >= 200:
            return g, sch
    # none of the schedules produced a line-like mask with enough px:
    # return the last schedule's gated mask anyway (may be empty -> caller skips)
    return line_like_mask(seed_mask(hsv, **schedules[-1]), hsv), schedules[-1]


def bounds_from_mask(hsv, mask, lo=2.0, hi=98.0):
    """Compute H/S/V range from mask pixels using percentiles (robust to
    long-tail extremes, unlike min/max) + small margin + min span.
    Returns (h_min,h_max,s_min,s_max,v_min,v_max), area. None if too few px."""
    area = int((mask > 0).sum())
    if area < 50:
        return None, area
    ys = hsv[:, :, 0][mask > 0].astype(np.float32)
    ss = hsv[:, :, 1][mask > 0].astype(np.float32)
    vs = hsv[:, :, 2][mask > 0].astype(np.float32)
    h_min, h_max = np.percentile(ys, lo), np.percentile(ys, hi)
    s_min, s_max = np.percentile(ss, lo), np.percentile(ss, hi)
    v_min, v_max = np.percentile(vs, lo), np.percentile(vs, hi)
    # margin. Keep H margin small (2). S/V margin tightened from 5 -> 2 so a
    # genuinely pale line (S ~ 15) is not dragged to S=10 by the margin alone
    # (that was one source of the 'right-click collapses S to ~10' report).
    # A 2-px margin still keeps the inRange window from clipping the line's
    # own edge pixels.
    h_min, h_max = max(0, h_min - 2), min(179, h_max + 2)
    s_min, s_max = max(0, s_min - 2), min(255, s_max + 2)
    v_min, v_max = max(0, v_min - 2), min(255, v_max + 2)
    # enforce minimum span (avoid razor-thin ranges)
    if h_max - h_min < 4:
        h_max = min(179, h_min + 4)
    if s_max - s_min < 4:
        s_max = min(255, s_min + 4)
    if v_max - v_min < 4:
        v_max = min(255, v_min + 4)
    return (int(round(h_min)), int(round(h_max)), int(round(s_min)),
            int(round(s_max)), int(round(v_min)), int(round(v_max))), area


def line_like_mask(mask, hsv, min_frac=0.30, min_area=50, min_aspect=2.0,
                   max_border_touch=2, elong_exempt=8, min_mean_s=80):
    """Keep only connected components that look like lane lines. Rejects:
      - too big  (area >= min_frac of the frame)          -> floor / wall
      - too tiny (area < min_area)                         -> sensor noise
      - hugs 3+ frame borders AND not extremely elongated  -> floor / wall
      - mean saturation (S) below min_mean_s                -> desaturated cracks
        / yellow-tinted ground specks (this is the speckled-floor fix)
    A full-width thin line (aspect >= elong_exempt) is exempt from the border
    rule so legitimately edge-to-edge lane lines survive.
    Returns a uint8 0/1 mask of the surviving components."""
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
        frac = area / total
        if frac >= min_frac:
            continue
        aspect = max(w, h) / max(1, min(w, h))
        touches = (1 if y <= 0 else 0) + (1 if y + h >= H - 1 else 0) + \
                  (1 if x <= 0 else 0) + (1 if x + w >= W - 1 else 0)
        if touches > max_border_touch and aspect < elong_exempt:
            continue
        # NEW: reject desaturated components (yellow-tinted ground cracks vs
        # a real saturated yellow line). mean S of the component must be high.
        mean_s = float(s_channel[labels == i].mean())
        if mean_s < min_mean_s:
            continue
        keep[labels == i] = 1
    return keep


def calibrate(hsv):
    mask, sch = detect_mask(hsv)
    result, area = bounds_from_mask(hsv, mask)
    return result, area, sch


def auto_pick(folder):
    best_path, best_area, best_hsv = None, -1, None
    paths = glob.glob(os.path.join(folder, "*.jpg")) + \
            glob.glob(os.path.join(folder, "*.png"))
    for i, p in enumerate(paths):
        if i >= 1032:   # cap scan cost
            break
        im = load_image(p)
        if im is None:
            continue
        hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
        m, _ = detect_mask(hsv)
        area = int((m > 0).sum())
        if area > best_area:
            best_area, best_path, best_hsv = area, p, hsv
    return best_path, best_area, best_hsv


def interactive_mask_confirm(frame, hsv, init_bounds, preview_path, imagepath=None):
    """Interactive mask QA: show red overlay.
    LEFT button:
      - click a RED blob you think is wrong -> drop ALL red pixels of that
        COLOR (color-based, not connected-component: a clearly-different false
        region is removed without taking the real line with it)
      - drag a box -> drop all red pixels inside
      -> re-calibrates H/S/V from the REMAINING yellow (bounds only TIGHTEN).
    RIGHT button (use when the auto-mask MISSED a yellow line):
      - click on the missed yellow -> flood-fill that similarly-colored region and
        add it to the mask (teaches the model the right color)
      - drag -> brush-paint a stroke onto the line
      -> re-calibrates H/S/V from ALL marked yellow (bounds WIDEN to include it,
         then inRange re-covers the whole line automatically).
    Enter/c saves, s skips, r resets to initial.
    Returns final (h_min..v_max) bounds, or None if skipped.
    """
    h_min, h_max, s_min, s_max, v_min, v_max = init_bounds
    mask = cv2.inRange(
        hsv,
        np.array([h_min, s_min, v_min]),
        np.array([h_max, s_max, v_max]),
    )
    excluded = np.zeros_like(mask)   # hard-excluded bad blobs (left-click)
    added = np.zeros_like(mask)      # user-painted yellow (right-click)

    def effective(st):
        """Final shown mask = (auto | painted) minus excluded.
        NOTE: `mask | ~excluded` is wrong on uint8 (~1==254). Explicit zeroing."""
        m = st["mask"].copy()
        m[st["added"] > 0] = 1
        m[st["excluded"] == 1] = 0
        return m

    state = {"mask": mask, "excluded": excluded, "added": added,
             "bounds": init_bounds, "init_bounds": init_bounds,
             "hsv": hsv, "frame": frame, "out": None,
             "drag": None, "drag_rect": None,
             "r_drag": None, "r_drag_rect": None,
             "history": [], "tb_dirty": False, "tb_last": 0.0}

    def sync_trackbars(b):
        """Push the 6 bound values into the OpenCV trackbar positions so the
        sliders always reflect state['bounds'] (after recalib / reset)."""
        cv2.setTrackbarPos("H_min", "mask", b[0])
        cv2.setTrackbarPos("H_max", "mask", b[1])
        cv2.setTrackbarPos("S_min", "mask", b[2])
        cv2.setTrackbarPos("S_max", "mask", b[3])
        cv2.setTrackbarPos("V_min", "mask", b[4])
        cv2.setTrackbarPos("V_max", "mask", b[5])

    def push_undo():
        """Snapshot (mask, added, excluded, bounds) onto the undo stack BEFORE a
        user edit, so 'u' can restore the previous state. Cap the stack to bound
        memory (each snapshot is ~3 masks + bounds)."""
        st = state
        st["history"].append(
            (st["mask"].copy(), st["added"].copy(), st["excluded"].copy(),
             st["bounds"]))
        if len(st["history"]) > 30:
            st["history"].pop(0)

    def undo():
        """Restore the most recent snapshot (key 'u')."""
        st = state
        if not st["history"]:
            print("[undo] nothing to undo")
            return
        m, a, e, b = st["history"].pop()
        st["mask"], st["added"], st["excluded"], st["bounds"] = m, a, e, b
        sync_trackbars(b)
        print(f"[undo] restored H[{b[0]},{b[1]}] S[{b[2]},{b[3]}] V[{b[4]},{b[5]}]")
        refresh()

    def refresh():
        m = effective(state)
        out = frame.copy()
        out[m > 0] = (0, 0, 255)
        bm = state["bounds"]
        cv2.putText(out, f"H[{bm[0]},{bm[1]}] S[{bm[2]},{bm[3]}] V[{bm[4]},{bm[5]}]",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(out, "L=del RED blob/box | R=add YELLOW(click=grow,drag=brush) | Enter/c=save | s=skip | r=reset",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        r = state.get("drag_rect")
        if r is not None:
            cv2.rectangle(out, (r[0], r[1]), (r[2], r[3]), (0, 255, 255), 2)
        state["out"] = out

    def recalib(st, widen):
        """Recompute H/S/V from currently-marked yellow.
        widen=True  -> bounds may GROW (right-click add: include painted yellow)
        widen=False -> bounds only TIGHTEN (left-click exclude)."""
        # Sanitize painted pixels: drop any desaturated (low-S) / off-hue
        # (low-H) / dim (low-V) ones so they can never drag the bounds down
        # via the widen() union or the painted-fold step. This is the fix for
        # 'one click and the ranges collapse' (S to single digits, H into
        # orange, V into shadow).
        st["added"][
            (st["hsv"][:, :, 1] < S_ABS_FLOOR)
            | (st["hsv"][:, :, 0] < H_ABS_FLOOR)
            | (st["hsv"][:, :, 2] < V_ABS_FLOOR)
        ] = 0
        eff = effective(st)
        res, area = bounds_from_mask(st["hsv"], eff)
        if res is None:
            print("[warn] too few yellow px marked; bounds kept, pixels hidden")
            return
        # When ADDING (right-click), also fold in the painted pixels' extents so
        # a line's true H/S/V range is reflected (percentile(2/98) in
        # bounds_from_mask would otherwise truncate the orange/whiter tail).
        # BUT use a robust percentile (15/85), NOT raw min/max: a flood-filled
        # region has a ragged edge, and raw min/max would drag a bound all the way
        # to a single outlier pixel -- e.g. one S=10 pixel at the line's dim edge
        # pulling S_min to 10 (the previous 'one right-click -> S collapses to
        # 10' bug). Percentile(15) ignores the lowest 15% of painted pixels, so
        # the bound lands on the painted line's *typical* low value, not its
        # single worst pixel.
        if widen and int(st["added"].sum()) > 0:
            ah = st["hsv"][:, :, 0][st["added"] > 0].astype(np.float32)
            as_ = st["hsv"][:, :, 1][st["added"] > 0].astype(np.float32)
            av = st["hsv"][:, :, 2][st["added"] > 0].astype(np.float32)
            res = (min(res[0], int(round(np.percentile(ah, 15)))), max(res[1], int(round(np.percentile(ah, 85)))),
                   min(res[2], int(round(np.percentile(as_, 15)))), max(res[3], int(round(np.percentile(as_, 85)))),
                   min(res[4], int(round(np.percentile(av, 15)))), max(res[5], int(round(np.percentile(av, 85)))))
        o = st["bounds"]
        if widen:
            nb = (min(o[0], res[0]), max(o[1], res[1]),
                  min(o[2], res[2]), max(o[3], res[3]),
                  min(o[4], res[4]), max(o[5], res[5]))
        else:
            # Left-click EXCLUDE: the user dropped a false-positive red blob/box.
            # Re-derive the range STRICTLY from the REMAINING yellow pixels
            # (the effective mask). We must NOT keep the old bound's extrema via
            # max/min(o, res) -- that preserved the deleted blob's color in the
            # range, so the red area could never be removed ("always comes back"
            # bug). bounds_from_mask already uses percentile(2/98) to trim tails,
            # so a direct assignment is stable and actually removes the deleted
            # color from the range. The floor clamp below still applies.
            nb = (res[0], res[1], res[2], res[3], res[4], res[5])
        # Floor saturation / hue / brightness: interactive edits must never collapse
        # the bounds into non-yellow pixel space (single-digit S, H into orange,
        # V into shadow). These clamps only block implausible lows, not
        # legitimately pale / off-hue / dim-but-still-yellow lines.
        nb = (max(nb[0], H_ABS_FLOOR), nb[1],
              max(nb[2], S_ABS_FLOOR), nb[3],
              max(nb[4], V_ABS_FLOOR), nb[5])
        st["bounds"] = nb
        nm = cv2.inRange(st["hsv"], np.array([nb[0], nb[2], nb[4]]),
                         np.array([nb[1], nb[3], nb[5]]))
        nm[st["excluded"] == 1] = 0
        st["mask"] = nm
        print(f"[recalib {'+' if widen else '-'}] "
              f"H[{nb[0]},{nb[1]}] S[{nb[2]},{nb[3]}] V[{nb[4]},{nb[5]}] (px={area})")
        sync_trackbars(nb)

    def brush(st, p0, p1, r=8):
        """Paint a thick stroke into the added mask (right-drag)."""
        cv2.line(st["added"], p0, p1, 1, thickness=2 * r)

    def grow(st, x, y, htol=10, stol=40, vtol=40):
        """Flood-fill a similarly-colored region from the clicked seed (right-click)."""
        hsv_img = st["hsv"]
        if not (0 <= y < hsv_img.shape[0] and 0 <= x < hsv_img.shape[1]):
            return
        hsv_copy = hsv_img.copy()
        fm = np.zeros((hsv_img.shape[0] + 2, hsv_img.shape[1] + 2), np.uint8)
        cv2.floodFill(hsv_copy, fm, (x, y), (0, 0, 0),
                      (htol, stol, vtol), (htol, stol, vtol),
                      flags=4 | cv2.FLOODFILL_FIXED_RANGE | (1 << 8))
        region = fm[1:-1, 1:-1] > 0
        # floodFill's FIXED_RANGE tolerance (S +- stol=40) is generous, so it
        # also swallows dim "ragged edges" that share the seed's hue but are far
        # less saturated (e.g. a pale line's shadowed border at S=10 next to a
        # S=30 body). Those edge pixels would later drag S_min down to single
        # digits through the painted-fold step. Reject any flooded pixel whose
        # S/H/V deviates from the CLICKED seed by more than a TIGHT tolerance --
        # i.e. keep only pixels that are actually the same color as where the
        # user clicked. This stops S collapsing to ~10, while a genuinely pale
        # line (clicked at S ~ 20-50) is still added normally.
        seed_s = int(hsv_img[y, x, 1])
        seed_h = int(hsv_img[y, x, 0])
        seed_v = int(hsv_img[y, x, 2])
        s_ch = hsv_img[:, :, 1].astype(np.int16)
        h_ch = hsv_img[:, :, 0].astype(np.int16)
        v_ch = hsv_img[:, :, 2].astype(np.int16)
        same_color = (np.abs(s_ch - seed_s) <= 15) & \
                     (np.abs(h_ch - seed_h) <= 12) & \
                     (np.abs(v_ch - seed_v) <= 30)
        # Build the candidate mask first, then filter it through line_like_mask.
        # floodFill's S+-40 tolerance is generous: when the user right-clicks
        # on a DIM (far) section of a yellow line, floodFill also pulls in the
        # nearby desaturated floor / blob, which then lowers S_min in the
        # bounds and inRange catches the WHOLE floor -> 'one right-click and a
        # big area turns red'. line_like_mask drops any blob/floor by SHAPE
        # (aspect, area), not color, so the dim line (thin, elongated) survives
        # and the floor (big square blob) does not. min_mean_s is relaxed to
        # 25 here (vs. 80 in detect_mask) so genuine dim lines still pass.
        candidate = (region & same_color
                     & (hsv_img[:, :, 1] >= S_ABS_FLOOR)
                     & (hsv_img[:, :, 0] >= H_ABS_FLOOR)
                     & (hsv_img[:, :, 2] >= V_ABS_FLOOR)).astype(np.uint8)
        filtered = line_like_mask(
            candidate, hsv_img,
            min_frac=0.25, min_area=40,
            min_aspect=2.0, max_border_touch=3,
            elong_exempt=5, min_mean_s=25,
        )
        st["added"][filtered > 0] = 1

    def on_mouse(event, x, y, flags, param):
        st = param
        # ---------- LEFT: exclude ----------
        if event == cv2.EVENT_LBUTTONDOWN:
            st["drag"] = (x, y)
            st["drag_rect"] = (x, y, x, y)
        elif event == cv2.EVENT_MOUSEMOVE and st["drag"] is not None:
            st["drag_rect"] = (st["drag"][0], st["drag"][1], x, y)
            refresh()
        elif event == cv2.EVENT_LBUTTONUP and st["drag"] is not None:
            x0, y0 = st["drag"]
            x1, y1 = x, y
            st["drag"] = None
            st["drag_rect"] = None
            xa, xb = min(x0, x1), max(x0, x1)
            ya, yb = min(y0, y1), max(y0, y1)
            if xb - xa < 4 and yb - ya < 4:
                m = effective(st)
                if 0 <= y0 < m.shape[0] and 0 <= x0 < m.shape[1] and m[y0, x0] > 0:
                    hsv_img = st["hsv"]
                    seed = hsv_img[y0, x0]
                    # COLOR-BASED exclusion (replaces the old connectedComponents
                    # approach). connectedComponents only looks at spatial
                    # adjacency, NOT color: once bounds are widened (e.g. a
                    # right-click pulled S_min down to ~14 and the whole floor
                    # turned red), the floor and the real yellow line become one
                    # 8-connected blob in the binary mask. Clicking the floor
                    # would then exclude the ENTIRE blob -- including the real
                    # line -- and recalib() would early-return on too-few px,
                    # leaving stale state and the false red re-appearing.
                    # Color-based exclusion removes every red pixel whose HSV is
                    # within tolerance of the clicked one, so a clearly-different
                    # false-red region is wiped out while the differently-colored
                    # real line is untouched. (H is not circular here: yellow
                    # lives in 15-50, far from the 0/179 wrap.)
                    htol, stol, vtol = 14, 55, 55
                    near = (np.abs(hsv_img[:, :, 0].astype(np.int16) - int(seed[0])) <= htol) & \
                           (np.abs(hsv_img[:, :, 1].astype(np.int16) - int(seed[1])) <= stol) & \
                           (np.abs(hsv_img[:, :, 2].astype(np.int16) - int(seed[2])) <= vtol)
                    push_undo()
                    st["excluded"][(m > 0) & near] = 1
                    recalib(st, widen=False)
                else:
                    print("[L-click] not on a red pixel, ignored")
            else:
                m = effective(st)
                sub = m[ya:yb + 1, xa:xb + 1]
                ys, xs = np.where(sub > 0)
                if len(xs) == 0:
                    print("[L-box] no red pixels inside box, ignored")
                else:
                    push_undo()
                    st["excluded"][ya + ys, xa + xs] = 1
                    recalib(st, widen=False)
            refresh()
        # ---------- RIGHT: add (mark missed yellow) ----------
        elif event == cv2.EVENT_RBUTTONDOWN:
            st["r_drag"] = (x, y)
            st["r_drag_rect"] = (x, y, x, y)
        elif event == cv2.EVENT_MOUSEMOVE and st["r_drag"] is not None:
            brush(st, st["r_drag"], (x, y))
            st["r_drag"] = (x, y)
            refresh()
        elif event == cv2.EVENT_RBUTTONUP and st["r_drag"] is not None:
            x0, y0 = st["r_drag"]
            x1, y1 = x, y
            st["r_drag"] = None
            st["r_drag_rect"] = None
            if abs(x1 - x0) < 4 and abs(y1 - y0) < 4:
                grow(st, x0, y0)        # click -> region grow
            # drag case already brushed during MOUSEMOVE
            push_undo()
            recalib(st, widen=True)
            refresh()

    refresh()
    cv2.namedWindow("mask", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("mask", on_mouse, state)
    print("[confirm] L-click/drag RED blob to DELETE; R-click/drag YELLOW to ADD (when auto-mask missed it).")
    print("          Enter/c = WRITE hsv.txt | s = SKIP | r = RESET | u = UNDO | m = save GT mask | trackbars below = drag to edit H/S/V bounds live")

    def on_trackbar(_val):
        """Trackbar callback: drag any slider -> inRange mask recomputed live,
        red overlay updates immediately. Reads all 6 sliders fresh so a single
        drag can never leave the bounds inconsistent (min>max is auto-swapped,
        absolute floors enforced)."""
        h_min = cv2.getTrackbarPos("H_min", "mask")
        h_max = cv2.getTrackbarPos("H_max", "mask")
        s_min = cv2.getTrackbarPos("S_min", "mask")
        s_max = cv2.getTrackbarPos("S_max", "mask")
        v_min = cv2.getTrackbarPos("V_min", "mask")
        v_max = cv2.getTrackbarPos("V_max", "mask")
        # Enforce ordering (min <= max) per dimension
        if h_min > h_max: h_min, h_max = h_max, h_min
        if s_min > s_max: s_min, s_max = s_max, s_min
        if v_min > v_max: v_min, v_max = v_max, v_min
        # Enforce absolute floors (same ones that guard recalib)
        h_min = max(h_min, H_ABS_FLOOR)
        s_min = max(s_min, S_ABS_FLOOR)
        v_min = max(v_min, V_ABS_FLOOR)
        nb = (h_min, h_max, s_min, s_max, v_min, v_max)
        state["tb_last"] = time.time()
        if nb != state["bounds"]:
            # Bounds changed -> switch to a PURE-bounds view. First change of a
            # drag snapshots the pre-drag state onto the undo stack ('u' can
            # restore it), then any stale manual marks (added/excluded) from
            # earlier clicks are dropped so the red overlay is determined ONLY
            # by the slider values -- same values now always give the same
            # overlay. tb_dirty coalesces one continuous drag into ONE undo
            # step instead of one per pixel value.
            if not state["tb_dirty"]:
                push_undo()
                state["tb_dirty"] = True
            if int(state["added"].sum()) > 0 or int(state["excluded"].sum()) > 0:
                state["added"][:] = 0
                state["excluded"][:] = 0
                print("[trackbar] bounds edit -> manual marks cleared (press u to undo)")
            state["bounds"] = nb
            nm = cv2.inRange(state["hsv"], np.array([h_min, s_min, v_min]),
                                        np.array([h_max, s_max, v_max]))
            state["mask"] = nm
            sync_trackbars(nb)   # sync in case we swapped/floored
            refresh()

    # 6 trackbars attached to the "mask" window: H_min/max, S_min/max, V_min/max.
    # Dragging any slider triggers on_trackbar -> mask recomputed, red overlay
    # redrawn live. setTrackbarPos inside on_trackbar does NOT re-trigger the
    # callback (verified in Qt/Win32 backends), so sync_trackbars is safe.
    cv2.createTrackbar("H_min", "mask", h_min, 179, on_trackbar)
    cv2.createTrackbar("H_max", "mask", h_max, 179, on_trackbar)
    cv2.createTrackbar("S_min", "mask", s_min, 255, on_trackbar)
    cv2.createTrackbar("S_max", "mask", s_max, 255, on_trackbar)
    cv2.createTrackbar("V_min", "mask", v_min, 255, on_trackbar)
    cv2.createTrackbar("V_max", "mask", v_max, 255, on_trackbar)

    while True:
        cv2.imshow("mask", state["out"])
        key = cv2.waitKey(20) & 0xFF
        if key == 13 or key == ord('c'):       # Enter or c
            cv2.imwrite(preview_path, state["out"])
            cv2.destroyWindow("mask")
            return state["bounds"]
        if key == ord('s'):
            cv2.destroyWindow("mask")
            return None
        if key == ord('r'):                     # reset to initial
            st = state
            push_undo()
            st["excluded"] = np.zeros_like(st["excluded"])
            st["added"] = np.zeros_like(st["added"])
            b = st["bounds"] = st["init_bounds"]
            st["mask"] = cv2.inRange(
                st["hsv"],
                np.array([b[0], b[2], b[4]]),
                np.array([b[1], b[3], b[5]]),
            )
            sync_trackbars(b)
            print("[reset] restored initial mask/bounds")
            refresh()
        if key == ord('u'):                     # undo last edit (slider/click/reset)
            undo()
        if key == ord('m'):                     # save GT mask (for recall_test.py)
            m = effective(state)
            base_dir = os.path.dirname(os.path.realpath(__file__))
            gt_dir = os.path.join(base_dir, "hsv-data", "gt_masks")
            os.makedirs(gt_dir, exist_ok=True)
            stem = (os.path.splitext(os.path.basename(imagepath))[0]
                    if imagepath else "preview")
            gt_path = os.path.join(gt_dir, stem + ".png")
            cv2.imwrite(gt_path, (m > 0).astype(np.uint8) * 255)
            print(f"[gt] saved human-confirmed mask -> {gt_path} "
                  f"(use recall_test.py --gt-dir hsv-data/gt_masks)")
        # Reset the drag-undo coalesce flag after a quiet period so the NEXT
        # slider drag starts a fresh undo step (one drag == one undo).
        if state["tb_dirty"] and time.time() - state["tb_last"] > 0.35:
            state["tb_dirty"] = False
        # key == 255 (no key) or anything else -> keep looping (mouse still active)


def main():
    here = os.path.dirname(os.path.realpath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=None, help="specific image to calibrate")
    ap.add_argument("--autopick", action="store_true",
                    help="scan data/images, use the one with most yellow px")
    args = ap.parse_args()

    if args.image:
        imagepath = args.image
        frame = load_image(imagepath)
        print(f"[input] --image: {imagepath}")
    elif args.autopick:
        folder = os.path.join(here, "data", "images")
        imagepath, area, _ = auto_pick(folder)
        if imagepath is None:
            raise SystemExit("no image found in data/images")
        frame = load_image(imagepath)
        print(f"[auto-pick] best: {imagepath} (yellow px={area})")
    else:
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(here, "config", "hsv_file_setting.ini"))
        imagepath = os.path.join(here, cfg["DEFAULT"]["imagepath"])
        frame = load_image(imagepath)
        print(f"[input] imagepath from ini: {imagepath}")

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    result, area, sch = calibrate(hsv)
    if result is None:
        raise SystemExit(f"[fail] too few yellow pixels ({area}) - check the image / lighting")

    h_min, h_max, s_min, s_max, v_min, v_max = result

    os.makedirs(os.path.join(here, "hsv-data"), exist_ok=True)
    prev = os.path.join(here, "hsv-data", "preview.png")

    print(f"[result] H:[{h_min},{h_max}] S:[{s_min},{s_max}] V:[{v_min},{v_max}]")
    print(f"         (seed used: H{sch['h']} S{sch['s']} V{sch['v']}, yellow px={area})")

    final_bounds = interactive_mask_confirm(frame, hsv, result, prev, imagepath=imagepath)
    if final_bounds is None:
        print("[skip] hsv.txt NOT written.")
        return

    h_min, h_max, s_min, s_max, v_min, v_max = final_bounds

    # ACCUMULATE: union with any existing hsv.txt so the saved range only grows
    # across images. This is what keeps later images' yellow (e.g. more orange /
    # lower-H lines) from being missed just because one calibration overwrote
    # the file with a narrower range. Delete hsv.txt to start fresh.
    hsv_path = os.path.join(here, "hsv-data", "hsv.txt")
    if os.path.exists(hsv_path):
        try:
            with open(hsv_path) as f:
                old = [int(x) for x in f.read().split()]
            if len(old) == 6:
                h_min, h_max = min(h_min, old[0]), max(h_max, old[1])
                s_min, s_max = min(s_min, old[2]), max(s_max, old[3])
                v_min, v_max = min(v_min, old[4]), max(v_max, old[5])
                print(f"[accumulate] merged with existing hsv.txt {tuple(old)}")
        except Exception as e:
            print(f"[warn] could not read existing hsv.txt, overwriting: {e}")

    # confirm -> write hsv_auto.txt (record, this image only) + hsv.txt (union, main.py)
    auto_path = os.path.join(here, "hsv-data", "hsv_auto.txt")
    with open(auto_path, "w") as f:
        f.write(f"{final_bounds[0]}\n{final_bounds[1]}\n{final_bounds[2]}\n"
                f"{final_bounds[3]}\n{final_bounds[4]}\n{final_bounds[5]}")

    if os.path.exists(hsv_path):
        bak = os.path.join(here, "hsv-data", "hsv.txt.bak")
        shutil.copy2(hsv_path, bak)
        print("[backup] old hsv.txt -> hsv.txt.bak")
    with open(hsv_path, "w") as f:
        f.write(f"{h_min}\n{h_max}\n{s_min}\n{s_max}\n{v_min}\n{v_max}")

    print(f"[saved] {auto_path}  (this image's own range)")
    print(f"[saved] {hsv_path}  (union across all calibrations; main.py uses this)")


if __name__ == "__main__":
    main()
