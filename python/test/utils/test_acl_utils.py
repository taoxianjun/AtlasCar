import unittest
from unittest.mock import patch, MagicMock
from src.utils import acl_utils
from src.utils.constant import SUCCESS, ACL_MEM_MALLOC_HUGE_FIRST, ACL_MEMCPY_DEVICE_TO_DEVICE


class TestAclUtils(unittest.TestCase):
    @patch('acl.rt.set_device')
    @patch('acl.rt.create_context')
    def test_init_acl(self, mock_create_context, mock_set_device):
        # Test that init_acl sets up the context and device correctly
        mock_create_context.return_value = (MagicMock(), SUCCESS)
        mock_set_device.return_value = SUCCESS
        context = acl_utils.init_acl(0)
        self.assertIsNotNone(context)
        mock_create_context.assert_called_once_with(0)
        mock_set_device.assert_called_once_with(0)

    @patch('acl.rt.destroy_context')
    @patch('acl.rt.reset_device')
    @patch('acl.finalize')
    def test_deinit_acl(self, mock_finalize, mock_reset_device, mock_destroy_context):
        # Test that deinit_acl cleans up the context and device correctly
        context = MagicMock()
        mock_destroy_context.return_value = SUCCESS
        mock_reset_device.return_value = SUCCESS
        mock_finalize.return_value = SUCCESS
        acl_utils.deinit_acl(context, 0)
        mock_destroy_context.assert_called_once_with(context)
        mock_reset_device.assert_called_once_with(0)
        mock_finalize.assert_called_once()

    @patch('acl.rt.malloc')
    @patch('acl.rt.memcpy')
    def test_copy_data_device_to_device(self, mock_memcpy, mock_malloc):
        # Test that copy_data_device_to_device correctly copies data from one device to another
        data_size = 1024
        device_data = MagicMock()
        device_buffer = MagicMock()
        mock_malloc.return_value = (device_buffer, SUCCESS)
        mock_memcpy.return_value = SUCCESS
        result = acl_utils.copy_data_device_to_device(device_data, data_size)
        self.assertEqual(result, device_buffer)
        mock_malloc.assert_called_once_with(data_size, ACL_MEM_MALLOC_HUGE_FIRST)
        mock_memcpy.assert_called_once_with(device_buffer, data_size, device_data, data_size, ACL_MEMCPY_DEVICE_TO_DEVICE)
    

if __name__ == '__main__':
    unittest.main()