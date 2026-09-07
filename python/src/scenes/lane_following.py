#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time

import numpy as np

from src.actions import SetServo, Stop, Start, TurnLeft, TurnRight, Advance, TurnAround
from src.models import LFNet
from src.scenes.base_scene import BaseScene
from src.utils import log

# --- LF 控制参数(现场标定, 改这里即可) ---
# v5 2026-08-29: 运动偏差——车运动时 lfnet 比静止低约 2.75°(运动模糊/振动/俯仰), 运行时按电机状态(state[:4])在静止值/运动值间切换 CENTER
CENTER = 92.38       # auto-written by calibrate_center.py (2026-08-28 23:08, centered-still 18 frames, median=92.38)
CENTER_MOVING = CENTER  # 2026-08-28: 相机锁定(曝光5/WB3000K)后静止≈运动, 运行时运动居中 lfnet≈92 == 静止标定92.38, 运动偏差消失 -> 与CENTER相同; 旧的88.69是旧相机配置下的运动值, 会致 LF 恒判偏右
DEADZONE = 2.5       # |diff| 小于此值 -> 死区(窄道早修防压线; 噪声由 EMA 吸收)
MAX_DEGREE = 0.32    # 最大修正幅度(上限, 防窄道过冲)
K_DEGREE = 0.012     # 差速比例系数(P)
EMA_ALPHA = 0.25     # 时间平滑系数
# --- PI 抗稳态偏置(2026-08-27): 纯 P 控对恒定扰动有余差, 加积分项消去 ---
KI = 0.002           # 积分增益(每帧累加 diff -> 弧度修正); 提高以更快抵消起步右偏
I_CAP = 150.0        # 积分项上限(model-deg*frames); 配合 anti-windup 兜底, KI*I_CAP=0.30<MAX_DEGREE
I_INIT = 0.0        # 积分初值预载(v6 2026-08-29: 8→0)。运动偏差已由 v5 运动切换 CENTER 解决, +8 右偏置反致起步误右修->整体右偏(实测 demand=KI*I_INIT=0.016 叠加小 diff 顶出死区); 车体靠 HW_TRIM 平衡, 不需额外偏置
DEADZONE_RAD = DEADZONE * K_DEGREE   # 直行阈值(弧度), 与原死区语义一致


class LF(BaseScene):
    def __init__(self, memory_name, camera_info, msg_queue):
        super().__init__(memory_name, camera_info, msg_queue)
        self.net = None
        self.forward_spd = 22
        self.smooth_steering = None   # EMA 平滑状态(首帧初始化)
        self.err_int = I_INIT        # PI 积分累加器(model-deg*frames); 预置偏置方向同 I_INIT 符号(负=左/正=右)
        self._was_paused = False      # 上一帧是否处于暂停(Helper转向/看门狗), 用于恢复循迹时重置积分初值
        self._paused_turn = False     # 暂停期间是否发生过路标转向(恢复时积分置0; 纯暂停恢复则保留I_INIT) (v3 2026-08-29)

    def init_state(self):
        log.info(f'start init {self.__class__.__name__}')
        lfnet_path = os.path.join(os.getcwd(), 'weights', 'lfnet.om')
        if not os.path.exists(lfnet_path):
            log.error(f'Cannot find the offline inference model(.om) file needed for {self.__class__.__name__}  scene.')
            return True
        self.net = LFNet(lfnet_path)
        log.info(f'{self.__class__.__name__} model init succ.')
        self.ctrl.execute(SetServo(servo=[90, 90]))  # servo[1] is the camera LEFT/RIGHT servo (servo[0] is unwired); 90 = front-center
        return False

    def loop(self):
        ret = self.init_state()
        if ret:
            log.error(f'{self.__class__.__name__} init failed.')
            return
        frame = np.ndarray((self.height, self.width, 3), dtype=np.uint8, buffer=self.broadcaster.buf)
        log.info(f'{self.__class__.__name__} loop start')
        self.ctrl.execute(Start())
        try:
            while True:
                if self.stop_sign.value:
                    break
                if self.pause_sign.value:
                    continue
                # 暂停循迹(Helper 原地转向 或 看门狗/手动暂停) -> 恢复时重置积分, 避免车道丢失/姿态突变卷出的伪积分
                # v3 2026-08-29: 区分恢复场景 —— 路标转向后车头姿态已变, 预置右偏置(+I_INIT)方向未知且可能
                #   反向抵消左修(实测 2026-08-28 01:21 日志: 左转后车偏右需左修, err_int 却被重置 +8 右偏置,
                #   前几帧左修力度被削, i 需先从 +8 卷到负值, 偏右持续 30+ 帧); 纯暂停(超声波/红灯/看门狗)
                #   车头姿态未变, 保留起步右偏置语义
                _turn_busy = self.ctrl.is_turn_busy()
                if _turn_busy or self.pause_sign.value:
                    self._was_paused = True
                    self._paused_turn = self._paused_turn or _turn_busy
                    continue
                if self._was_paused:   # 刚从暂停恢复: 转弯后中性重启(0), 纯暂停保留偏置(I_INIT)
                    self.err_int = 0.0 if self._paused_turn else I_INIT
                    self._was_paused = False
                    self._paused_turn = False
                start = time.time()
                img_bgr = frame.copy()
                raw_steering = float(self.net.infer(img_bgr)[0])

                # --- 时间平滑(EMA 一阶低通): 抑制单帧模型噪声 ---
                if self.smooth_steering is None:
                    self.smooth_steering = raw_steering
                else:
                    self.smooth_steering = EMA_ALPHA * raw_steering + (1 - EMA_ALPHA) * self.smooth_steering
                curr_steering_val = self.smooth_steering
                # v5 运动偏差: 车运动时 lfnet 比静止低 2.75°, 按电机状态(state[:4])切换 CENTER, 避免静止标定值在运动中误判偏右
                _moving = any(m != 0 for m in self.ctrl.state[:4])
                _center = CENTER_MOVING if _moving else CENTER
                log.info(f'lfnet: {raw_steering:.2f} smooth: {curr_steering_val:.2f} i: {self.err_int:.1f} center: {_center:.2f}{"M" if _moving else "S"}')

                # --- PI 转向: 比例(P)+积分(I) 抗恒定偏置余差 ---
                # diff<0 需左, >0 需右(与标签约定 compute_steering_angle: 输出>90=车道在右需右转 一致, 此处不翻转)
                diff = curr_steering_val - _center
                # 抗积分饱和(anti-windup):
                #  1) 条件积分: 仅 |diff|>死区 才累加, 避免居中抖动/恒定小偏置在死区内慢慢卷积分
                #  2) 饱和回退: 本帧 demand 已夹到 ±MAX_DEGREE 且与误差同向 -> 撤销本次累加, 防止过冲后长时间单向往回修
                integrate = abs(diff) > DEADZONE
                if integrate:
                    self.err_int += diff
                demand_unsat = K_DEGREE * diff + KI * self.err_int
                # 注: 不再用恒定 FF_TRIM 常加项(会在右道段强制左漂); 右偏抵消改由 err_int 初值 I_INIT 提供, 积分自适应后续修正
                demand = max(-MAX_DEGREE, min(MAX_DEGREE, demand_unsat))
                if integrate and abs(demand_unsat) > MAX_DEGREE and np.sign(demand_unsat) == np.sign(diff):
                    self.err_int -= diff   # 饱和回退: 撤销本次积分
                if self.err_int > I_CAP:
                    self.err_int = I_CAP
                if self.err_int < -I_CAP:
                    self.err_int = -I_CAP
                if abs(demand) <= DEADZONE_RAD:
                    self.ctrl.execute(Advance(speed=self.forward_spd))
                else:
                    degree = abs(demand)
                    if degree < 0.05:
                        degree = 0.05
                    if demand < 0:
                        self.ctrl.execute(TurnLeft(degree=degree, speed=self.forward_spd))
                    else:
                        self.ctrl.execute(TurnRight(degree=degree, speed=self.forward_spd))

                log.info(f'infer cost {time.time() - start}')
        except KeyboardInterrupt:
            self.ctrl.execute(Stop())
