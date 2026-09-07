#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from sys import modules

from src.scenes.helper import Helper
from src.scenes.lane_following import LF
from src.scenes.manual import Manual
from src.scenes.redlight import RedLight
from src.scenes.tracking import Tracking
from src.utils import log

__all__ = ['Manual', 'Tracking', 'Helper', 'LF', 'RedLight', 'scene_initiator']


def scene_initiator(name):
    try:
        scene = getattr(modules.get(__name__), name)
    except AttributeError:
        log.error(f"{name} doesn't exist.")
        return None
    if isinstance(scene, type):
        return scene

    log.error(f"{name} is not a valid scene.")
    return None
