import unittest
from multiprocessing import Queue, Value
from unittest.mock import patch, MagicMock

from src.actions import SetServo, Stop, Advance
from src.models import YoloV5
from src.scenes.tracking import Tracking


class TestTracking(unittest.TestCase):
    def setUp(self):
        self.memory_name = 'test_memory'
        self.camera_info = {'height': 480, 'width': 640, 'fps': 30}
        self.msg_queue = Queue()
        self.tracking = Tracking(self.memory_name, self.camera_info, self.msg_queue)
        self.tracking.broadcaster.buf = bytearray(640 * 480 * 3)
        self.tracking.stop_sign = Value('i', 0)
        self.tracking.pause_sign = Value('i', 0)

    def tearDown(self):
        del self.memory_name
        del self.camera_info
        del self.msg_queue
        del self.tracking

    @patch('src.scenes.tracking.os.path.exists')
    @patch('src.scenes.tracking.log')
    def test_init_state(self, mock_log, mock_path_exists):
        # Test that the init_state method executes the SetServo action
        # and logs an error message when the tracking.om file is missing
        mock_path_exists.return_value = False
        ret = self.tracking.init_state()
        self.assertTrue(ret)
        mock_log.error.assert_called_once_with(
            'Cannot find the offline inference model(.om) file needed for Tracking scene.')

        mock_path_exists.return_value = True
        self.tracking.ctrl.execute = MagicMock()
        ret = self.tracking.init_state()
        self.assertFalse(ret)
        self.tracking.ctrl.execute.assert_called_once_with(SetServo(servo=[90, 65]))

    @patch('src.scenes.tracking.BaseScene.init_state')
    @patch('src.scenes.tracking.log')
    def test_loop(self, mock_log, mock_init_state):
        # Test that the loop method executes the correct actions
        # based on the bounding boxes returned by the YoloV5 model
        mock_init_state.return_value = False
        self.tracking.ctrl.execute = MagicMock()
        self.tracking.model = MagicMock(spec=YoloV5)
        self.tracking.model.infer.return_value = []
        self.tracking.loop()
        self.tracking.ctrl.execute.assert_called_once_with(Stop())

        self.tracking.model.infer.return_value = [[100, 200, 300, 400, 0.9]]
        self.tracking.loop()
        self.tracking.ctrl.execute.assert_called_with(Advance(speed=30))


if __name__ == '__main__':
    unittest.main()
