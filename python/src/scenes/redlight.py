#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例场景：红绿灯识别 -> 行车决策。

本文件是"扩展新识别任务"的标准模板，用来证明项目并不局限于路标识别：
只要准备好一个 YOLOv5 格式的 .om 模型，把"检测类别 -> 小车动作"的映射写在这里，
再注册到 scenes/__init__.py 与 cloud_control.py 的 MODE_SCENES，
就能让小车识别任意目标并做出对应动作。相机采集、Controller、MQTT 等底层一律不用改。

使用方式：
  - 本地：python main.py --mode cmd   然后输入 RedLight
  - 云端：下发 set_mode = redlight
  - 需自备模型：weights/redlight.om （类别需包含 red_light / green_light）

关键点：YoloV5 类默认把类名写死成 ['left','right','stop','turnaround']，
所以加载其它模型后必须覆盖 self.model.names，使其与 redlight.om 的实际类别顺序一致，
否则返回的类别名会错乱。换模型时只改 MODEL_CLASSES 与 ACTION_MAP 两处即可。
"""
import os
import time

import numpy as np

from src.actions import SetServo, Stop, Advance
from src.models import YoloV5
from src.scenes.base_scene import BaseScene
from src.utils import log


class RedLight(BaseScene):
    """检测红绿灯并按灯色停车 / 通行。可作为"新增识别任务"的模板。"""

    # redlight.om 的类别顺序（必须与训练时一致，索引即 YOLOv5 输出的 class_id）
    MODEL_CLASSES = ['red_light', 'green_light']

    # 类别名 -> 动作语义。想支持更多目标，继续往这里加即可。
    ACTION_MAP = {
        'red_light': 'stop',
        'green_light': 'go',
    }

    def __init__(self, memory_name, camera_info, msg_queue,
                 model_path=None, cruise_speed=25):
        super().__init__(memory_name, camera_info, msg_queue)
        self.model = None
        self.model_path = model_path or os.path.join(os.getcwd(), 'weights', 'redlight.om')
        self.cruise_speed = cruise_speed

    def init_state(self):
        log.info(f'start init {self.__class__.__name__}')
        if not os.path.exists(self.model_path):
            log.error(f'Cannot find the offline inference model(.om) file needed for '
                      f'{self.__class__.__name__} scene: {self.model_path}')
            return True
        self.model = YoloV5(self.model_path)
        # 覆盖 YoloV5 默认写死的类别名，使其匹配本场景的模型
        self.model.names = list(self.MODEL_CLASSES)
        log.info(f'{self.__class__.__name__} model init succ.')
        self.ctrl.execute(SetServo(servo=[90, 65]))
        return False

    def loop(self):
        ret = self.init_state()
        if ret:
            log.error(f'{self.__class__.__name__} init failed.')
            return
        frame = np.ndarray((self.height, self.width, 3), dtype=np.uint8, buffer=self.broadcaster.buf)
        log.info(f'{self.__class__.__name__} loop start')
        last_action = None
        try:
            while True:
                if self.stop_sign.value:
                    break
                if self.pause_sign.value:
                    continue

                img_bgr = frame.copy()
                bboxes = self.model.infer(img_bgr)
                # 只保留本场景关心的类别
                bboxes = [b for b in bboxes if b[4] in self.ACTION_MAP]
                if not bboxes:
                    # 没看到灯：保持慢速巡航（也可改成 Stop，看需求）
                    if last_action != 'cruise':
                        self.ctrl.execute(Advance(speed=self.cruise_speed))
                        last_action = 'cruise'
                    continue

                # 取置信度最高的目标
                bboxes = sorted(bboxes, key=lambda x: x[5], reverse=True)
                cate = bboxes[0][4]
                action = self.ACTION_MAP.get(cate)
                if action is None or action == last_action:
                    continue

                if action == 'stop':
                    self.ctrl.execute(Stop())
                elif action == 'go':
                    self.ctrl.execute(Advance(speed=self.cruise_speed))
                last_action = action
                log.info(f'redlight decision: {cate} -> {action}')
        except KeyboardInterrupt:
            self.ctrl.execute(Stop())
