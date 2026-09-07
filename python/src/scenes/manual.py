import datetime
import os

import cv2
import numpy as np

from src.actions import Advance, Stop, SetServo, TurnLeft, TurnRight, SpinClockwise, SpinAntiClockwise, BackUp, \
    ShiftLeft, ShiftRight, CustomAction
from src.actions.complex_actions import ComplexAction, TurnAround
from src.scenes.base_scene import BaseScene
from src.utils import log


class Manual(BaseScene):
    def __init__(self, memory_name, camera_info, msg_queue):
        super().__init__(memory_name, camera_info, msg_queue)
        self.speed = 22
        self.save_dir = os.path.join(os.getcwd(), 'capture')
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir, exist_ok=True)

    def init_state(self):
        self.ctrl.execute(SetServo(servo=[90, 90]))  # servo[1] = camera LEFT/RIGHT (90 = front-center); servo[0] unwired

    def loop(self):
        ret = self.init_state()
        if ret:
            log.error(f'{self.__class__.__name__} init failed.')
            return
        frame = np.ndarray((self.height, self.width, 3), dtype=np.uint8, buffer=self.broadcaster.buf)
        log.info(f'{self.__class__.__name__} loop start')
        last_action = SetServo(servo=[90, 90])  # servo[1] = camera LEFT/RIGHT (90 = front-center); servo[0] unwired

        while True:
            try:
                if not self.msg_queue.empty():
                    key = self.msg_queue.get()
                else:
                    continue
            except KeyboardInterrupt:
                self.ctrl.execute(Stop())
                break

            degree = 0
            if key == 'up':
                self.speed = min(self.speed + 1, 60)
            elif key == 'down':
                self.speed = max(self.speed - 1, 20)
            elif key == 'left':
                last_action = ShiftLeft()
            elif key == 'right':
                last_action = ShiftRight()
            elif key == 'w':
                last_action = Advance()
            elif key == 'a':
                last_action = TurnLeft()
                degree = 1.1
            elif key == 's':
                last_action = BackUp()
            elif key == 'd':
                last_action = TurnRight()
                degree = 1.1
            elif key == 'q':
                last_action = SpinAntiClockwise()
            elif key == 'e':
                last_action = SpinClockwise()
            elif key == 'space':
                last_action = Stop()
            elif key == 'esc':
                self.ctrl.execute(Stop())
                break
            elif key == 'c':
                save_img = frame.copy()
                cv2.imwrite(os.path.join(self.save_dir, f'{datetime.datetime.now()}.jpg'), save_img)
                log.info(f'image saved.')
            elif key == 't':
                last_action = CustomAction(motor_setting=[-62, 50, 50, -50])
            elif key == 'r':
                last_action = CustomAction(motor_setting=[55, -50, -50, 50])
            elif key == 'z':
                last_action = TurnAround()
            elif key == 'x':
                from src.actions.complex_actions import Spin
                last_action = Spin()
            else:
                continue

            if not isinstance(last_action, ComplexAction) and not isinstance(last_action, CustomAction):
                last_action.update_speed = False
                last_action.speed_setting = last_action.generate_speed_setting(speed=self.speed, degree=degree)
                last_action.fix_speed()
            self.ctrl.execute(last_action)
