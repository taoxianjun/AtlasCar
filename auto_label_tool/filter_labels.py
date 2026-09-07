#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
filter_labels.py  v1.0

Drop extreme-angle labels that are almost always single-line detection noise,
so the model trains on the well-supported steering range and is not pulled by
a few outliers. Angle range is 0..180 (90 = straight); the lane-following
task only needs a modest correction band, so samples far outside it are
discarded rather than clipped (clipping would lie to the model about the angle).

Why [45, 135] (2026-08-27):
  label.txt stats show median=89, p10=73, p90=105, and only 32/2143 (1.5%)
  samples fall outside 45..135. Those tails are the single-line / missed-line
  detection artifacts (check_label_quality marks them as unstable), so dropping
  them is safe and tightens supervision.

Safety:
  - backs up label.txt to label.txt.bak_filter_<ts> BEFORE writing
  - never deletes images; only rewrites label.txt
  - keeps samples with angle in [LOW, HIGH] inclusive

Usage:
  cd auto_label_tool
  python filter_labels.py
  python filter_labels.py ../Lane-Follow-Train/dataset
"""
import os
import sys
import time
import shutil

HERE = os.path.dirname(os.path.realpath(__file__))
DEFAULT_DS = os.path.normpath(os.path.join(HERE, "..", "Lane-Follow-Train", "dataset"))
LOW, HIGH = 45.0, 135.0


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DS
    lp = os.path.join(ds, "label.txt")
    if not os.path.isfile(lp):
        sys.exit(f"[ERR] no label.txt in {ds}")

    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = lp + f".bak_filter_{ts}"
    shutil.copy(lp, bak)
    print(f"[OK] backed up old label.txt -> {bak}")

    rows = [l.strip() for l in open(lp, encoding="utf-8") if l.strip()]
    kept, dropped = [], 0
    for l in rows:
        try:
            name, ang = l.split()
            ang = float(ang)
        except ValueError:
            kept.append(l)   # malformed line: keep as-is, don't guess
            continue
        if ang < LOW or ang > HIGH:
            dropped += 1
        else:
            kept.append(l)

    with open(lp, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")

    print(f"[OK] kept={len(kept)}  dropped={dropped}  "
          f"(angle < {LOW} or > {HIGH})")
    print(f"     new label.txt -> {lp}")


if __name__ == "__main__":
    main()
