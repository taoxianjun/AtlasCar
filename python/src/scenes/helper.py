#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time

import numpy as np
from src.actions import SetServo, Stop, TurnLeftInPlace, TurnRightInPlace, TurnAround
from src.models import YoloV5
from src.scenes.base_scene import BaseScene
from src.utils import log

# 路标触发区域(归一化坐标 0~1, 相对相机分辨率 self.height/self.width)
# 旧版写死 300<x<1000 & y>=450, 仅对 1280x720 生效; 换成相对值后任意分辨率都生效。
# 调参: 漏触发(车到跟前都不转) -> 调小 FY_xx(更早触发);  误触发(远处就乱转) -> 调大 FY_xx 或收窄 FX_xx。
TRIGGER_FX_MIN, TRIGGER_FX_MAX, TRIGGER_FY_LR = 0.20, 0.80, 0.55     # left/right: x 居中带, y>0.55H
TRIGGER_FX_MIN_TA, TRIGGER_FX_MAX_TA, TRIGGER_FY_TA = 0.30, 0.70, 0.50  # turnaround: 更居中, y>0.50H


class Helper(BaseScene):
    def __init__(self, memory_name, camera_info, msg_queue):
        super().__init__(memory_name, camera_info, msg_queue)
        self.det = None
        self.cls = None

    def init_state(self):
        log.info(f'start init {self.__class__.__name__}')
        det_path = os.path.join(os.getcwd(), 'weights', 'yolo.om')
        if not os.path.exists(det_path):
            log.error(f'Cannot find the offline inference model(.om) file needed for {self.__class__.__name__}  scene.')
            return True
        self.det = YoloV5(det_path)
        log.info(f'{self.__class__.__name__} model init succ.')
        self.ctrl.execute(SetServo(servo=[90, 90]))  # servo[1] = camera LEFT/RIGHT (90 = front-center); servo[0] unwired
        return False

    def loop(self):
        ret = self.init_state()
        if ret:
            log.error(f'{self.__class__.__name__} init failed.')
            return
        frame = np.ndarray((self.height, self.width, 3), dtype=np.uint8, buffer=self.broadcaster.buf)
        log.info(f'{self.__class__.__name__} loop start')
        last_action = None
        COOLDOWN = 5.0             # 转向完成后的冷却秒数(防同一路标反复触发)
        last_turn_time = 0.0       # 上次实际执行转向的时刻
        try:
            while True:
                if self.stop_sign.value:
                    break
                if self.pause_sign.value:
                    continue
                start = time.time()

                # 冷却期内不检测,防止转向后路标还在视野里重复触发
                if time.time() - last_turn_time < COOLDOWN:
                    continue

                # 推理检测(异常保护: 任一帧推理抛错不要干掉整个 Helper 进程,
                # 否则表现为"Helper 像没执行、车一直往前冲")
                img_bgr = frame.copy()
                try:
                    bboxes = self.det.infer(img_bgr)
                except Exception as e:
                    log.error(f'infer exception: {e}')
                    bboxes = []
                log.info(f'{bboxes}')
                bboxes = sorted(bboxes, key=lambda x: x[5], reverse=True)
                for x1, y1, x2, y2, cate, score in bboxes:
                    x, y = (x1 + x2) // 2, (y1 + y2) // 2
                    # 归一化坐标(相对相机分辨率), 与 1280x720 硬编码解耦, 适配任意分辨率
                    fx, fy = x / self.width, y / self.height
                    log.info(f'det: {cate} score={float(score):.2f} '
                             f'box=({int(x1)},{int(y1)},{int(x2)},{int(y2)}) norm=({fx:.2f},{fy:.2f})')
                    if last_action != cate and len(bboxes) > 1:
                        cate = last_action

                    hit = False
                    # 触发区域: x 居中带(去掉两侧误检), y 在画面下半部分(路标在车前地面)
                    # 实测场地若"触发不及时/漏触发"调 FX_LR/FY_LR; "误触发"调小 FY 或收窄 FX
                    if cate == 'left' or cate == 'right':
                        if TRIGGER_FX_MIN < fx < TRIGGER_FX_MAX and fy > TRIGGER_FY_LR:
                            hit = True
                    elif cate == 'turnaround':
                        if TRIGGER_FX_MIN_TA < fx < TRIGGER_FX_MAX_TA and fy > TRIGGER_FY_TA:
                            hit = True

                    if hit:
                        # 两段式已并入动作序列(TurnLeftInPlace/TurnRightInPlace 以
                        # Advance+Sleep 直行前进段开头;TurnAround 自带 1.55s 前进段),
                        # 不再需要 DELAY/pending 机制。检测到即置忙(LF 停手)+执行转向。
                        # busy_sec 须 >= 前进段+转向段总时长(左/右转 2.8+0.65≈3.45;
                        # turnaround: 0.1+2.35+0.3+0.45+1.30+0.57≈5.07)。否则 LF 会在转向中途
                        # 抢回控制权。turnaround 第一段已加长至 2.35s,故 busy_sec 提到 6.0 留余量。
                        busy_sec = 4.3 if cate != 'turnaround' else 6.0
                        self.ctrl.turn_busy_until = time.time() + busy_sec
                        log.info(f'turn: {cate} (busy {busy_sec}s, forward phase inside action seq)')
                        if cate == 'left':
                            self.ctrl.execute(TurnLeftInPlace())
                        elif cate == 'right':
                            self.ctrl.execute(TurnRightInPlace())
                        elif cate == 'turnaround':
                            self.ctrl.execute(TurnAround())
                        last_turn_time = time.time()
                    last_action = cate
                    break
                log.info(f'infer cost {time.time() - start}')
        except KeyboardInterrupt:
            self.ctrl.execute(Stop())
