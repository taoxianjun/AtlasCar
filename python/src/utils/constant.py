#!/usr/bin/env python3
# -*- coding: utf-8 -*-

DEVICE_ID = 0

SUCCESS = 0
FAILED = 1

ACL_MEM_MALLOC_HUGE_FIRST = 0
ACL_MEM_MALLOC_NORMAL_ONLY = 2
ACL_MEMCPY_DEVICE_TO_DEVICE = 3

LOG_NAME = 'logs'
LOG_TYPE = 'CAR'

GB = 1024 * 1024 * 1024

ACL_FLOAT = 0
ACL_FLOAT16 = 1
ACL_INT8 = 2
ACL_INT32 = 3
ACL_UINT8 = 4
ACL_INT16 = 6
ACL_UINT16 = 7
ACL_UINT32 = 8
ACL_INT64 = 9
ACL_UINT64 = 10
ACL_DOUBLE = 11
ACL_BOOL = 12

CAMERA_INFO = {
    'height': 720,
    'width': 1280,
    'fps': 30
}

PORT_CODE_FINDER = '''
#!/bin/bash
for sysdevpath in $(find /sys/bus/usb/devices/usb*/ -name dev); do
    (
        syspath="${sysdevpath%/dev}"
        devname="$(udevadm info -q name -p $syspath)"
        [[ "$devname" == "bus/"* ]] && exit
        eval "$(udevadm info -q property --export -p $syspath)"
        [[ -z "$ID_SERIAL" ]] && exit
        echo "/dev/$devname - $ID_SERIAL"
    )
done
'''

ESP32_NAME = '1a86_USB_Serial'
