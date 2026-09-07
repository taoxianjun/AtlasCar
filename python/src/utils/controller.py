#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import atexit
import os
import pickle
import shutil
import time

import serial
from filelock import FileLock

from src.actions.base_action import BaseAction
from src.utils.common_utils import SingleTonType
from src.utils.logger import logger_instance as log
from src.utils.constant import ESP32_NAME
from src.utils.init_utils import get_port


class Controller(metaclass=SingleTonType):
    """
    由单例和文件锁保证的全局唯一的控制器
    支持执行动作序列及单个动作

    """

    # 保证所有进程内的控制器内的参数保持一致
    def _set_gloabl_unique(self):
        with self._lock:
            if not os.path.exists(self._ser_path):
                self.reset()
                self._save()
            else:
                try:
                    self._update()
                except EOFError:
                    self.reset()
                    self._save()
            self._inc_count()

    def __init__(self) -> None:
        # 获取当前用户的home目录
        home = os.path.expanduser('~')

        # 新建临时文件夹
        self._temp_path = os.path.join(home, 'temp', 'controller')
        if not os.path.exists(self._temp_path):
            os.makedirs(self._temp_path, exist_ok=True)
        # 设置序列化文件保存路径，文件锁路径，全局引用计数路径
        self._ser_path = os.path.join(self._temp_path, 'controller.pickle')
        self._lock_path = os.path.join(self._temp_path, 'controller.lock')
        self._count_path = os.path.join(self._temp_path, 'controller.count')

        # 创建文件锁
        self._lock = FileLock(self._lock_path)

        # esp32串口信息
        esp32_port = get_port(ESP32_NAME)
        self._ser = serial.Serial(esp32_port, 115200)
        self._check_val = -12345

        # 需要由串口保存的信息
        # 分别为最后一次成功下发指令的时间，电机+舵机的状态，当前速度，当前舵机角度
        self.last_modify_time = 0
        self.state = [0, 0, 0, 0, 0, 0, self._check_val]
        self.speed = 0
        self.servo_angle = [0, 0]
        # 原地转向互斥锁:Helper 转向期间置为结束时间戳,LF 检测到忙就暂停发动作
        # (easy 模式双进程共用 Controller,不互斥会互相覆盖电机指令)
        self.turn_busy_until = 0.0

        # 初始化跨进程共享状态文件 + 引用计数 + 退出清理。
        # 注意: 这段代码原来被错误地放在 is_turn_busy() 的 return 之后, 成了死代码,
        # 导致 controller.pickle 从不在 __init__ 时创建、atexit 也不注册,
        # 跨进程的 turn_busy_until 管道因此彻底断开(Helper 设的忙标志 LF 永远读不到)。
        with self._lock:
            if not os.path.exists(self._ser_path):
                self._save()          # 仅写入默认公共变量, 不在此 reset() 以免启动时误发停车
            self._inc_count()
        atexit.register(self._deinit)

    # 查询"是否有场景正在原地转向"(读共享状态,供 LF 每帧检查)
    def is_turn_busy(self):
        with self._lock:
            try:
                self._update()
            except Exception:
                pass
            return time.time() < self.turn_busy_until

    # 重置电机与舵机状态
    def reset(self):
        self.speed = 0
        self.servo_angle = [90, 90]  # servo[1] is camera LEFT/RIGHT servo (90=front-center); servo[0] unwired
        state = [self.speed] * 4 + self.servo_angle + [self._check_val]
        self.send_to_device(state)

    # 执行动作序列
    def execute(self, action):
        # 获取文件锁
        with self._lock:
            # 保护 turn_busy_until: 调用方(Helper)在 execute 前已置好"转向忙"截止时间,
            # 此处 _update() 会把共享文件里的旧值读回并覆盖, 导致 LF 永远读不到 busy 而一直发循迹指令,
            # 把 Helper 的转向盖掉。先缓存调用方设置的值, _update() 后再取较大者保留。
            _busy_until = self.turn_busy_until
            # 从序列化文件更新当前控制器的相关参数(文件缺失/损坏时跳过, 不崩进程)
            try:
                self._update()
            except Exception:
                pass
            if _busy_until > self.turn_busy_until:
                self.turn_busy_until = _busy_until

            # 获取输入action的相关attr
            attr_dict = action.__dict__
            force = attr_dict.get('force', None)
            send_time = attr_dict.get('send_time', None)
            action_seq = attr_dict.get('action_seq', None)
            update_controller_speed = attr_dict.get('update_controller_speed', True)
            log.info(f'update_controller_speed: {update_controller_speed}')
            log.info(f'self.speed: {self.speed}')

            # 判断是否丢弃过时的动作
            # 如果动作序列带有force（强制执行）属性将无视动作下发时间
            # 如果动作序列带有下发时间，且动作序列下发时间早于最后一次动作的执行时间，当前动作序列将被丢弃
            if force is None or not force:
                if send_time is not None and isinstance(send_time, float) and self.last_modify_time > send_time:
                    return -1

            # 判断输入动作是否为动作序列或单个简单动作
            if action_seq is None and isinstance(action, BaseAction):
                action_seq = [action]

            # 执行动作序列
            for action in action_seq:
                # 调用动作的__call__方法
                state = action(self.speed, self.servo_angle)
                # 如果当前动作不需要下发指令至ESP32，跳过后续步骤
                if state is None:
                    continue
                state += [self._check_val]
                # 下发指令并获取到修改的时间戳
                ret, modify_time = self.send_to_device(state)
                log.info(f'action {action.__class__.__name__} execute {ret}')

                # 更新控制器相关信息
                self.state = state
                self.last_modify_time = modify_time
                if update_controller_speed and action.speed != -1:
                    self.speed = action.speed
                if action.servo_angle != [-1, -1]:
                    self.servo_angle = action.servo_angle

            # 保存控制器的相关信息
            self._save()
            return 0

    def send_to_device(self, state):
        start = time.time()
        # 将电机与舵机状态进行编码并进行组合
        msg = b''.join([num.to_bytes(2, byteorder='little', signed=True) for num in state])
        # 下发编码好的14bytes信息至esp32
        try:
            self._ser.write(msg)
        except Exception:
            esp32_port = None
            while esp32_port is None:
                esp32_port = get_port(ESP32_NAME)
            self._ser = serial.Serial(esp32_port, 115200)
            self._ser.write(msg)
        log.info(f'{state}')
        # 读取esp32返回的succ指令
        ret = self.recv_from_device().strip().decode()
        log.debug(f'{ret}')
        if ret == 'FAIL':
            log.warn(f'Ultrasonic obstacle avoidance is activated. Please move the car to a safe position.')
        end = time.time()
        log.debug(f'action execute cost: {end - start}s')
        return ret, time.time()

    def recv_from_device(self):
        return self._ser.readline()

    # 从序列化文件中获取参数并更新当前控制器的相关参数
    def _update(self):
        with open(self._ser_path, 'rb') as f:
            attr_dict = pickle.load(f)
            for k, v in attr_dict.items():
                setattr(self, k, v)

    # 保存当前控制器的相关参数至序列化文件
    def _save(self):
        with open(self._ser_path, 'wb') as f:
            pickle.dump(self.get_public_var(), f)

    # 增加全局引用计数
    def _inc_count(self):
        count = 1
        if os.path.exists(self._count_path):
            with open(self._count_path, 'r') as f:
                count = int(f.readline()) + 1

        with open(self._count_path, 'w') as f:
            f.write(str(count))

    # 释放资源前减少全局引用计数
    def _dec_count(self):
        count = 0
        if os.path.exists(self._count_path):
            with open(self._count_path, 'r') as f:
                count = int(f.readline()) - 1

            if count > 0:
                with open(self._count_path, 'w') as f:
                    f.write(str(count))
                return False
            else:
                return True
        else:
            raise RuntimeError('Cannot find the processes count file.')

    # 过滤出需要保存的参数
    def get_public_var(self):
        dic = self.__dict__
        public_var = {key: value for key, value in dic.items() if not key.startswith('_')}
        return public_var

    # 在__del__方法被调用前执行的去初始化方法
    def _deinit(self):
        with self._lock:
            finalize = self._dec_count()
        # 引用记数归零则删除临时文件路径,并发送指令保证电机停转
        if finalize:
            self.reset()
            shutil.rmtree(self._temp_path)
