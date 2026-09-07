from ctypes import c_bool
from datetime import datetime
from multiprocessing import shared_memory, Value
import subprocess
import time

import cv2
import numpy as np

from src.utils.logger import logger_instance as log

# Camera lock parameters (auto-set by calibrate_camera.py; run it on-device to fill real values).
# EXPOSURE units are driver-specific; calibrate_camera.py scans brightness and picks a value.
# 0 means "not calibrated yet" -> runtime leaves auto-exposure ON so the car still works.
CAMERA_EXPOSURE = 5       # 0 = uncalibrated; auto-written by calibrate_camera.py (2026-08-28 00:46, exp=5)
CAMERA_WB_RED = 1.3003    # gray-world red gain (LEGACY: this UVC cam has NO red/blue gain ctrl -> unused; kept only so calibrate_camera.py write-back doesn't break)
CAMERA_WB_BLUE = 1.0998   # gray-world blue gain (LEGACY: unused, see above)
CAMERA_WB_TEMPERATURE = 4600   # 白平衡锁定色温(开尔文, 2800-6500)。该 UVC 摄像头无 red/blue gain 控件, 只能锁色温; 固定色温消除 AUTO WB 漂移(2026-08-29)


def detect_ae_off(cap, test_exposure):
    """Probe which V4L2 CAP_PROP_AUTO_EXPOSURE constant actually disables AE.

    OpenCV/V4L2 semantics differ by driver (commonly 0=manual/1=auto, but some use
    0.25=manual/0.75=auto, etc.). Rather than hardcode one value, try candidate
    constants and verify the EFFECT: in manual (AE off) mode the driver reports the
    exposure we set (responsive to our set); in auto mode it ignores our set and keeps
    its own value (unresponsive). Returns the working constant, or None if AE cannot
    be disabled on this driver.
    """
    candidates = [0, 0.25, 1, 0.75]
    # FIX 2026-08-27: do NOT derive the probe values from test_exposure. Some
    # V4L2 drivers silently CLAMP CAP_PROP_EXPOSURE to their max (e.g. 5000);
    # feeding test_exposure=8000 -> a=b=clamped -> |ra-rb|==0 -> false "not
    # responsive" -> we wrongly conclude AE cannot be disabled. Instead, discover
    # the real exposure ceiling by reading back a huge set, then probe with two
    # DISTINCT in-range values.
    try:
        cap.set(cv2.CAP_PROP_EXPOSURE, 1 << 30)
        max_exp = cap.get(cv2.CAP_PROP_EXPOSURE)
        if not max_exp or max_exp <= 1:
            max_exp = 5000
    except Exception:
        max_exp = 5000
    a = max(1, int(max_exp * 0.2))
    b = max(1, int(max_exp * 0.6))
    for ae in candidates:
        try:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, ae)
            cap.set(cv2.CAP_PROP_EXPOSURE, a)
            time.sleep(0.3)
            ra = cap.get(cv2.CAP_PROP_EXPOSURE)
            cap.set(cv2.CAP_PROP_EXPOSURE, b)
            time.sleep(0.3)
            rb = cap.get(cv2.CAP_PROP_EXPOSURE)
        except Exception:
            continue
        if ra is None or rb is None:
            continue
        # responsive => manual mode: reported exposure changed with our set
        if abs(ra - rb) > max(1.0, 0.05 * max(abs(ra), abs(rb))):
            # restore the (clamped) target exposure and report the working constant
            cap.set(cv2.CAP_PROP_EXPOSURE, max(1, min(int(test_exposure), int(max_exp))))
            return ae
    return None


def lock_wb_temperature(device='/dev/video0', temperature=4600):
    """Lock white balance by fixing white_balance_temperature via v4l2-ctl.

    This UVC cam exposes ONLY white_balance_temperature (+ its auto toggle) — no
    red_balance/blue_balance gain ctrls, so OpenCV's CAP_PROP_WHITE_BALANCE_RED_V/
    BLUE_V are no-ops (that's why the old code always fell back to AUTO WB, and WB
    drifted between calibrate_center runs -> CENTER drift).

    v4l2-ctl sets the control at device level, so it applies to the already-open
    cv2.VideoCapture fd. Returns True if the temperature is confirmed active & equal.
    """
    try:
        subprocess.run(
            ['v4l2-ctl', '-d', device, '--set-ctrl', 'white_balance_temperature_auto=0'],
            capture_output=True, timeout=15)
        subprocess.run(
            ['v4l2-ctl', '-d', device, '--set-ctrl', 'white_balance_temperature=%d' % int(temperature)],
            capture_output=True, timeout=15)
        r = subprocess.run(
            ['v4l2-ctl', '-d', device, '--list-ctrls'], capture_output=True, timeout=15)
        out = r.stdout.decode(errors='replace')
        for line in out.splitlines():
            if 'white_balance_temperature ' in line and 'temperature_auto' not in line:
                # active (no 'inactive' flag) and value matches -> locked
                if 'inactive' not in line and ('value=%d' % int(temperature)) in line:
                    return True
        return False
    except Exception:
        return False


class CameraBroadcaster:
    def __init__(self, camera_info):
        self.height = camera_info.get('height', 720)
        self.width = camera_info.get('width', 1280)
        self.fps = camera_info.get('fps', 30)
        self.stop_sign = Value(c_bool, False)
        self.frame = shared_memory.SharedMemory(create=True, size=np.zeros(shape=(self.height, self.width, 3),
                                                                           dtype=np.uint8).nbytes)
        self.memory_name = self.frame.name

    def run(self):
        cap = cv2.VideoCapture()
        cap.open(0, apiPreference=cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)

        # P0 (2026-08-26): lock exposure & white balance to kill light-sensitivity at source.
        # Only lock when calibrated (CAMERA_EXPOSURE > 0); otherwise keep auto-exposure so the car works.
        # V4L2 CAP_PROP_AUTO_EXPOSURE semantics vary by driver, so we PROBE the working
        # constant at runtime via detect_ae_off() instead of hardcoding 0.25/0/1/etc.
        if CAMERA_EXPOSURE > 0:
            ae = detect_ae_off(cap, CAMERA_EXPOSURE)
            if ae is not None:
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, ae)   # turn OFF auto exposure -> manual
                cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE)
                # White balance: this UVC cam has NO red/blue gain ctrls (old code below was a
                # silent no-op and always fell back to AUTO WB -> WB drifted -> CENTER drifted
                # between calibrate_center runs). Lock it by fixing color temperature via v4l2-ctl.
                if CAMERA_WB_TEMPERATURE > 0:
                    if lock_wb_temperature('/dev/video0', CAMERA_WB_TEMPERATURE):
                        log.info(f'WB locked: white_balance_temperature={CAMERA_WB_TEMPERATURE}K '
                                 f'(auto off, exposure stays locked).')
                    else:
                        log.warning('Could NOT lock WB temperature via v4l2-ctl; white balance '
                                    'may still drift (check device path / v4l2-ctl availability).')
                log.info(f'Camera exposure locked: AUTO_EXPOSURE={ae}, EXPOSURE={CAMERA_EXPOSURE}.')
            else:
                log.warning('Could NOT disable auto-exposure on this driver; running with auto '
                            'exposure (light-sensitivity may persist).')
        else:
            log.warning('CAMERA_EXPOSURE not calibrated (0); running with default auto exposure.')

        sender = np.ndarray((self.height, self.width, 3), dtype=np.uint8, buffer=self.frame.buf)

        try:
            while True:
                if self.stop_sign.value:
                    self.frame.close()
                    self.frame.unlink()
                    break
                start = datetime.now()
                ret, frame = cap.read()
                if not ret or frame is None:   # 防崩溃：读取失败时跳过本帧，避免 frame[:] 抛异常拖垮相机进程
                    time.sleep(0.01)
                    continue
                end1 = datetime.now()
                sender[:] = frame[:]
                end2 = datetime.now()
                log.debug(f'{self.memory_name}  read time: {end1 - start}, copy time: {end2 - end1}')
        except (KeyboardInterrupt, SystemExit):
            log.info('Cam broadcaster closing')
            self.frame.close()
            self.frame.unlink()
