# check_hsv.py  v3
# Purpose: sample yellow lane-line HSV range from a test image,
#          with real-time mask feedback and right-click UNDO of last point.
import cv2
import os
import configparser
import numpy as np

config = configparser.ConfigParser()
cur_dir_path = os.path.dirname(os.path.realpath(__file__))
cfg_dir_path = os.path.join(cur_dir_path, "config")
cfg_file_path = os.path.join(cfg_dir_path, 'hsv_file_setting.ini')
config.read(cfg_file_path)
image_test_path = config['DEFAULT']['imagepath']

tmp_folder_name = "hsv-data"
tmp_file_path = os.path.join(tmp_folder_name, "hsv.txt")

# Load prior range if exists (accumulation across light conditions).
# WARNING: if a previous run sampled wrong (too-wide range), delete hsv.txt first!
if os.path.exists(tmp_file_path):
    with open(tmp_file_path, 'r') as f:
        h_min, h_max, s_min, s_max, v_min, v_max = [int(x) for x in f.read().split('\n')]
    print(f"[warn] existing hsv.txt loaded: H[{h_min},{h_max}] S[{s_min},{s_max}] V[{v_min},{v_max}]")
    print("        if this range is wrong, delete hsv-data/hsv.txt and re-run.")
    has_prior = True
else:
    h_min = h_max = s_min = s_max = v_min = v_max = -1
    has_prior = False

frame = cv2.imread(image_test_path)
if frame is None:
    raise SystemExit(f"cannot read image: {image_test_path}")
orig = frame.copy()              # clean copy for re-drawing after undo
hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

h_list, s_list, v_list = [], [], []
points = []                      # (x, y) of sampled pixels, for undo + redraw

def recompute_range():
    """Recompute min/max from sampled lists (call after add/undo)."""
    global h_min, h_max, s_min, s_max, v_min, v_max
    if not h_list:
        h_min = h_max = s_min = s_max = v_min = v_max = -1
        return
    h_min, h_max = min(h_list), max(h_list)
    s_min, s_max = min(s_list), max(s_list)
    v_min, v_max = min(v_list), max(v_list)
    if h_max - h_min < 4: h_max = min(179, h_min + 4)
    if s_max - s_min < 4: s_max = min(255, s_min + 4)
    if v_max - v_min < 4: v_max = min(255, v_min + 4)

def redraw():
    """Repaint the original image with remaining sampled points."""
    global frame
    frame = orig.copy()
    for (x, y) in points:
        cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)
    cv2.imshow("image", frame)

def update_mask():
    if h_min < 0:
        cv2.imshow("mask", orig)
        return
    lower = np.array([h_min, s_min, v_min])
    upper = np.array([h_max, s_max, v_max])
    mask = cv2.inRange(hsv, lower, upper)
    overlay = orig.copy()
    overlay[mask > 0] = (0, 0, 255)  # red where selected
    cv2.imshow("mask", overlay)

def click_event(event, x, y, flags, params):
    global h_min, h_max, s_min, s_max, v_min, v_max
    if event == cv2.EVENT_LBUTTONDOWN:
        h = int(hsv[y, x, 0]); s = int(hsv[y, x, 1]); v = int(hsv[y, x, 2])
        h_list.append(h); s_list.append(s); v_list.append(v); points.append((x, y))
        print(f"clicked HSV = ({h}, {s}, {v})")
        redraw()
        recompute_range()
        update_mask()
    elif event == cv2.EVENT_RBUTTONDOWN:
        # undo last point (handy when you mis-click on background)
        if points:
            points.pop(); h_list.pop(); s_list.pop(); v_list.pop()
            print("undo last point")
            recompute_range()
            redraw()
            update_mask()
        else:
            print("nothing to undo")

cv2.namedWindow("image", cv2.WINDOW_NORMAL)
cv2.imshow("image", frame)
cv2.setMouseCallback("image", click_event)
update_mask()
print("Left-click YELLOW lane lines. Right-click to UNDO last point.")
print("Watch 'mask': red should cover ONLY the yellow lines.")
print("Press any key to SAVE & exit. Ctrl+C aborts WITHOUT saving.")
cv2.waitKey(0)
cv2.destroyAllWindows()

if h_min < 0:
    # guard: never write the -1 placeholder, or it will corrupt future runs
    # (next run loads -1 as "existing range" and min(-1, real) stays -1).
    print("[warn] no point was sampled (h_min<0). hsv.txt NOT written.")
    print("        re-run check_hsv.py, click yellow lines, then press any KEY to exit.")
else:
    if has_prior and os.path.exists(tmp_file_path):
        with open(tmp_file_path, 'r') as f:
            fh_min, fh_max, fs_min, fs_max, fv_min, fv_max = [int(x) for x in f.read().split('\n')]
        h_min, h_max = min(fh_min, h_min), max(fh_max, h_max)
        s_min, s_max = min(fs_min, s_min), max(fs_max, s_max)
        v_min, v_max = min(fv_min, v_min), max(fv_max, v_max)
    os.makedirs(tmp_folder_name, exist_ok=True)
    with open(tmp_file_path, 'w') as f:
        f.write(f"{h_min}\n{h_max}\n{s_min}\n{s_max}\n{v_min}\n{v_max}")
    print(f"Saved HSV range -> H:[{h_min},{h_max}] S:[{s_min},{s_max}] V:[{v_min},{v_max}]")
    print(f"            file: {tmp_file_path}")
