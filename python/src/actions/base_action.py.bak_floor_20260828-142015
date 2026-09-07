#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
from abc import ABC, abstractmethod

# ---------------------------------------------------------------------------
# HW_TRIM: per-motor hardware compensation.
#   state order: [m0, m1, m2, m3, ...]  where m0,m1 = LEFT wheels, m2,m3 = RIGHT wheels.
#   The LEFT wheels (m0,m1) are physically weaker, so their commands are boosted by
#   HW_TRIM[i] so that, after the hardware's real gain, all four wheels deliver the
#   same actual speed -> the car goes straight without manual correction.
#   This is the SINGLE software "hardware calibration knob": tune it here if the
#   mechanical imbalance changes. It is applied per-motor in fix_speed(), so it is
#   fully transparent to every action (Advance / Turn / Shift / Spin ...) and does
#   NOT disturb the steering differential.
# ---------------------------------------------------------------------------
# NOTE: for real straight driving restore HW_TRIM=[1.55, 1.55, 1.0, 1.0].
#       With the MIN_START floor below, even HW_TRIM=[1,1,1,1] + speed=20 now moves
#       (the weakest wheel is boosted past the ~30 motor dead-zone).
HW_TRIM = [1.0, 1.0, 1.0, 1.0]

# ---------------------------------------------------------------------------
# Motor minimum drive threshold ("dead-zone"): a commanded value < ~30 (motor
# command units) does NOT turn the wheel (PWM duty too low to overcome static
# friction). This is a HARDWARE property, not a logic bug.
#   MIN_START  : floor applied to the weakest MOVING wheel so it reaches >=32
#                (with margin above the ~30 dead-zone) -> speed=22/20 etc. all turn.
#   MIN_COMMAND: a command whose raw speed < MIN_COMMAND is treated as "creep/stop",
#                so we do NOT force-feed it (keep Stop / very-slow intent intact).
#                Effective "minimum movable speed" = 20.
# The floor scales ALL moving wheels by the SAME factor, so the steering
# differential ratio is preserved (only the absolute level is lifted).
# ---------------------------------------------------------------------------
MIN_START = 32
MIN_COMMAND = 20


class BaseAction(ABC):
    """
    基础动作的基类，所有基本动作均继承于该类
    """

    def __init__(self, *args, **kwds) -> None:
        """
        基础动作类的初始化方法，通过args与kwds控制输入参数
        :param args:
        :param kwds:
        """
        # 抽象的速度信息
        self.speed = kwds.get('speed', -1)
        # 电机角度
        self.servo_angle = kwds.get('servo', [-1, -1])

        # 根据电机的实际情况修改下发到电机的速度（软件补偿左轮偏弱，见 HW_TRIM）
        self.motor_rating = list(HW_TRIM)

        # 确定是否需要在运行时根据前动作更新电机角度及电机速度
        self.update_speed = False
        self.update_servo = False

        if self.speed == -1:
            self.update_speed = True

        if self.servo_angle[0] == -1 and self.servo_angle[1] == -1:
            self.update_servo = True

        # 由速度生成方法将抽象的总体速度计算为4个电机的速度并输出为list
        self.speed_setting = self.generate_speed_setting(self.speed)
        self.fix_speed()

    def fix_speed(self):
        # 1) per-motor hardware compensation (HW_TRIM): balance left/right weakness
        v = [int(speed * ratio) for speed, ratio in zip(self.speed_setting, self.motor_rating)]
        # 2) minimum-drive floor: lift the weakest MOVING wheel to >= MIN_START so the
        #    wheel actually turns even at low commanded speed (overcomes ~30 dead-zone).
        moving = [abs(x) for x in v if x != 0]
        if moving and min(moving) < MIN_START:
            # only boost real "go" commands; a raw speed < MIN_COMMAND is creep/stop.
            if any(abs(b) >= MIN_COMMAND for b in self.speed_setting):
                k = (MIN_START + 0.999) / min(moving)  # +0.999 avoids int() truncation back under threshold
                v = [int(x * k) for x in v]
        self.speed_setting = v

    @staticmethod
    @abstractmethod
    def generate_speed_setting(speed, degree=0):
        """
        生成4个电机的速度，并输出为列表
        抽象类，需要根据具体情况进行设置
        :param speed: 抽象的速度。 当前动作初始化时设置 或 控制器根据前一动作速度进行设置
        :param degree: 如需转弯，速度计算需要的角度信息
        :return:
        """
        pass

    def __call__(self, speed, servo_angle):
        """
        call魔法函数，两个输入参数由控制器输入
        当init方法设置了相关信息，则忽略控制器输入的参数
        当init方法没有设置相关信息，相关信息的将由控制器输入的参数进行更新

        :param speed: 抽象速度
        :param servo_angle: 舵机的角度
        :return: 长度为6的列表，前4位为4个电机的速度，后2位为舵机的两个角度
        """
        if self.update_servo:
            self.servo_angle = servo_angle
        if self.update_speed:
            degree = 0
            if hasattr(self, 'degree'):
                degree = self.degree
            self.speed_setting = self.generate_speed_setting(speed, degree)
            self.fix_speed()

        return self.speed_setting + self.servo_angle


class Advance(BaseAction):
    """
    小车前进
    """

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [-speed, -speed, speed, speed]


class BackUp(BaseAction):
    """
    小车后退
    """

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [speed, speed, -speed, -speed]


class CustomAction(BaseAction):
    """
    自定义动作
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.speed_setting = kwds.get('motor_setting', [0, 0, 0, 0])
        self.update_controller_speed = False
        self.update_speed = False

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [0, 0, 0, 0]


class Stop(BaseAction):
    """
    小车停止
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.speed = 0

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [0, 0, 0, 0]


class TurnLeft(BaseAction):
    """
    小车左转（yaw left）：右轮加速 + 左轮减速的对称差速。
    对称差速比原单边加速转向权限翻倍，且转向中前进速度恒定不突窜。
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.degree = kwds.get('degree', 0)
        self.speed_setting = self.generate_speed_setting(speed=self.speed, degree=self.degree)
        self.fix_speed()

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        d = min(max(degree, 0.0), 0.7)  # clamp，防止一侧电机反转
        return [-int(speed * (1 - d)), -int(speed * (1 - d)),
                int(speed * (1 + d)), int(speed * (1 + d))]


class TurnRight(BaseAction):
    """
    小车右转（yaw right）：左轮加速 + 右轮减速的对称差速。
    对称差速比原单边加速转向权限翻倍，且转向中前进速度恒定不突窜。
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.degree = kwds.get('degree', 0)
        self.speed_setting = self.generate_speed_setting(speed=self.speed, degree=self.degree)
        self.fix_speed()

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        d = min(max(degree, 0.0), 0.7)  # clamp，防止一侧电机反转
        return [-int(speed * (1 + d)), -int(speed * (1 + d)),
                int(speed * (1 - d)), int(speed * (1 - d))]


class ShiftLeft(BaseAction):
    """
    向左平移（使用统一 HW_TRIM，不再私自覆盖补偿，避免横移漂移）
    """

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [speed, -speed, -speed, speed]


class ShiftRight(BaseAction):
    """
    向右平移
    """

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [-speed, speed, speed, -speed]


class LeftOblique(BaseAction):
    """
    斜向左前方
    """

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [0, -speed, 0, speed]


class RightOblique(BaseAction):
    """
    斜向右前方
    """

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [-speed, 0, speed, 0]


class SpinClockwise(BaseAction):
    """
    顺时针旋转
    """

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [-speed] * 4


class SpinAntiClockwise(BaseAction):
    """
    逆时针旋转
    """

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [speed] * 4


class SetServo(BaseAction):
    """
    舵机转动
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.speed = 0
        # 舵机动作只动舵机,不应清零共享的 controller.speed
        # (否则 easy 模式双进程下会把 LF 的前进速度清成 0,车直接停)
        self.update_controller_speed = False

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return [0, 0, 0, 0]


class Sleep(BaseAction):
    """
    Sleep(1)等同于time.sleep(1)
    可加入至动作序列进行使用
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.sleep_time = args[0]

    @staticmethod
    def generate_speed_setting(speed, degree=0):
        return []

    def __call__(self, speed, servo_angle):
        time.sleep(self.sleep_time)
        return None
