#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import threading
import tty

import termios
from yaml import safe_load


# 单例类
class SingleTonType(type):
    _instance_lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if not hasattr(cls, '_instance'):
            with SingleTonType._instance_lock:
                if not hasattr(cls, '_instance'):
                    cls._instance = super(SingleTonType, cls).__call__(*args, **kwargs)
        return cls._instance


def path_check(path: str):
    base_name = os.path.basename(path)
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f'{base_name} does not exist.')
    if not os.access(path, mode=os.R_OK):
        raise PermissionError(f'{base_name} is unreadable')


def load_yaml(config_path: str):
    path_check(config_path)
    with open(config_path, 'r') as f:
        config = safe_load(f.read())
    return config


def getkey():
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    try:
        while True:
            b = os.read(sys.stdin.fileno(), 3).decode()
            if len(b) == 3:
                k = ord(b[2])
            else:
                k = ord(b)
            key_mapping = {
                127: 'backspace',
                10: 'return',
                32: 'space',
                9: 'tab',
                27: 'esc',
                65: 'up',
                66: 'down',
                67: 'right',
                68: 'left'
            }
            return key_mapping.get(k, chr(k))

    except TypeError:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
