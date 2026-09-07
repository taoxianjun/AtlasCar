#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from abc import ABC

from src.actions.base_action import Advance, Sleep, SpinAntiClockwise, Stop, SpinClockwise, CustomAction, ShiftLeft, \
    TurnRight


class ComplexAction(ABC):
    def __init__(self, ):
        # 当前动作是否强制执行，默认为强制执行
        self.force = True
        # 当前动作序列是否更新控制器记录的速度，默认为不更新
        self.update_controller_speed = False
        pass


class TurnLeftInPlace(ComplexAction):
    def __init__(self):
        super().__init__()
        self.action_seq = [
            # 前进段(Phase-1):直行 2.8s 走向路标,脱离循迹(原 helper 的 DELAY 机制
            # 已删除,前进时长并入动作序列;现场按路标距离调 Sleep)
            Advance(speed=30),
            Sleep(2.8),
            SpinAntiClockwise(speed=50),   # 52→50: 2026-08-28 后续实测左转角度略超, 回退2档(时长0.65s保持)
            Sleep(0.65),                    # 0.7→0.65:实测转过了,微调回来
            Stop()
        ]


class TurnRightInPlace(ComplexAction):
    def __init__(self):
        super().__init__()
        self.action_seq = [
            # 前进段(Phase-1):直行 2.8s 走向路标,脱离循迹(同 TurnLeftInPlace)
            Advance(speed=30),
            Sleep(2.8),
            SpinClockwise(speed=50),       # 52→50: 与左转对称(2026-08-28 后续)
            Sleep(0.65),                    # 0.7→0.65:实测转过了,微调回来
            Stop()
        ]


class TurnAround(ComplexAction):
    def __init__(self):
        super().__init__()
        self.action_seq = [
            Stop(),
            Sleep(0.1),
            Advance(speed=30),
            Sleep(2.35),                    # 1.55→2.35:用户反馈掉头第一段直行太短,加长0.8s
            Stop(),
            Sleep(0.3),
            SpinAntiClockwise(speed=50),
            Sleep(0.45),        # 第一次:实测刚好,保持
            Advance(speed=30),
            Sleep(1.30),        # 1.35→1.30:距离再回调0.05s实测
            SpinAntiClockwise(speed=50),
            Sleep(0.57),        # 0.56→0.57:角度再加0.01s实测
            Stop(),
        ]


class Start(ComplexAction):
    def __init__(self):
        super().__init__()
        self.update_controller_speed = True
        self.action_seq = [
            Advance(speed=35),
            Sleep(0.2),
            Advance(speed=25)
        ]


class Parking(ComplexAction):
    def __init__(self):
        super().__init__()
        self.action_seq = [
            Stop(),
            Sleep(1),

            CustomAction(motor_setting=[-85, 65, 60, -55]),
            Sleep(0.75),
            Stop(),

            Sleep(2),
            CustomAction(motor_setting=[65, -58, -55, 55]),
            Sleep(1),
            Stop()
        ]
