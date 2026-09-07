#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import acl

from src.utils.constant import SUCCESS, ACL_MEM_MALLOC_HUGE_FIRST, ACL_MEMCPY_DEVICE_TO_DEVICE
from src.utils.logger import logger_instance as log


def check_ret(message, ret):
    if ret != SUCCESS:
        raise Exception("{} failed ret={}".format(message, ret))


def init_acl(device_id):
    acl.init()
    ret = acl.rt.set_device(device_id)
    if ret:
        raise RuntimeError(ret)
    context, ret = acl.rt.create_context(device_id)
    if ret:
        raise RuntimeError(ret)
    log.info('Init ACL Successfully')
    return context


def deinit_acl(context, device_id):
    ret = acl.rt.destroy_context(context)
    if ret:
        raise RuntimeError(ret)

    ret = acl.rt.reset_device(device_id)
    if ret:
        raise RuntimeError(ret)
    ret = acl.finalize()
    if ret:
        raise RuntimeError(ret)
    log.info('Deinit ACL Successfully')


def copy_data_device_to_device(device_data, data_size):
    device_buffer, ret = acl.rt.malloc(data_size, ACL_MEM_MALLOC_HUGE_FIRST)
    if ret != SUCCESS:
        log.error(f"Malloc device memory failed, error: {ret}")
        return None

    ret = acl.rt.memcpy(device_buffer, data_size,
                        device_data, data_size,
                        ACL_MEMCPY_DEVICE_TO_DEVICE)
    if ret != SUCCESS:
        log.error(f"Copy device data to device memory failed, error: {ret}")
        acl.rt.free(device_buffer)
        return None

    return device_buffer
