# quick_check.py v1
# Headless estimate of how many frames pass lane detection with the CURRENT
# hsv-data/hsv.txt, so you know whether to widen the HSV range BEFORE running
# the full main.py labeling (which pops a window for every frame).
import os
import sys
import cv2

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from utils.lane_util import detect_edges, region_of_interest, detect_line_segments, average_slope_intercept

data_dir = "data/images"
files = sorted(
    [f for f in os.listdir(data_dir) if f.split('.')[0].isdigit() and int(f.split('.')[0]) > 0],
    key=lambda x: int(x.split('.')[0])
)

total = 0
passed = 0
for f in files:
    frame = cv2.imread(os.path.join(data_dir, f))
    if frame is None:
        continue
    total += 1
    edges = detect_edges(frame)
    cropped = region_of_interest(edges)
    segs = detect_line_segments(cropped)
    lines = average_slope_intercept(frame, segs)
    if len(lines) > 1:
        passed += 1

ratio = passed / total if total else 0
print(f"total={total}  passed(>=2 lines)={passed}  ratio={ratio:.1%}")
if ratio < 0.5:
    print("[warn] <50% frames yield 2 lane lines -> HSV range too narrow. "
          "Sample more light conditions with check_hsv.py to widen it.")
else:
    print("[ok] range looks sufficient, you can run main.py to label.")
