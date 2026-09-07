#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摄像头照片采集与数据集存储模块。

从 CameraBroadcaster 写入的共享内存中读取最新帧，按数据集目录结构
`dataset_root/<label>/NNNNN_<时间戳>.jpg` 存储。特点：
  - 每个 label 独立顺序编号（重启后扫描目录续号，不覆盖历史数据）
  - JPEG 质量可调，支持长边缩放
  - 返回结构化元信息，便于命令行日志 / 云端上报
  - 既可在 Manual 场景按键触发，也可在云端命令中调用

帧在共享内存中为 BGR 排列（cv2.VideoCapture 默认），cv2.imencode 直接可用。
"""

import os
import re
import time
from datetime import datetime
from multiprocessing import shared_memory

import cv2
import numpy as np

from src.utils.logger import logger_instance as log

# 单张照片的文件名形如 00012_20260810_180723_451.jpg
_FILENAME_RE = re.compile(r'^(\d{5})_')


class CameraCapture:
    def __init__(self, memory_name, camera_info, dataset_root='dataset',
                 default_label='unlabeled', jpeg_quality=95, max_side=0):
        """
        :param memory_name: CameraBroadcaster 创建的共享内存名
        :param camera_info: 与 main.py 中一致的相机参数（height/width）
        :param dataset_root: 数据集根目录
        :param default_label: 默认标签（即子目录名）
        :param jpeg_quality: JPEG 压缩质量 0~100
        :param max_side: 长边最大像素，0 表示不缩放
        """
        self.memory_name = memory_name
        self.height = int(camera_info.get('height', 720))
        self.width = int(camera_info.get('width', 1280))
        self.dataset_root = dataset_root
        self.default_label = default_label
        self.jpeg_quality = int(jpeg_quality)
        self.max_side = int(max_side)

        self._shm = None
        self._frame = None
        self._counters = {}  # label -> 下一个序号

    # ------------------------------------------------------------------ 共享内存
    def _ensure_shm(self):
        if self._shm is None:
            self._shm = shared_memory.SharedMemory(name=self.memory_name)
            self._frame = np.ndarray((self.height, self.width, 3),
                                     dtype=np.uint8, buffer=self._shm.buf)

    def read_frame(self):
        """读出当前帧的副本（BGR ndarray）。"""
        self._ensure_shm()
        return self._frame.copy()

    # ------------------------------------------------------------------ 编号管理
    def _next_index(self, label):
        folder = os.path.join(self.dataset_root, label)
        os.makedirs(folder, exist_ok=True)
        if label not in self._counters:
            # 扫描已有文件，取最大序号后继续，避免覆盖历史采集
            max_n = 0
            for fn in os.listdir(folder):
                m = _FILENAME_RE.match(fn)
                if m:
                    max_n = max(max_n, int(m.group(1)))
            self._counters[label] = max_n + 1
        idx = self._counters[label]
        self._counters[label] += 1
        return idx

    # ------------------------------------------------------------------ 采集主接口
    def capture(self, label=None, return_frame=False):
        """采集一张照片并落盘。

        :param label: 子目录标签，缺省用 default_label
        :param return_frame: 是否一并返回 ndarray（云端批量采集有用）
        :return: 字典，含 success/path/label/index/size/width/height 等
        """
        label = label or self.default_label
        try:
            frame = self.read_frame()
        except Exception as e:  # 共享内存尚未就绪等
            log.error(f'read frame failed: {e}')
            return {'success': False, 'error': str(e)}

        if self.max_side and max(frame.shape[:2]) > self.max_side:
            scale = self.max_side / max(frame.shape[:2])
            frame = cv2.resize(frame, None, fx=scale, fy=scale,
                               interpolation=cv2.INTER_AREA)

        idx = self._next_index(label)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        filename = f'{idx:05d}_{ts}.jpg'
        path = os.path.join(self.dataset_root, label, filename)

        ok, buf = cv2.imencode('.jpg', frame,
                               [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            log.error('cv2.imencode failed')
            return {'success': False, 'error': 'encode failed'}

        with open(path, 'wb') as f:
            f.write(buf.tobytes())

        size = os.path.getsize(path)
        log.info(f'captured -> {path} ({frame.shape[1]}x{frame.shape[0]}, {size}B)')
        result = {
            'success': True,
            'path': path,
            'filename': filename,
            'label': label,
            'index': idx,
            'width': int(frame.shape[1]),
            'height': int(frame.shape[0]),
            'size': size,
        }
        if return_frame:
            result['frame'] = frame
        return result

    def summary(self):
        """统计各标签已采集数量，用于状态上报。"""
        out = {}
        for label in os.listdir(self.dataset_root) if os.path.isdir(self.dataset_root) else []:
            folder = os.path.join(self.dataset_root, label)
            if os.path.isdir(folder):
                out[label] = len([f for f in os.listdir(folder)
                                  if f.lower().endswith('.jpg')])
        return out

    def close(self):
        if self._shm is not None:
            self._shm.close()
            self._shm = None
