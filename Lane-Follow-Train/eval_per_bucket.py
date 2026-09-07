"""Per-brightness-bucket RMSE evaluation for the lane-following model.

The training goal is not just a low AVERAGE RMSE, but a model that behaves
consistently across all 4 capture lighting levels (the robustness half of the
plan). This script re-builds the SAME validation split used in training
(split_data, seed=42, 4 brightness buckets) and reports RMSE per bucket so we
can see whether one lighting level is systematically worse.

Run:  python eval_per_bucket.py
"""
import math
import os

import numpy as np
import torch
import cv2
import yaml
from collections import defaultdict
from tqdm.auto import tqdm

from utils import split_data, get_transforms, _img_brightness
from torchvision.models import resnet18

with open('config.yaml') as f:
    cfg = yaml.safe_load(f)

H = cfg['common']['height']
W = cfg['common']['width']
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# ---- rebuild the exact val split used in training (seed=42, 4 buckets) ----
train_l, val_l = split_data(cfg['common']['dataset_path'])
_, val_transform = get_transforms(H, W)

image_dir = os.path.join(cfg['common']['dataset_path'], 'images')

# Recompute bucket edges the SAME way split_data does: over ALL labels.
with open(os.path.join(cfg['common']['dataset_path'], 'label.txt'), 'r', encoding='utf-8') as f:
    all_labels = [l.strip() for l in f if l.strip()]
brites_all = {}
for l in all_labels:
    nm = l.split(' ')[0]
    if nm not in brites_all:
        brites_all[nm] = _img_brightness(image_dir, nm)
bvals = np.array([v for v in brites_all.values() if v is not None])
edges = np.quantile(bvals, np.linspace(0, 1, 5))  # n_buckets = 4


def bucket_of(b):
    if b is None:
        return 0
    return int(np.searchsorted(edges[1:-1], b, side='left'))


# ---- load best model ----
model = resnet18(pretrained=True)
model.fc = torch.nn.Linear(512, 1)
model.load_state_dict(torch.load(os.path.join(cfg['common']['output_dir'], 'lfnet.pth'),
                                 map_location=device))
model.to(device)
model.eval()

# ---- per-bucket inference ----
per_bucket_sq = defaultdict(list)
for l in tqdm(val_l, desc='eval'):
    name, lab = l.split(' ')
    lab = float(lab)
    b = bucket_of(brites_all.get(name))
    raw = np.fromfile(os.path.join(image_dir, name), dtype=np.uint8)
    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if img is None:
        continue
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    t = val_transform(image=img)['image'].unsqueeze(0).to(device)
    with torch.no_grad():
        pred = model(t).item()
    per_bucket_sq[b].append((pred - lab) ** 2)

print('\n===== Per-brightness-bucket RMSE (val set) =====')
all_sq = []
for b in sorted(per_bucket_sq):
    sq = per_bucket_sq[b]
    rmse = math.sqrt(np.mean(sq)) if sq else float('nan')
    rng = f"V_mean in [{edges[b]:.1f}, {edges[b+1]:.1f})" if b + 1 < len(edges) else \
          f"V_mean >= {edges[b]:.1f}"
    print(f"  bucket {b} (n={len(sq):3d}, {rng}): RMSE = {rmse:6.2f} deg")
    all_sq += sq
print(f"  {'-'*52}")
print(f"  OVERALL (n={len(all_sq)}): RMSE = {math.sqrt(np.mean(all_sq)):.2f} deg")
