#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端 MQTT 控制编排层。

把华为云 IoTDA 下发的命令翻译成小车现有的按键/场景操作：
命令 -> msg_queue -> Manual 场景进程 -> Controller -> 串口 -> ESP32，
因此不需要改动任何既有的运动控制与推理代码。
"""

import json
import os
import threading
import time
from multiprocessing import Process

from src.actions import Stop
from src.scenes import scene_initiator
from src.utils import CameraCapture, log
from src.utils.iot_client import IoTDAClient

# 云端动作名 -> Manual 场景已支持的按键
ACTION_KEY_MAP = {
    'forward': 'w',
    'backward': 's',
    'turn_left': 'a',
    'turn_right': 'd',
    'spin_left': 'q',
    'spin_right': 'e',
    'shift_left': 'left',
    'shift_right': 'right',
    'turn_around': 'z',
    'capture': 'c',
    'stop': 'space',
}
# 下发后不需要看门狗兜底刹车的动作
STATIC_ACTIONS = {'stop', 'capture'}

# 自动驾驶等预设场景，值为需要依次拉起的场景名
MODE_SCENES = {
    'manual': ['Manual'],
    'auto': ['Helper', 'LF'],
    'tracking': ['Tracking'],
    'redlight': ['RedLight'],
    'idle': [],
}

SPEED_MIN, SPEED_MAX, SPEED_DEFAULT = 25, 60, 29
SERVICE_ID = 'CarControl'

DEFAULT_CONFIG = {
    'device_id': '',
    'secret': '',
    'host': 'iot-mqtts.cn-north-4.myhuaweicloud.com',
    'port': 1883,
    'ca_cert': '',
    'sign_type': 0,
    # 超过该秒数没收到新指令则自动刹车，防止断网后小车失控
    'command_timeout': 3.0,
    # 状态上报间隔，单位秒
    'report_interval': 10.0,
    # 数据集照片根目录
    'dataset_root': 'dataset',
}


def load_config(config_path=None):
    """优先读环境变量，其次读 json 配置文件，最后用默认值。"""
    config = dict(DEFAULT_CONFIG)

    path = config_path or os.path.join(os.getcwd(), 'cloud_config.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            config.update(json.load(f))

    env_map = {
        'device_id': 'IOT_DEVICE_ID',
        'secret': 'IOT_DEVICE_SECRET',
        'password': 'IOT_PASSWORD',
        'client_id': 'IOT_CLIENT_ID',
        'host': 'IOT_SERVER',
        'port': 'IOT_PORT',
        'ca_cert': 'IOT_CA_CERT',
    }
    for key, env in env_map.items():
        if os.environ.get(env):
            config[key] = os.environ[env]

    if not config['device_id'] or not (config.get('secret') or config.get('password')):
        raise ValueError(f'device_id/secret/password 未配置，请填写 {path} 或设置 IOT_DEVICE_ID/IOT_DEVICE_SECRET/IOT_PASSWORD')
    return config


class CloudControl:
    def __init__(self, shared_memory_name, camera_info, msg_queue, ctrl, config):
        self.shared_memory_name = shared_memory_name
        self.camera_info = camera_info
        self.msg_queue = msg_queue
        self.ctrl = ctrl
        self.config = config

        self.mode = 'idle'
        self.speed = SPEED_DEFAULT
        self.moving = False
        self.last_command_time = time.time()
        self._duration_timer = None
        self._scene_processes = []
        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        # 远程数据集采集：直接从共享内存取帧落盘，无需经过 Manual 场景
        self.capturer = CameraCapture(shared_memory_name, camera_info,
                                      dataset_root=config.get('dataset_root', 'dataset'))
        self.client = IoTDAClient(
            device_id=config['device_id'],
            secret=config.get('secret'),
            host=config['host'],
            port=config['port'],
            ca_cert=config['ca_cert'] or None,
            sign_type=config['sign_type'],
            password=config.get('password'),
            client_id=config.get('client_id'),
        )
        self.client.command_handler = self.handle_command

    # ------------------------------------------------------------------ 命令处理

    def handle_command(self, command_name, paras):
        with self._lock:
            self.last_command_time = time.time()

            if command_name in ('move', 'control'):
                return self._do_move(paras)
            if command_name == 'key':
                return self._do_key(paras.get('value', ''))
            if command_name == 'set_mode':
                return self._do_set_mode(paras.get('mode', ''))
            if command_name == 'set_speed':
                return self._do_set_speed(paras.get('speed', SPEED_DEFAULT))
            if command_name == 'capture':
                return self._do_capture(paras)
            if command_name in ('emergency_stop', 'stop'):
                return self._do_emergency_stop()
            if command_name == 'heartbeat':
                return 0, {'status': 'alive'}

            log.warn(f'unknown command: {command_name}')
            return 1, {'error': f'unknown command {command_name}'}

    def _do_move(self, paras):
        action = str(paras.get('action', '')).lower()
        key = ACTION_KEY_MAP.get(action)
        if key is None:
            return 1, {'error': f'unsupported action {action}'}

        if self.mode != 'manual':
            self._do_set_mode('manual')

        speed = paras.get('speed')
        if speed is not None:
            self._do_set_speed(speed)

        self._put_key(key)
        self.moving = action not in STATIC_ACTIONS

        # 带时长的动作到点自动停车
        self._cancel_duration_timer()
        duration = paras.get('duration')
        if self.moving and duration:
            self._duration_timer = threading.Timer(float(duration), self._timed_stop)
            self._duration_timer.daemon = True
            self._duration_timer.start()

        return 0, {'action': action, 'speed': self.speed}

    def _do_key(self, value):
        if not value:
            return 1, {'error': 'empty key'}
        if self.mode != 'manual':
            self._do_set_mode('manual')
        self._put_key(value)
        self.moving = value not in ('space', 'c')
        return 0, {'key': value}

    def _do_set_mode(self, mode):
        mode = str(mode).lower()
        if mode not in MODE_SCENES:
            return 1, {'error': f'unsupported mode {mode}, expect {list(MODE_SCENES)}'}
        if mode == self.mode:
            return 0, {'mode': mode}

        self._kill_scenes()
        for name in MODE_SCENES[mode]:
            scene = scene_initiator(name)
            if scene is None:
                self._kill_scenes()
                return 1, {'error': f'scene {name} not found'}
            scene_obj = scene(self.shared_memory_name, self.camera_info, self.msg_queue)
            process = Process(target=scene_obj.loop)
            process.start()
            self._scene_processes.append(process)

        self.mode = mode
        self.speed = SPEED_DEFAULT
        self.moving = False
        log.info(f'mode switched to {mode}')
        return 0, {'mode': mode}

    def _do_set_speed(self, speed):
        try:
            target = int(speed)
        except (TypeError, ValueError):
            return 1, {'error': f'invalid speed {speed}'}
        target = max(SPEED_MIN, min(SPEED_MAX, target))

        # Manual 场景内部只认加减速按键，这里用按键把速度推到目标值
        key = 'up' if target > self.speed else 'down'
        for _ in range(abs(target - self.speed)):
            self._put_key(key)
        self.speed = target
        return 0, {'speed': self.speed}

    # ------------------------------------------------------------------ 远程采集
    def _do_capture(self, paras):
        label = str(paras.get('label') or self.capturer.default_label)
        try:
            count = int(paras.get('count', 1))
        except (TypeError, ValueError):
            count = 1
        count = max(1, min(count, 50))
        interval = float(paras.get('interval', 0)) if paras.get('interval') else 0.0

        taken = []
        for i in range(count):
            r = self.capturer.capture(label=label)
            if r.get('success'):
                taken.append(r)
            if interval and i < count - 1:
                time.sleep(interval)

        log.info(f'cloud capture: {len(taken)}/{count} saved under label "{label}"')
        return 0, {
            'taken': len(taken),
            'label': label,
            'sample': taken[0] if taken else None,
            'summary': self.capturer.summary(),
        }

    def _do_emergency_stop(self):
        self._cancel_duration_timer()
        self._kill_scenes()
        self.ctrl.execute(Stop())
        self.mode = 'idle'
        self.moving = False
        log.warn('emergency stop executed')
        return 0, {'status': 'stopped'}

    # ------------------------------------------------------------------ 内部工具

    def _put_key(self, key):
        self.msg_queue.put(key)

    def _timed_stop(self):
        with self._lock:
            if self.moving:
                self._put_key('space')
                self.moving = False

    def _cancel_duration_timer(self):
        if self._duration_timer is not None:
            self._duration_timer.cancel()
            self._duration_timer = None

    def _kill_scenes(self):
        for process in self._scene_processes:
            try:
                process.kill()
                process.join(timeout=1)
            except Exception as exc:
                # 进程已退出等情况 kill 会抛异常，不应中断急停链路
                log.warn(f'kill scene process failed: {exc}')
        self._scene_processes.clear()
        self.ctrl.execute(Stop())

    # ------------------------------------------------------------------ 后台线程

    def _watchdog_loop(self):
        """指令超时或断连时自动刹车，避免小车拖着旧指令一路狂奔。"""
        timeout = float(self.config['command_timeout'])
        while not self._stop_event.wait(0.2):
            with self._lock:
                # 断网保护（最高优先级）：无论小车处于 manual/auto/tracking 哪种模式，
                # 只要 MQTT 已断连就立即执行硬急停（kill 所有场景进程 + Stop），
                # 杜绝 auto/tracking 模式断网后小车继续自主狂奔失控。
                if not self.client.connected:
                    if self.mode != 'idle':
                        log.warn('watchdog: link lost, emergency stop')
                        self._do_emergency_stop()
                    continue
                # 仅 manual 模式需要「无新指令则刹车」：auto/tracking 由自身逻辑控制运动，
                # 不应因 idle 超时被强行刹停。
                if self.mode != 'manual' or not self.moving:
                    continue
                idle = time.time() - self.last_command_time
                if idle > timeout:
                    log.warn(f'watchdog braking: idle {idle:.1f}s')
                    self._put_key('space')
                    self.moving = False

    def _report_loop(self):
        interval = float(self.config['report_interval'])
        while not self._stop_event.wait(interval):
            self.client.report_properties(SERVICE_ID, {
                'mode': self.mode,
                'speed': self.speed,
                'moving': self.moving,
                'dataset': self.capturer.summary(),
            })

    # ------------------------------------------------------------------ 生命周期

    def run_forever(self):
        for target in (self._watchdog_loop, self._report_loop):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
        try:
            self.client.loop_forever()
        finally:
            self.shutdown()

    def shutdown(self):
        self._stop_event.set()
        self._cancel_duration_timer()
        self._kill_scenes()
        self.client.stop()
        log.info('cloud control stopped')
