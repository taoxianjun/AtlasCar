#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# calibrate_camera.py  (v2.0, 2026-08-29)
#   -- auto-lock camera exposure & white balance, then write them back into
#      src/utils/camera_broadcaster.py (same auto-write pattern as calibrate_center.py)
#
# 用途：把车放到"典型光照、对准赛道"的位置 -> 跑本脚本 -> 它只开相机、不发车、
#   扫描一组候选 EXPOSURE，挑出画面平均亮度最接近目标值(默认 125/255)的那档，
#   再扫描候选白平衡色温(该 UVC 摄像头无 red/blue gain 控件)，挑 gray-world 误差
#   最小(画面最中性)的色温，最终【默认自动写回】
#   camera_broadcaster.py 的 CAMERA_EXPOSURE / CAMERA_WB_TEMPERATURE。
#   之后 main.py 启动相机即自动套用锁定参数（光敏感源头被锁死）。
#
# 运行（务必在 python/ 目录下）：
#   cd /home/HwHiAiUser/E2ESamples/src/E2E-Sample/Car/python
#   python calibrate_camera.py            # 默认扫描 + 自动写回
#   python calibrate_camera.py --no-write # 只测不写，确认后再写
#   python calibrate_camera.py --target 120   # 目标平均亮度(0..255)
#   python calibrate_camera.py --secs 4       # 每档停留/采样时长(秒)
#   python calibrate_camera.py --range 1,200,4000   # 自定义候选曝光范围(起,步,止)
#
# 注意：本脚本只开相机读帧，不实例化 Controller / 不碰 ESP32 / 电机 / 舵机，安全只读。
# =============================================================================
import argparse
import os
import re
import subprocess
import time

import cv2
import numpy as np

from src.utils import CAMERA_INFO, log, detect_ae_off


# 候选曝光扫描点（V4L2 曝光单位因驱动而异，覆盖常见区间即可；挑最接近目标亮度的档）
DEFAULT_CANDIDATES = [1, 2, 5, 10, 20, 40, 80, 150, 300, 600, 1200, 2400, 4000, 8000]
TARGET_BRIGHTNESS = 125      # 0..255，居中不过曝不欠曝
# 候选白平衡色温(开尔文)。该 UVC 摄像头无 red/blue gain 控件, 只能锁色温;
# 扫描挑 gray-world 误差最小(画面最中性)的色温。
WB_TEMP_CANDIDATES = [3000, 3500, 4000, 4500, 4600, 5000, 5500, 6000, 6500]
WB_DEVICE = '/dev/video0'


def sample_brightness(cap, n=10, sleep_s=0.3):
    """在固定曝光下采样 n 帧，返回 (灰度均值, 各通道均值 BGR)。"""
    grays, means_bgr = [], []
    for _ in range(n):
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        grays.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
        means_bgr.append(frame.reshape(-1, 3).mean(axis=0))  # BGR
        time.sleep(sleep_s)
    if not grays:
        return None, None
    return float(np.mean(grays)), np.mean(means_bgr, axis=0)  # BGR mean


def scan_exposure(cap, candidates, target, secs, ae_off):
    """遍历候选曝光，返回 (best_exp, [(exp, brightness), ...])。"""
    # 关自动白平衡(该 UVC 摄像头用 white_balance_temperature_auto 控件, 非 OpenCV AUTO_WB;
    # 旧 CAP_PROP_AUTO_WB=0 是静默 no-op) -> 让曝光扫描在稳定色温下进行
    subprocess.run(['v4l2-ctl', '-d', WB_DEVICE, '--set-ctrl', 'white_balance_temperature_auto=0'],
                   capture_output=True, timeout=15)
    results = []
    for exp in candidates:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, ae_off)   # 用探测到的手动曝光常量
        cap.set(cv2.CAP_PROP_EXPOSURE, exp)
        time.sleep(0.5)                             # 等曝光稳定
        bright, _ = sample_brightness(cap, n=8, sleep_s=max(0.1, secs / 8))
        if bright is None:
            continue
        results.append((exp, bright))
        log.info(f'  EXPOSURE={exp:6d}  mean_brightness={bright:6.1f}')
    if not results:
        return None, results
    # 挑亮度最接近 target 的档（亮度越高越接近也不溢出优先）
    best = min(results, key=lambda r: abs(r[1] - target))
    return best[0], results


def scan_wb_temperature(cap, exp, secs, ae_off, device=WB_DEVICE):
    """在选定曝光下扫描候选白平衡色温，挑 gray-world 误差最小(画面最中性)的色温。

    该 UVC 摄像头只有 white_balance_temperature 控件（无 red/blue gain），通过
    v4l2-ctl 逐个设色温 + 采样画面，用 R/B 通道偏离 G 的程度度量色偏，选最接近
    中性灰的色温作为锁定值。
    """
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, ae_off)   # 确保仍处手动曝光
    cap.set(cv2.CAP_PROP_EXPOSURE, exp)
    time.sleep(0.5)
    # 关自动白平衡，进入手动色温模式（v4l2-ctl 设的是设备级 control，作用于已打开的 cap）
    subprocess.run(['v4l2-ctl', '-d', device, '--set-ctrl', 'white_balance_temperature_auto=0'],
                   capture_output=True, timeout=15)

    results = []
    for temp in WB_TEMP_CANDIDATES:
        subprocess.run(['v4l2-ctl', '-d', device, '--set-ctrl',
                        'white_balance_temperature=%d' % temp],
                       capture_output=True, timeout=15)
        time.sleep(0.5)
        _, mean_bgr = sample_brightness(cap, n=8, sleep_s=max(0.1, secs / 8))
        if mean_bgr is None or mean_bgr[1] <= 1e-6:
            continue
        mb, mg, mr = mean_bgr  # BGR
        err = abs(mr - mg) + abs(mb - mg)   # R/B 偏离 G 的总和 -> 越小越中性
        results.append((temp, err))
        log.info(f'  WB_TEMP={temp:5d}K  gray_world_err={err:7.1f}  BGR=({mb:.0f},{mg:.0f},{mr:.0f})')

    if not results:
        log.warning('No valid frames during WB temperature scan; fallback to 4600K.')
        return 4600
    best = min(results, key=lambda r: r[1])
    return best[0]


def write_params(exp, wb_temperature):
    """把标定结果自动写回 camera_broadcaster.py 的两个常量（整行重写 + 备份）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, 'src', 'utils', 'camera_broadcaster.py')
    if not os.path.exists(target):
        log.warning(f'Cannot find {target}, skip auto-write. Edit camera params manually.')
        return False
    with open(target, 'r', encoding='utf-8') as f:
        content = f.read()
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = f'{target}.bak_cam_{ts}'
    with open(bak, 'w', encoding='utf-8') as f:
        f.write(content)

    mapping = {
        'CAMERA_EXPOSURE': f'CAMERA_EXPOSURE = {int(exp)}       # auto-written by calibrate_camera.py ({time.strftime("%Y-%m-%d %H:%M")}, exp={int(exp)})',
        'CAMERA_WB_TEMPERATURE': f'CAMERA_WB_TEMPERATURE = {int(wb_temperature)}   # auto-written by calibrate_camera.py ({time.strftime("%Y-%m-%d %H:%M")}, gray-world best color temperature (K))',
    }
    new_content = content
    for name, new_line in mapping.items():
        new_content, n = re.subn(rf'^{name}\s*=.*$', new_line, new_content, count=1, flags=re.M)
        if n == 0:
            log.warning(f'{name} not found in {target}, skip auto-write for it.')
            return False
    with open(target, 'w', encoding='utf-8') as f:
        f.write(new_content)
    log.info(f'>> Wrote CAMERA_EXPOSURE={int(exp)}, CAMERA_WB_TEMPERATURE={int(wb_temperature)} into {target}')
    log.info(f'>> Backup: {bak}')
    print(f'\n>>> 已自动把相机锁定参数写进 {target}')
    print(f'>>>   CAMERA_EXPOSURE       = {int(exp)}')
    print(f'>>>   CAMERA_WB_TEMPERATURE = {int(wb_temperature)}K')
    print(f'>>> 旧值已备份到 {bak}（如需回退直接还原该备份）\n')
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=float, default=TARGET_BRIGHTNESS,
                        help='目标平均亮度 0..255 (默认 125)')
    parser.add_argument('--secs', type=float, default=4.0,
                        help='整体采样时长(秒)，用于分摊到每档采样')
    parser.add_argument('--range', type=str, default=None,
                        help='自定义候选曝光范围 "起,步,止"，如 "1,200,4000"')
    parser.add_argument('--no-write', action='store_true',
                        help='只测出推荐参数并打印，不自动写回 camera_broadcaster.py')
    args = parser.parse_args()

    if args.range:
        try:
            start, step, stop = (int(x) for x in args.range.split(','))
            candidates = list(range(start, stop + 1, step))
        except Exception:
            log.warning('Bad --range format, use default candidates.')
            candidates = list(DEFAULT_CANDIDATES)
    else:
        candidates = list(DEFAULT_CANDIDATES)

    per_candidate = max(0.4, args.secs / max(1, len(candidates)))

    cap = cv2.VideoCapture()
    cap.open(0, apiPreference=cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_INFO.get('width', 1280))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_INFO.get('height', 720))
    time.sleep(0.5)  # 相机预热

    # 自动探测本机驱动下能真正关闭自动曝光的 AUTO_EXPOSURE 常量（V4L2 取值因驱动而异）
    AE_OFF = detect_ae_off(cap, test_exposure=200)
    if AE_OFF is None:
        log.warning('Could not disable auto-exposure on this driver; falling back to 0.25 (may not lock).')
        AE_OFF = 0.25
    else:
        log.info(f'Detected working AUTO_EXPOSURE constant = {AE_OFF} (manual mode confirmed).')

    try:
        log.info('=' * 60)
        log.info(f'Scanning {len(candidates)} candidate EXPOSURE values (target brightness={args.target:.0f})...')
        best_exp, results = scan_exposure(cap, candidates, args.target, per_candidate, AE_OFF)
        if best_exp is None:
            log.error('No valid frames captured during scan, aborted.')
            return
        log.info('=' * 60)
        log.info(f'Best EXPOSURE = {best_exp}  (brightness closest to {args.target:.0f})')

        # FIX 2026-08-27: clamp best_exp to the driver's exposure_absolute max.
        # The candidate scan can pick a value (e.g. 8000) above the HW ceiling
        # (e.g. 5000); writing that out makes the runtime lock probe overflow and
        # silently fail ("Could NOT disable auto-exposure"). Read back the actual
        # value the driver accepted and use it instead.
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, AE_OFF)
        cap.set(cv2.CAP_PROP_EXPOSURE, best_exp)
        actual = cap.get(cv2.CAP_PROP_EXPOSURE)
        if actual is not None and abs(actual - best_exp) > 1:
            log.warning(f'best_exp={best_exp} clamped by driver to {int(actual)} (exposure_absolute range).')
            best_exp = int(actual)

        log.info('Scanning white balance color temperature...')
        wb_temperature = scan_wb_temperature(cap, best_exp, args.secs, AE_OFF)
        log.info(f'  CAMERA_WB_TEMPERATURE={wb_temperature}K')

        print(f'\n>>> 推荐相机锁定参数：')
        print(f'>>>   CAMERA_EXPOSURE       = {int(best_exp)}')
        print(f'>>>   CAMERA_WB_TEMPERATURE = {wb_temperature}K')

        if args.no_write:
            log.info('(--no-write) 已跳过自动写回，请手动改 camera_broadcaster.py 顶部的两个常量。')
            print('>>> --no-write：未写入文件。\n')
        else:
            write_params(best_exp, wb_temperature)
    except Exception as e:
        log.error(f'calibrate_camera failed: {e}')
    finally:
        try:
            cap.release()
        except Exception:
            pass
        log.info('calibrate_camera done.')


if __name__ == '__main__':
    main()
