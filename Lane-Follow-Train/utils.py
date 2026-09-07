import os
import random
from collections import defaultdict

import albumentations as A
import cv2
import numpy as np
import torch
from albumentations.pytorch.transforms import ToTensorV2
from torch.utils.data import DataLoader
from torch.utils.data import Dataset


class LaneDataset(Dataset):
    def __init__(self, image_dir, labels, transform=None):
        self.image_dir = image_dir
        self.transform = transform
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, index):
        image_name, label = self.labels[index].split(' ')
        label = float(label)

        image_path = os.path.join(self.image_dir, image_name)

        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = self.transform(image=image)['image']

        target = torch.tensor(label)
        return image, target


def _img_brightness(image_dir, name):
    """Mean V channel of an image (brightness proxy); Chinese-path safe."""
    path = os.path.join(image_dir, name)
    raw = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if img is None:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return float(hsv[:, :, 2].mean())


def split_data(data_dir, ratio=0.9, seed=42, n_buckets=4):
    """Stratified train/val split by image brightness.

    A plain random split can leave an entire lighting level only in train or
    only in val, making val_RMSE unrepresentative and hiding light-sensitivity.
    Stratifying by brightness guarantees every lighting level is represented in
    both splits (the "robust across lighting" half of the training goal).
    """
    with open(os.path.join(data_dir, 'label.txt'), 'r', encoding='utf-8') as f:
        all_labels = [l.strip() for l in f if l.strip()]

    image_dir = os.path.join(data_dir, "images")
    brites = {}
    for l in all_labels:
        name = l.split(' ')[0]
        if name not in brites:
            brites[name] = _img_brightness(image_dir, name)

    bvals = np.array([v for v in brites.values() if v is not None])
    edges = np.quantile(bvals, np.linspace(0, 1, n_buckets + 1))

    def bucket_of(b):
        if b is None:
            return 0
        return int(np.searchsorted(edges[1:-1], b, side='left'))

    random.seed(seed)
    buckets = defaultdict(list)
    for l in all_labels:
        buckets[bucket_of(brites.get(l.split(' ')[0]))].append(l)

    train_labels, val_labels = [], []
    for b, items in buckets.items():
        random.shuffle(items)
        k = int(round(len(items) * (1 - ratio)))
        val_labels += items[:k]
        train_labels += items[k:]

    print(f"Training data size: {len(train_labels)}")
    print(f"Validation data size: {len(val_labels)}")
    print(f"Stratified by brightness buckets: "
          f"{ {bk: len(v) for bk, v in buckets.items()} }")
    return train_labels, val_labels


def get_transforms(height, width):
    train_transform = A.Compose([
        A.Resize(height, width),
        # ----- photometric augmentation: fight light-sensitivity -----
        # Yellow lane line shifts hue/sat under different lighting
        # (yellow -> whiter in overexposure, -> orange/darker in dim light).
        # The OLD recipe only jittered brightness +-20% and value +-10 with
        # hue/sat = 0, so the model never saw color drift and keyed on yellow
        # -> breaks the moment real light changes. Now cover hue/sat too and
        # widen the range so 4 discrete capture levels interpolate smoothly.
        A.RandomBrightnessContrast(brightness_limit=0.4, contrast_limit=0.4, p=0.8),
        A.HueSaturationValue(hue_shift_limit=25, sat_shift_limit=35, val_shift_limit=25, p=0.6),
        # Motion / defocus simulation: lane lines blur while the car is moving,
        # so the model should not overfit to razor-sharp edges.
        A.OneOf([
            A.MotionBlur(blur_limit=5, p=1.0),
            A.GaussianBlur(blur_limit=(3, 5), p=1.0),
        ], p=0.3),
        # Transient occlusion / sensor dropouts on the lane.
        A.CoarseDropout(max_holes=6, max_height=20, max_width=20, p=0.2),
        # WARNING: do NOT add HorizontalFlip / Rotate / any spatial transform here.
        # The label is a steering scalar (0..180, 90=straight); a flip/rotation
        # would invert or shift that angle and silently corrupt supervision.
        # use mean and std from ImageNet
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2()
    ])

    val_transform = A.Compose([
        A.Resize(height, width),
        # use mean and std from ImageNet
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2()
    ])

    return train_transform, val_transform


def prepare_dataset(dataset_path, batch_size, height, width):
    image_dir = os.path.join(dataset_path, "images")
    train_labels, val_labels = split_data(dataset_path)

    train_transform, val_transform = get_transforms(height, width)
    train_dataset = LaneDataset(image_dir, train_labels, transform=train_transform)
    val_dataset = LaneDataset(image_dir, val_labels, transform=val_transform)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, pin_memory=False,
                              shuffle=True, num_workers=0, drop_last=False)

    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False,
                            num_workers=0, pin_memory=False)
    return train_loader, val_loader
