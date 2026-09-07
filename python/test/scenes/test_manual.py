import unittest
from multiprocessing import Queue
from unittest.mock import patch, MagicMock

from src.actions import SetServo, Advance
from src.scenes.manual import Manual


class TestManual(unittest.TestCase):
    def setUp(self):
        self.memory_name = 'test_memory'
        self.camera_info = {'height': 480, 'width': 640, 'fps': 30}
        self.msg_queue = Queue()
        self.manual = Manual(self.memory_name, self.camera_info, self.msg_queue)

    def tearDown(self):
        del self.memory_name
        del self.camera_info
        del self.msg_queue
        del self.manual

    @patch('src.scenes.manual.os.path.exists')
    @patch('src.scenes.manual.log')
    def test_init_state(self, mock_log, mock_path_exists):
        # Test that the init_state method executes the SetServo action
        mock_path_exists.return_value = True
        self.manual.ctrl.execute = MagicMock()
        self.manual.init_state()
        self.manual.ctrl.execute.assert_called_once_with(SetServo(servo=[90, 65]))

    @patch('src.scenes.manual.os.path.exists')
    @patch('src.scenes.manual.log')
    def test_init_state_missing_file(self, mock_log, mock_path_exists):
        # Test that the init_state method logs an error message when the LFNet model file is missing
        mock_path_exists.return_value = False
        self.manual.init_state()
        mock_log.error.assert_called_once_with('Cannot find the offline inference model(.om) file needed for LF scene.')

    @patch('src.scenes.manual.BaseScene.init_state')
    @patch('src.scenes.manual.log')
    def test_loop(self, mock_log, mock_init_state):
        # Test that the loop method executes the correct actions based on the key input
        mock_init_state.return_value = False
        self.manual.ctrl.execute = MagicMock()
        self.manual.broadcaster.buf = bytearray(640 * 480 * 3)
        self.manual.msg_queue.put('up')
        self.manual.loop()
        self.manual.ctrl.execute.assert_called_once_with(Advance(speed_setting=[29, 0, 0, 0], update_speed=False))


if __name__ == '__main__':
    unittest.main()
