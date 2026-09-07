import unittest
import os
import sys
from unittest.mock import patch, MagicMock
from src.utils.common_utils import SingleTonType, path_check, load_yaml, getkey


class TestSingleTonType(unittest.TestCase):
    def test_singleton(self):
        # Test that the SingleTonType metaclass creates a singleton instance
        class TestClass(metaclass=SingleTonType):
            def __init__(self, value):
                self.value = value

        instance1 = TestClass(1)
        instance2 = TestClass(2)
        self.assertEqual(instance1, instance2)
        self.assertEqual(instance1.value, 1)
        self.assertEqual(instance2.value, 1)

class TestPathCheck(unittest.TestCase):
    def test_path_check(self):
        # Test that path_check raises the correct exceptions for invalid paths
        with self.assertRaises(FileNotFoundError):
            path_check('nonexistent_file.txt')
        with self.assertRaises(PermissionError):
            path_check('/etc/shadow')

class TestLoadYaml(unittest.TestCase):
    def test_load_yaml(self):
        # Test that load_yaml loads a YAML file correctly
        config = load_yaml('test_config.yaml')
        self.assertEqual(config['name'], 'Test Config')
        self.assertEqual(config['value'], 42)

class TestGetKey(unittest.TestCase):
    @patch('os.read')
    @patch('termios.tcsetattr')
    @patch('tty.setcbreak')
    @patch('termios.tcgetattr')
    def test_getkey(self, mock_tcgetattr, mock_setcbreak, mock_tcsetattr, mock_read):
        # Test that getkey returns the correct key mappings for different keys
        mock_tcgetattr.return_value = MagicMock()
        mock_setcbreak.return_value = None
        mock_tcsetattr.return_value = None
        mock_read.side_effect = [b'a', b'b', b'\x1b', b'[', b'A', b' ']
        self.assertEqual(getkey(), 'a')
        self.assertEqual(getkey(), 'b')
        self.assertEqual(getkey(), 'esc')
        self.assertEqual(getkey(), '[')
        self.assertEqual(getkey(), 'up')
        self.assertEqual(getkey(), 'space')

if __name__ == '__main__':
    unittest.main()