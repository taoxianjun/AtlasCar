import unittest
from multiprocessing import Queue
from unittest.mock import patch, MagicMock
from src.actions import SetServo, Stop, Start, TurnLeft, TurnRight, Advance, TurnAround
from src.models import LFNet
from src.scenes.lane_following import LF

class TestLF(unittest.TestCase):
    def setUp(self):
        self.memory_name = 'test_memory'
        self.camera_info = {'height': 480, 'width': 640, 'fps': 30}
        self.msg_queue = Queue()
        self.lf = LF(self.memory_name, self.camera_info, self.msg_queue)

    def tearDown(self):
        del self.memory_name
        del self.camera_info
        del self.msg_queue
        del self.lf

    @patch('src.scenes.lane_following.os.path.exists')
    @patch('src.scenes.lane_following.LFNet')
    @patch('src.scenes.lane_following.BaseScene.init_state')
    @patch('src.scenes.lane_following.log')
    def test_init_state(self, mock_log, mock_init_state, mock_lfnet, mock_path_exists):
        # Test that the init_state method initializes the LFNet model and executes the SetServo action
        mock_path_exists.return_value = True
        mock_init_state.return_value = False
        mock_lfnet.return_value = MagicMock()
        self.lf.init_state()
        mock_lfnet.assert_called_once_with('weights/lfnet.om')
        self.lf.ctrl.execute.assert_called_once_with(SetServo(servo=[90, 65]))

    @patch('src.scenes.lane_following.BaseScene.init_state')
    @patch('src.scenes.lane_following.log')
    def test_init_state_missing_file(self, mock_log, mock_init_state):
        # Test that the init_state method logs an error message when the LFNet model file is missing
        mock_init_state.return_value = False
        self.lf.init_state()
        mock_log.error.assert_called_once_with('Cannot find the offline inference model(.om) file needed for LF scene.')

    @patch('src.scenes.lane_following.BaseScene.init_state')
    @patch('src.scenes.lane_following.log')
    def test_init_state_init_failed(self, mock_log, mock_init_state):
        # Test that the init_state method logs an error message when the init_state method returns True
        mock_init_state.return_value = True
        self.lf.init_state()
        mock_log.error.assert_called_once_with('LF init failed.')

    @patch('src.scenes.lane_following.BaseScene.init_state')
    @patch('src.scenes.lane_following.log')
    def test_loop(self, mock_log, mock_init_state):
        # Test that the loop method executes the correct actions based on the LFNet model output
        mock_init_state.return_value = False
        self.lf.net = MagicMock()
        self.lf.net.infer.return_value = [70.0]
        self.lf.loop()
        self.lf.ctrl.execute.assert_called_once_with(TurnLeft(degree=0.7))

if __name__ == '__main__':
    unittest.main()