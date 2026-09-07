#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# calibrate_center.py  (v1.1, 2026-08-26)  -- auto-write CENTER into lane_following.py
#
# 用途：标定 lane_following 的 CENTER 值。
#   把车在直道"居中且静止"放好 -> 跑本脚本 -> 它只做推理、不发任何驱动
#   指令（车原地不动），采集约 2 秒 lfnet raw 输出，打印中位数/均值/范围，
#   并【默认自动写回】 lane_following.py 的 CENTER（--no-write 可只看不写）。
#   居中时模型本应输出 CENTER 自身，故该中位数即应写进 lane_following.py:14 的 CENTER。
#
# 运行（务必在 python/ 目录下，确保能 import src 且 weights/lfnet.om 存在）：
#   cd /home/HwHiAiUser/E2ESamples/src/E2E-Sample/Car/python
#   python calibrate_center.py            # 默认采 2.0s，并自动把 CENTER 写进 lane_following.py
#   python calibrate_center.py --secs 3   # 采 3.0s
#   python calibrate_center.py --no-write # 只测不写，手动确认后再写
#
# 注意：本脚本不实例化 Controller，绝不触碰 ESP32 / 电机 / 舵机，安全只读。
# =============================================================================
import argparse
import os
import re
import time

import numpy as np
from multiprocessing import Process, shared_memory

from src.utils import CameraBroadcaster, CAMERA_INFO, log
from src.models import LFNet


def write_center(median, n_samples):
    """把标定的 median 自动写回 lane_following.py 的 CENTER 常量（整行重写，保留备份）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, 'src', 'scenes', 'lane_following.py')
    if not os.path.exists(target):
        log.warning(f'Cannot find {target}, skip auto-write. Edit CENTER manually.')
        return False
    with open(target, 'r', encoding='utf-8') as f:
        content = f.read()
    # 1) 备份当前文件（任何写操作前的兜底，可直接还原）
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = f'{target}.bak_center_{ts}'
    with open(bak, 'w', encoding='utf-8') as f:
        f.write(content)
    # 2) 整行重写 CENTER 定义（正则匹配模块级 CENTER 行，保留文件其余内容）
    new_line = (f"CENTER = {median:.2f}       "
                f"# auto-written by calibrate_center.py "
                f"({time.strftime('%Y-%m-%d %H:%M')}, centered-still {n_samples} frames, median={median:.2f})")
    new_content, n = re.subn(r'^CENTER\s*=.*$', new_line, content, count=1, flags=re.M)
    if n == 0:
        log.warning('CENTER definition not found in target, skip auto-write. Edit manually.')
        return False
    with open(target, 'w', encoding='utf-8') as f:
        f.write(new_content)
    log.info(f'>> Wrote CENTER = {median:.2f} into {target}')
    log.info(f'>> Backup: {bak}')
    print(f'\n>>> 已自动把 CENTER = {median:.2f} 写进 {target}')
    print(f'>>> 旧值已备份到 {bak}（如需回退直接还原该备份）\n')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--secs', type=float, default=2.0, help='采集时长(秒)')
    parser.add_argument('--no-write', action='store_true',
                        help='只测出推荐 CENTER 并打印，不自动写回 lane_following.py')
    args = parser.parse_args()

    om_path = os.path.join(os.getcwd(), 'weights', 'lfnet.om')
    if not os.path.exists(om_path):
        log.error(f'Cannot find {om_path}, aborted.')
        return

    # 1) 起相机广播进程（与 main.py 完全一致），写入共享内存
    camera = CameraBroadcaster(CAMERA_INFO)
    cam_proc = Process(target=camera.run)
    cam_proc.start()

    shm = None
    try:
        shm = shared_memory.SharedMemory(name=camera.memory_name)
        # 共享内存里的帧，shape 与相机一致 (H,W,3) uint8
        frame = np.ndarray(
            (CAMERA_INFO['height'], CAMERA_INFO['width'], 3),
            dtype=np.uint8, buffer=shm.buf)

        # 2) 加载 lfnet 模型（ACL 初始化 + 加载 om）
        log.info('Loading lfnet.om ...')
        net = LFNet(om_path)

        # 3) 相机预热：丢弃前 0.5s（首帧可能为黑帧/未稳定）
        log.info('Camera warm-up 0.5s ...')
        time.sleep(0.5)

        # 4) 采集 raw 值（只推理，不发车）
        log.info(f'Collecting lfnet raw for {args.secs:.1f}s (car must be centered & stationary)...')
        vals = []
        t0 = time.time()
        while time.time() - t0 < args.secs:
            raw = net.infer(frame.copy())[0]
            raw = float(np.asarray(raw).reshape(-1)[0])
            vals.append(raw)
            time.sleep(0.02)  # 轻微节流，避免无意义的满负载

        if not vals:
            log.error('No inference result collected, aborted.')
            return

        # 5) 统计
        arr = np.array(vals, dtype=np.float32)
        median = float(np.median(arr))
        mean = float(arr.mean())
        mn, mx = float(arr.min()), float(arr.max())

        log.info('=' * 60)
        log.info(f'  samples : {len(vals)}')
        log.info(f'  median  : {median:.2f}   <-- 推荐写进 lane_following.py:14 CENTER')
        log.info(f'  mean    : {mean:.2f}')
        log.info(f'  min/max : {mn:.2f} / {mx:.2f}')
        log.info('=' * 60)
        print(f'\n>>> 推荐 CENTER = {median:.2f}  (median of {len(vals)} samples)')

        if args.no_write:
            log.info('(--no-write) 已跳过自动写回，请手动把 CENTER 改成上面的值。')
            print('>>> --no-write：未写入文件，请手动改 lane_following.py:14 的 CENTER。\n')
        else:
            write_center(median, len(vals))

    except Exception as e:
        log.error(f'calibrate_center failed: {e}')
    finally:
        # 6) 清理：停相机进程并释放共享内存
        try:
            camera.stop_sign.value = True
            cam_proc.join(timeout=5)
            if cam_proc.is_alive():
                cam_proc.kill()
        except Exception:
            pass
        if shm is not None:
            try:
                shm.close()
            except Exception:
                pass
        log.info('calibrate_center done.')


if __name__ == '__main__':
    main()
