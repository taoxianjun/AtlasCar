#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os

import numpy as np

from src.actions import SetServo, Stop, TurnLeft, TurnRight, Advance
from src.models import YoloV5
from src.scenes.base_scene import BaseScene
from src.utils import log


class Tracking(BaseScene):
    def __init__(self, memory_name, camera_info, msg_queue):
        super().__init__(memory_name, camera_info, msg_queue)
        self.model = None

    def init_state(self):
        log.info(f'start init {self.__class__.__name__}')
        model_path = os.path.join(os.getcwd(), 'weights', 'tracking.om')
        if not os.path.exists(model_path):
            log.error(f'Cannot find the offline inference model(.om) file needed for {self.__class__.__name__}  scene.')
            return True
        self.model = YoloV5(model_path)
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
        last_not_seen = True
        forward_speed_slow = 30
        forward_speed_fast = 40
        while True:
            action = None
            if self.stop_sign.value:
                break
            if self.pause_sign.value:
                continue

            img_bgr = frame.copy()
            bboxes = self.model.infer(img_bgr)
            log.info(f'{bboxes}')
            if not bboxes:
                if last_not_seen:
                    action = Stop()
                else:
                    last_not_seen = True
                    continue
            else:
                if len(bboxes) > 1:
                    ori_box = sorted(bboxes, key=lambda x: x[-1], reverse=True)[0][:4]
                else:
                    ori_box = bboxes[0][:4]
                x1, y1, x2, y2 = ori_box
                x, y = (x1 + x2) // 2, (y1 + y2) // 2
                h, w = y2 - y1, x2 - x1

                if h * w < 141 * 128 or y < 110:
                    speed = forward_speed_fast
                else:
                    speed = forward_speed_slow

                if x < 400:
                    action = TurnLeft(degree=1.1, speed=speed)
                elif x > 1000:
                    action = TurnRight(degree=1.1, speed=speed)
                else:
                    action = Advance(speed=speed)

                if h * w > 800 * 500 or y > 390:
                    action = Stop()

            if action is None or action == last_action:
                continue
            self.ctrl.execute(action)
            last_action = action
