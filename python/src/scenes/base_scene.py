#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from ctypes import c_bool
from multiprocessing import shared_memory, Value

from src.utils import Controller


class BaseScene(ABC):
    def __init__(self, memory_name, camera_info, msg_queue):
        self.pause_sign = Value(c_bool, False)
        self.stop_sign = Value(c_bool, False)
        self.ctrl = Controller()
        self.msg_queue = msg_queue
        self.broadcaster = shared_memory.SharedMemory(name=memory_name)
        self.camera_info = camera_info
        self.height = self.camera_info.get('height', 720)
        self.width = self.camera_info.get('width', 1280)
        self.fps = self.camera_info.get('fps', 30)

    @abstractmethod
    def init_state(self):
        pass

    @abstractmethod
    def loop(self):
        pass
