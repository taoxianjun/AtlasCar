import unittest
from unittest.mock import MagicMock, patch
import json
import serial
import carControl  # 导入你的模块


class TestCarControl(unittest.TestCase):

    def setUp(self):
        self.ser = MagicMock(spec=serial.Serial)
        carControl.ser = self.ser

    def test_speed(self):
        self.ser.readline.return_value = b'{"speed": [1, 10]}'
        result = carControl.speed('up')
        self.assertEqual(result, [1, 10])
        self.ser.readline.return_value = b'{"speed": [-1, 10]}'
        result = carControl.speed('down')
        self.assertEqual(result, [-1, 10])
        self.ser.readline.return_value = b'{"speed": [0, 5]}'
        result = carControl.speed(5)
        self.assertEqual(result, [0, 5])

    def test_move(self):
        self.ser.readline.return_value = b'{"speed": [0, 10]}'
        result = carControl.move('STOP')
        self.assertEqual(result, [0, 10])
        self.ser.readline.return_value = b'{"speed": [0, 10]}'
        result = carControl.move('LEFT', 1)
        self.assertEqual(result, [0, 10])

    def test_servo(self):
        self.ser.readline.return_value = b'{"speed": [0, 10]}'
        result = carControl.servo(90, 90)
        self.assertEqual(result, [0, 10])

    def test_check_distance(self):
        self.ser.readline.return_value = b'{"distance": 10}'
        result = carControl.check_distance()
        self.assertEqual(result, 10)

    def test_read_serial(self):
        self.ser.readline.return_value = b'{"speed": [0, 10]}'
        result = carControl.read_serial()
        self.assertEqual(result, [0, 10])
        self.ser.readline.return_value = b'{"distance": 10}'
        result = carControl.read_serial("distance")
        self.assertEqual(result, 10)


if __name__ == '__main__':
    unittest.main()
