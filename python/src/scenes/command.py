from src.actions import Stop
from src.scenes.base_scene import BaseScene


class Command(BaseScene):
    def __init__(self, memory_name, camera_info, msg_queue):
        super().__init__(memory_name, camera_info, msg_queue)

    def init_state(self):
        pass

    def loop(self):
        self.init_state()
        while True:
            try:
                if not self.msg_queue.empty():
                    key = self.msg_queue.get()
                else:
                    continue
            except KeyboardInterrupt:
                self.ctrl.execute(Stop())
                break
