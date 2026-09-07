#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from src.utils.common_utils import SingleTonType
from src.utils.constant import GB, LOG_NAME, LOG_TYPE

log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), os.pardir, LOG_NAME)


class Logger(logging.Logger):
    def __init__(self, logger_name=LOG_TYPE, log_dir=log_path):
        super(Logger, self).__init__(logger_name)
        self.level = logging.INFO
        self._format = logging.Formatter("%(asctime)s [%(processName)s:%(process)d][%(levelname)s]: %(message)s",
                                         "%Y-%m-%d %H:%M:%S")
        self.setup_logging_file(log_dir)
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(self.level)
        console.setFormatter(self._format)
        self.addHandler(console)

    def setup_logging_file(self, log_dir):
        log_dir = os.path.realpath(log_dir)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, mode=0o750, exist_ok=True)
        log_file_name = f'{datetime.datetime.now()}.log'
        file_handle = RotatingFileHandler(os.path.join(log_dir, log_file_name), maxBytes=GB)
        file_handle.setLevel(logging.DEBUG)
        file_handle.setFormatter(self._format)
        self.addHandler(file_handle)


class SingletonLogger(metaclass=SingleTonType):
    def get_logger(self):
        return Logger()


logger_instance = SingletonLogger().get_logger()
