# -*- coding: utf-8 -*-
"""
capture.py  v1.0  --  Lane-Following raw dataset capture (camera snapshot)

Collects raw road-surface frames into auto_label_tool/data/images/ with the
numeric filenames that auto_label_tool/main.py expects:
    -> 1.jpg, 2.jpg, 3.jpg ...   (note: 0.jpg is SKIPPED by main.py on purpose)

Run this on the DK (the board that has the camera) or any machine with a webcam.

Usage:
    python capture.py                      # manual: press SPACE to save one frame
    python capture.py --auto --fps 5       # auto capture at 5 fps
    python capture.py --device 0 --out data/images

Keys:  SPACE = save one frame,  q = quit
"""
import argparse
import os
import cv2
import time


def next_index(out_dir):
    """Next free numeric index, starting at 1 (0 is skipped by main.py)."""
    existing = []
    if os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            base = f.split('.')[0]
            if base.isdigit():
                existing.append(int(base))
    return (max(existing) + 1) if existing else 1


def main():
    ap = argparse.ArgumentParser(description="Capture lane-following dataset")
    ap.add_argument('--device', type=int, default=0, help='camera device id')
    ap.add_argument('--out', default='data/images', help='output image dir')
    ap.add_argument('--width', type=int, default=640)
    ap.add_argument('--height', type=int, default=480)
    ap.add_argument('--auto', action='store_true', help='auto capture at --fps')
    ap.add_argument('--fps', type=float, default=5.0, help='auto capture fps')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    idx = next_index(args.out)
    print("[INFO] saving to '%s', starting at %d.jpg" % (args.out, idx))

    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        raise SystemExit("[ERR] cannot open camera device %d" % args.device)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    last_save = 0.0
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERR] failed to read frame")
            break
        cv2.imshow("capture  (SPACE=save  q=quit)", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

        do_save = False
        if args.auto:
            now = time.time()
            if now - last_save >= 1.0 / args.fps:
                do_save = True
                last_save = now
        elif key == ord(' '):
            do_save = True

        if do_save:
            path = os.path.join(args.out, "%d.jpg" % idx)
            cv2.imwrite(path, frame)
            print("[SAVE] %s" % path)
            idx += 1

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
