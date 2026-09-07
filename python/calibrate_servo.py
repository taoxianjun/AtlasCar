#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# calibrate_servo.py  (v1.1, 2026-08-26)
#
# Purpose: find which servo channel (0 or 1) drives the camera LEFT/RIGHT, and
#   what angle makes it face straight ahead (front-center). Then write that
#   [ch0, ch1] pair back to lane_following.py:36 / manual.py / controller.reset().
#
# IMPORTANT: the original assumption "servo[0]=horizontal, servo[1]=vertical"
#   was WRONG on this car -- tuning servo[0] did NOT move the camera. The servo
#   index order may be REVERSED (real horizontal = servo[1]) or servo[0] is not
#   wired. So this tool lets you switch channels and tune either one.
#
# Run (must be inside python/, ESP32 serial present):
#   cd /home/HwHiAiUser/E2ESamples/src/E2E-Sample/Car/python
#   /usr/local/miniconda3/bin/python calibrate_servo.py            # GUI (display/ssh -X)
#   /usr/local/miniconda3/bin/python calibrate_servo.py --stream  # browser + terminal
#
# Keys:
#   GUI/stream : Left/Right or A/D tune CURRENT channel; W/S switch step(1/5/10);
#                C switch channel (0<->1); R reset to [90,65]; Enter print & exit
#
# Note: on exit, Controller.atexit resets servo to [90,65] -- EXPECTED. The tool
#   only READS angles; once written into code constants, LF uses correct values.
#   We pause 2s before exit so you can confirm the centered frame.
# =============================================================================
import argparse
import os
import sys
import time
import threading
import socket
import http.server
import termios
import tty

import cv2
import numpy as np
from multiprocessing import Process, shared_memory

from src.utils import CameraBroadcaster, CAMERA_INFO, log, Controller
from src.actions import SetServo

SERVO_DEFAULT = [90, 65]   # [ch0, ch1] initial; both 0..180
STOP = threading.Event()


def build_camera():
    camera = CameraBroadcaster(CAMERA_INFO)
    cam_proc = Process(target=camera.run)
    cam_proc.start()
    shm = shared_memory.SharedMemory(name=camera.memory_name)
    frame_view = np.ndarray(
        (CAMERA_INFO['height'], CAMERA_INFO['width'], 3),
        dtype=np.uint8, buffer=shm.buf)
    time.sleep(0.5)   # camera warm-up
    return camera, cam_proc, shm, frame_view


def _apply(ctrl, vals):
    ctrl.execute(SetServo(servo=[vals[0], vals[1]]))


def _handle(ch, vals, step, si, steps, delta):
    """Return (ch, vals, si, step) after applying a delta to the current channel."""
    if delta == 'ch':
        ch = 1 - ch
    elif delta == 'reset':
        vals[0], vals[1] = 90, 65
    elif delta == 'left':
        vals[ch] = max(0, vals[ch] - step)
    elif delta == 'right':
        vals[ch] = min(180, vals[ch] + step)
    elif delta == 'step_up':
        si = (si + 1) % len(steps)
        step = steps[si]
    elif delta == 'step_down':
        si = (si - 1) % len(steps)
        step = steps[si]
    return ch, vals, si, step


def _status(ch, vals, step):
    return f'ch={ch} vals=[{vals[0]},{vals[1]}] step={step}'


def gui_mode(camera, cam_proc, shm, frame_view, ctrl):
    vals = [90, 65]
    ch = 0
    steps = [1, 5, 10]
    si, step = 0, steps[0]
    _apply(ctrl, vals)
    print('[calibrate_servo] GUI: A/D or <-/-> tune CURRENT ch; W/S step; C switch ch; R reset; Enter exit')
    print('[calibrate_servo] NOTE: if tuning ch0 does not move camera left/right, press C to try ch1 (index may be reversed)')
    try:
        while True:
            cv2.imshow('calibrate_servo', frame_view)
            k = cv2.waitKey(30)
            if k == -1:
                continue
            if k in (13, 10, 27):   # Enter / Esc
                break
            if k in (ord('r'), ord('R')):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'reset')
            elif k in (ord('c'), ord('C')):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'ch')
            elif k in (ord('a'), ord('A')):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'left')
            elif k in (ord('d'), ord('D')):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'right')
            elif k in (ord('w'), ord('W')):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'step_up')
            elif k in (ord('s'), ord('S')):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'step_down')
            else:
                code = (k >> 8) & 0xFF
                if code == 81:       # Left
                    ch, vals, si, step = _handle(ch, vals, step, si, steps, 'left')
                elif code == 83:     # Right
                    ch, vals, si, step = _handle(ch, vals, step, si, steps, 'right')
                elif code == 82:     # Up
                    ch, vals, si, step = _handle(ch, vals, step, si, steps, 'step_up')
                elif code == 84:     # Down
                    ch, vals, si, step = _handle(ch, vals, step, si, steps, 'step_down')
                else:
                    continue
            _apply(ctrl, vals)
            print(_status(ch, vals, step), flush=True)
    except KeyboardInterrupt:
        pass
    return vals


def stream_mode(camera, cam_proc, shm, frame_view, ctrl):
    latest = {'jpeg': None}
    lock = threading.Lock()

    def cam_thread():
        while not STOP.is_set():
            ret, buf = cv2.imencode('.jpg', frame_view)
            if ret:
                with lock:
                    latest['jpeg'] = buf.tobytes()
            time.sleep(0.03)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while not STOP.is_set():
                    with lock:
                        jpg = latest['jpeg']
                    if jpg:
                        self.wfile.write(b'--FRAME\r\n')
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Content-Length', str(len(jpg)))
                        self.end_headers()
                        self.wfile.write(jpg)
                        self.wfile.write(b'\r\n')
                    time.sleep(0.03)
            except Exception:
                pass

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(('0.0.0.0', 8080), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    threading.Thread(target=cam_thread, daemon=True).start()

    vals = [90, 65]
    ch = 0
    steps = [1, 5, 10]
    si, step = 0, steps[0]
    _apply(ctrl, vals)
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = '<DK_IP>'
    print(f'[calibrate_servo] Open browser: http://{ip}:8080/  (use DK LAN IP if shown wrong)')
    print('[calibrate_servo] terminal: A/D tune ch; W/S step; C switch ch; R reset; Enter exit')
    print('[calibrate_servo] NOTE: if ch0 does not move camera left/right, press C to try ch1 (index may be reversed)')

    old = termios.tcgetattr(sys.stdin)
    tty.setraw(sys.stdin.fileno())
    try:
        while True:
            ch_in = sys.stdin.read(1)
            if ch_in in ('\r', '\n'):
                break
            if ch_in == '\x03':   # Ctrl-C
                break
            if ch_in == '\x1b':   # arrow ESC sequence
                nxt = sys.stdin.read(2)
                if nxt == '[D':
                    ch, vals, si, step = _handle(ch, vals, step, si, steps, 'left')
                elif nxt == '[C':
                    ch, vals, si, step = _handle(ch, vals, step, si, steps, 'right')
                elif nxt == '[A':
                    ch, vals, si, step = _handle(ch, vals, step, si, steps, 'step_up')
                elif nxt == '[B':
                    ch, vals, si, step = _handle(ch, vals, step, si, steps, 'step_down')
                else:
                    continue
            elif ch_in in ('a', 'A'):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'left')
            elif ch_in in ('d', 'D'):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'right')
            elif ch_in in ('w', 'W'):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'step_up')
            elif ch_in in ('s', 'S'):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'step_down')
            elif ch_in in ('c', 'C'):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'ch')
            elif ch_in in ('r', 'R'):
                ch, vals, si, step = _handle(ch, vals, step, si, steps, 'reset')
            else:
                continue
            _apply(ctrl, vals)
            print(f'\r{_status(ch, vals, step)}', end='', flush=True)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
    return vals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stream', action='store_true',
                        help='headless mode: HTTP MJPEG stream + terminal keys')
    args = parser.parse_args()

    camera, cam_proc, shm, frame_view = build_camera()
    ctrl = Controller()

    vals = [90, 65]
    try:
        if args.stream:
            vals = stream_mode(camera, cam_proc, shm, frame_view, ctrl)
        else:
            try:
                cv2.namedWindow('__probe__')
                cv2.destroyWindow('__probe__')
                vals = gui_mode(camera, cam_proc, shm, frame_view, ctrl)
            except cv2.error:
                print('[warn] no GUI backend (no display / no X11); switching to --stream mode')
                vals = stream_mode(camera, cam_proc, shm, frame_view, ctrl)
    finally:
        print(f'\n>>> final vals = [{vals[0]},{vals[1]}]')
        print('>>> Identify which channel (0 or 1) drives camera LEFT/RIGHT. The value of THAT')
        print('>>> channel when the camera faces straight ahead is your front-center angle.')
        print('>>> Then tell me, e.g. "ch1 is horizontal, front-center = 95" and I will patch')
        print('>>> lane_following.py:36 / manual.py / controller.reset() to [val0, val1].')
        try:
            with open(os.path.join(os.getcwd(), 'servo_center.txt'), 'w') as f:
                f.write(f'{vals[0]},{vals[1]}')
        except Exception:
            pass
        time.sleep(2)
        try:
            camera.stop_sign.value = True
            cam_proc.join(timeout=5)
            if cam_proc.is_alive():
                cam_proc.kill()
        except Exception:
            pass
        try:
            shm.close()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        print('[calibrate_servo] done.')


if __name__ == '__main__':
    main()
