import cv2
import numpy as np
import logging
import os

def detect_edges(frame, hsv_txt=None):
    """
    寻找色域 + 腐蚀膨胀

    hsv_txt: path to a 6-line HSV range file (low_h/high_h/low_s/high_s/low_v/
      high_v). When None, defaults to hsv-data/hsv.txt (backward compatible with
      the deployment pipeline). Pass e.g. hsv-data/hsv_auto.txt to re-label under
      the auto-computed (often narrower) yellow range for an experiment.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # 读取色域范围
    base_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if hsv_txt is None:
        hsv_data_dir = os.path.join(base_dir, "hsv-data")
        hsv_data_path = os.path.join(hsv_data_dir, "hsv.txt")
    else:
        hsv_data_path = hsv_txt

    with open(hsv_data_path, 'r') as f:
        content = f.read()
        
    low_h, high_h, low_s, high_s, low_v, high_v = list(map(int, content.split("\n")))
    
    # 设置色域范围
    lower_color = np.array([low_h, low_s, low_v]) 
    upper_color = np.array([high_h, high_s, high_v])
    mask = cv2.inRange(hsv, lower_color, upper_color)
    
    # 腐蚀
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    erode = cv2.erode(mask, kernel, iterations=5)

    # 膨胀
    dilate = cv2.dilate(erode, kernel, iterations=2)

    # 闭运算
    close = cv2.morphologyEx(dilate, cv2.MORPH_CLOSE, kernel, iterations=15)

    # Reject non-lane blobs (white floor / white parking lines / reflections).
    # inRange above is intentionally wide to keep yellow across lighting, but
    # under overexposure white floor / white parking lines / reflections share
    # the yellow hue and get swept in. Keep only thin, fairly-saturated,
    # lane-shaped components; drop big blobs and desaturated (white) ones.
    # (Mirrors the gating in auto_hsv.line_like_mask, kept self-contained so
    #  detect_edges stays import-clean.)
    close = reject_non_lane(close, hsv)
    return close


def reject_non_lane(mask, hsv, min_frac=0.30, min_area=50,
                    min_aspect=2.0, max_border_touch=2, elong_exempt=8,
                    min_mean_s=0):
    """Drop connected components that are NOT lane lines.
      - too big  (area >= min_frac of frame)          -> floor / wall
      - too tiny (area < min_area)                     -> sensor noise
      - hugs 3+ borders AND not elongated              -> floor / wall
      - (saturation gate DISABLED by default: under overexposure the real
        yellow line also desaturates, so a saturation floor would delete the
        line itself. Shape/area/border gates above are what separate line
        from white floor. Keep min_mean_s>0 only as a last-resort guard
        against near-pure-white specks, never as the primary filter.)
      NOTE: set min_mean_s > 0 only with a LOW value (e.g. 8); the previous
      40 was wrong and deleted the line at bright lighting."""
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
    masked_image = cv2.bitwise_and(img, mask)
    return masked_image
    
    
def detect_line_segments(cropped_edges):
    rho = 1  
    angle = np.pi / 180  
    min_threshold = 10  
    minLineLength = 10 
    maxLineGap = 6 
    line_segments = cv2.HoughLinesP(cropped_edges, rho, angle, min_threshold, np.array([]), minLineLength,
                                    maxLineGap)
    if line_segments is None:
        return None
    # Normalize HoughLinesP output. It can return either (N,1,4) or (N,4)
    # depending on OpenCV build; reshape to a flat (N,4) so the caller's
    # unpacking loop is always valid. Without this, the (N,4) case crashes
    # with "cannot unpack non-iterable numpy.int32 object" in
    # average_slope_intercept (mirrors the fix already in check_label_quality).
    return np.array(line_segments).reshape(-1, 4)


def average_slope_intercept(frame, line_segments):
    lane_lines = []
    if line_segments is None:
        logging.info('No line_segment segments detected')
        return lane_lines
    # Normalize to flat (N,4); HoughLinesP may return (N,1,4) or (N,4).
    line_segments = np.array(line_segments).reshape(-1, 4)

    height, width, _ = frame.shape
    left_fit = []
    right_fit = []

    boundary = 1/2
    left_region_boundary = width * (1 - boundary)  
    right_region_boundary = width * boundary 

    for x1, y1, x2, y2 in line_segments:
        if x1 == x2:
            logging.info(f'skipping vertical line segment (slope=inf): {(x1, y1, x2, y2)}')
            continue
        fit = np.polyfit((x1, x2), (y1, y2), 1)
        slope = fit[0]
        intercept = fit[1]
        if slope < 0:
            if x1 < left_region_boundary and x2 < left_region_boundary:
                left_fit.append((slope, intercept))
        else:
                if x1 > right_region_boundary and x2 > right_region_boundary:
                    right_fit.append((slope, intercept))

    if len(left_fit) > 0:
        left_fit_average = np.average(left_fit, axis=0)
        lane_lines.append(make_points(frame, left_fit_average))

    if len(right_fit) > 0:
        right_fit_average = np.average(right_fit, axis=0)
        lane_lines.append(make_points(frame, right_fit_average))

    return lane_lines


def make_points(frame, line):
    height, width, _ = frame.shape
    slope, intercept = line
    y1 = height 
    y2 = int(y1 * 1 / 2)  

    x1 = max(-width, min(2 * width, int((y1 - intercept) / slope)))
    x2 = max(-width, min(2 * width, int((y2 - intercept) / slope)))
    return [[x1, y1, x2, y2]]


def display_lines(frame, lines, line_color=(0, 255, 0), line_width=5): # revise
    line_image = np.zeros_like(frame)
    if lines is not None:
        for line in lines:
            for x1, y1, x2, y2 in line:
                cv2.line(line_image, (x1, y1), (x2, y2), line_color, line_width)
    line_image = cv2.addWeighted(frame, 0.8, line_image, 1, 1)
    return line_image