# -*- coding: utf-8 -*-
"""
rename_images.py  v1.0  --  Normalize phone/camera photos to numeric names

auto_label_tool/main.py requires pure-integer filenames (1.jpg, 2.jpg ...).
Use this to convert photos taken by a phone/camera (any name) into the
expected sequence, ordered by filename or by modification time.

Usage:
    python rename_images.py --src /path/to/photos --out data/images
    python rename_images.py --src /path/to/photos --out data/images --by-mtime --copy

Note: 0.jpg is skipped by main.py, so we start at 1.jpg.
"""
import argparse
import glob
import os
import shutil

VALID_EXT = ('.jpg', '.jpeg', '.png', '.bmp')


def main():
    ap = argparse.ArgumentParser(description="Rename photos to numeric sequence")
    ap.add_argument('--src', required=True, help='folder with source photos')
    ap.add_argument('--out', default='data/images', help='target dir')
    ap.add_argument('--by-mtime', action='store_true', help='sort by modify time')
    ap.add_argument('--copy', action='store_true', help='copy instead of move')
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        raise SystemExit("[ERR] src not found: %s" % args.src)
    os.makedirs(args.out, exist_ok=True)

    files = [f for f in glob.glob(os.path.join(args.src, '*'))
             if os.path.splitext(f)[1].lower() in VALID_EXT]
    if not files:
        raise SystemExit("[ERR] no images found in %s" % args.src)

    if args.by_mtime:
        files.sort(key=os.path.getmtime)
    else:
        files.sort()

    existing = [int(f.split('.')[0]) for f in os.listdir(args.out)
                if f.split('.')[0].isdigit()]
    idx = (max(existing) + 1) if existing else 1

    for f in files:
        dst = os.path.join(args.out, "%d.jpg" % idx)
        if args.copy:
            shutil.copy(f, dst)
        else:
            shutil.move(f, dst)
        idx += 1

    print("[OK] normalized %d images -> %s (started at %d.jpg)"
          % (len(files), args.out, (max(existing) + 1) if existing else 1))


if __name__ == "__main__":
    main()
