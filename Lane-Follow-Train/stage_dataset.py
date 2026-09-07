#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage_dataset.py  v1.0

Copies the latest auto_label_tool/dataset-* output into
Lane-Follow-Train/dataset/ in the exact layout that
utils.prepare_dataset expects:
    dataset/images/*.jpg   +   dataset/label.txt

It also validates label.txt:
  - each line: "<image_name> <steering_angle>"
  - the referenced image must exist
  - steering_angle must be a float within [0, 180]
  - prints straight / left / right sample counts

Usage:
  python stage_dataset.py
  python stage_dataset.py --auto_label_dir ../auto_label_tool --train_dataset ./dataset
  python stage_dataset.py --source /abs/path/to/dataset-2026-08-20-...
"""
import argparse
import glob
import os
import shutil
import sys

# straight band: 90 +/- 5 ; <85 left ; >95 right (auto_label_tool 0..180 scale)
STRAIGHT_BAND = 5


def find_latest_dataset(auto_label_dir):
    cands = sorted(glob.glob(os.path.join(auto_label_dir, 'dataset-*')),
                   key=os.path.getmtime, reverse=True)
    return cands[0] if cands else None


def main():
    here = os.path.dirname(os.path.realpath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--auto_label_dir',
                    default=os.path.join(here, '..', 'auto_label_tool'))
    ap.add_argument('--train_dataset', default=os.path.join(here, 'dataset'))
    ap.add_argument('--source', default=None,
                    help='explicit dataset-* path to stage')
    args = ap.parse_args()

    src = args.source or find_latest_dataset(args.auto_label_dir)
    if not src or not os.path.isdir(src):
        sys.exit(f'[ERR] no auto_label dataset found (looked in {args.auto_label_dir})')

    img_src = os.path.join(src, 'images')
    lbl_src = os.path.join(src, 'label.txt')
    if not os.path.isdir(img_src) or not os.path.isfile(lbl_src):
        sys.exit(f'[ERR] {src} missing images/ or label.txt')

    dst_img = os.path.join(args.train_dataset, 'images')
    dst_lbl = os.path.join(args.train_dataset, 'label.txt')
    os.makedirs(dst_img, exist_ok=True)

    # remove stale images to avoid mixing datasets
    for f in os.listdir(dst_img):
        os.remove(os.path.join(dst_img, f))

    valid, bad = 0, 0
    straight = left = right = 0
    with open(lbl_src, 'r') as fin, open(dst_lbl, 'w') as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            parts = line.split(' ')
            if len(parts) != 2:
                bad += 1
                continue
            name, val = parts
            img_path = os.path.join(img_src, name)
            if not os.path.isfile(img_path):
                bad += 1
                continue
            try:
                v = float(val)
            except ValueError:
                bad += 1
                continue
            if not (0.0 <= v <= 180.0):
                bad += 1
                continue
            shutil.copy(img_path, os.path.join(dst_img, name))
            fout.write(f'{name} {val}\n')
            valid += 1
            if abs(v - 90) <= STRAIGHT_BAND:
                straight += 1
            elif v < 90:
                left += 1
            else:
                right += 1

    print(f'[OK] staged from : {src}')
    print(f'     valid samples : {valid}')
    print(f'     skipped/bad   : {bad}')
    print(f'     straight/left/right = {straight}/{left}/{right}')

    if valid == 0:
        sys.exit('[ERR] nothing valid staged')

    over = 0
    with open(dst_lbl) as f:
        for line in f:
            v = float(line.split(' ')[1])
            if v > 135:
                over += 1
    if over:
        print(f'[WARN] {over} samples have steering>135. '
              f'Make sure lane_following.py uses the 0..180 bucket scheme '
              f'(see the fix), or these sharp turns will not steer on the car.')


if __name__ == '__main__':
    main()
