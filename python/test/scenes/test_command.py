import unittest
from multiprocessing import Queue
from unittest.mock import patch
from src.actions import Stop
from src.scenes.command import Command

class TestCommand(unittest.TestCase):
    def setUp(self):
        self.memory_name = 'test_memory'
        self.camera_info = {'height': 480, 'width': 640, 'fps': 30}
        self.msg_queue = Queue()
        self.command = Command(self.memory_name, self.camera_info, self.msg_queue)

    def tearDown(self):
        del self.memory_name
        del self.camera_info
        del self.msg_queue
        del self.command

    def test_init_state(self):
        # Test that the init_state method does not raise an exception
        self.command.init_state()

    @patch('src.scenes.command.Command.init_state')
    @patch('src.scenes.command.Command.ctrl.execute')
    def test_loop(self, mock_execute, mock_init_state):
        # Test that the loop method executes the Stop action when KeyboardInterrupt is raised
        mock_init_state.return_value = None
        self.msg_queue.put('test')
        with self.assertRaises(KeyboardInterrupt):
            self.command.loop()
        mock_execute.assert_called_once_with(Stop())

if __name__ == '__main__':
    unittest.main()