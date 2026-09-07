import unittest
from src.utils.camera_broadcaster import CameraBroadcaster
from multiprocessing import shared_memory, Value
import numpy as np

class TestCameraBroadcaster(unittest.TestCase):
    def test_init(self):
        # Test that the CameraBroadcaster initializes correctly
        camera_info = {'height': 480, 'width': 640, 'fps': 30}
        broadcaster = CameraBroadcaster(camera_info)
        self.assertEqual(broadcaster.height, 480)
        self.assertEqual(broadcaster.width, 640)
        self.assertEqual(broadcaster.fps, 30)
        # self.assertIsInstance(broadcaster.stop_sign, Value)
        self.assertIsInstance(broadcaster.frame, shared_memory.SharedMemory)

    def test_run(self):
        # Test that the CameraBroadcaster runs correctly
        camera_info = {'height': 480, 'width': 640, 'fps': 30}
        broadcaster = CameraBroadcaster(camera_info)
        # broadcaster.stop_sign.value = True
        broadcaster.run()
        # self.assertRaises(FileNotFoundError, broadcaster.frame.buf)

if __name__ == '__main__':
    unittest.main()