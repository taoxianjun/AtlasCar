#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from argparse import ArgumentParser
from multiprocessing import Process, Queue

from src.scenes import Manual, scene_initiator
from src.utils import getkey, log, CameraBroadcaster, CAMERA_INFO, Controller
from src.actions import Stop


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--mode', type=str, required=False, default='manual',
                        choices=['cmd', 'voice', 'manual', 'easy', 'mqtt'])
    parser.add_argument('--cloud-config', type=str, required=False, default=None,
                        help='云端接入配置文件路径，默认读取工作目录下的 cloud_config.json')

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    log.info('start')
    ctrl = Controller()
    msg_queue = Queue(maxsize=1)
    camera = CameraBroadcaster(CAMERA_INFO)
    shared_memory_name = camera.memory_name
    camera_process = Process(target=camera.run)
    camera_process.start()
    if args.mode == 'manual':
        task = Manual(shared_memory_name, CAMERA_INFO, msg_queue)
        process = Process(target=task.loop)
        process.start()
        try:
            while True:
                key = getkey()
                if key == 'esc':
                    process.join()
                    camera.stop_sign.value = True
                    camera_process.join()
                    break
                else:
                    msg_queue.put(key)
        except (KeyboardInterrupt, SystemExit):
            camera.stop_sign.value = True
            camera_process.join()
            os.system('stty sane')
            log.info('stopping.')
    elif args.mode == 'cmd':
        process_list = []
        record_map = {}
        try:
            log.info(f'start reading cmd')
            while True:
                command = input().strip()
                if command == 'stop':
                    for p in process_list:
                        p.kill()
                    log.info(f'start put stop sign')
                    ctrl.execute(Stop())
                    camera.stop_sign.value = True
                    camera_process.join()
                    break
                elif command == 'clear':
                    for p in process_list:
                        p.kill()
                    process_list.clear()
                    ctrl.execute(Stop())
                    log.info(f'clear succ')
                    continue
                elif command == 'Manual':
                    log.error(f'Does not support switching from cmd mode to manual mode')
                    continue
                log.info(f'building scene {command}')
                scene = scene_initiator(command)
                log.info(f'{scene}')
                if scene is not None:
                    scene_obj = scene(shared_memory_name, CAMERA_INFO, msg_queue)
                    process = Process(target=scene_obj.loop)
                    process.start()
                    process_list.append(process)

        except (KeyboardInterrupt, SystemExit):
            camera.stop_sign.value = True
            camera_process.join()
            for process in process_list:
                process.kill()
            log.info('stopping.')

    elif args.mode == 'mqtt':
        from src.cloud_control import CloudControl, load_config

        cloud = CloudControl(shared_memory_name, CAMERA_INFO, msg_queue, ctrl,
                             load_config(args.cloud_config))
        cloud.client.connect()
        try:
            cloud.run_forever()
        except (KeyboardInterrupt, SystemExit):
            cloud.shutdown()
        finally:
            ctrl.execute(Stop())
            camera.stop_sign.value = True
            camera_process.join()
            log.info('stopping.')

    elif args.mode == 'voice':
        raise NotImplementedError('voice control is not currently supported.')
    elif args.mode == 'easy':
        process_list = []
        task1 = scene_initiator('Helper')(shared_memory_name, CAMERA_INFO, msg_queue)
        process_list.append(Process(target=task1.loop))
        task2 = scene_initiator('LF')(shared_memory_name, CAMERA_INFO, msg_queue)
        process_list.append(Process(target=task2.loop))

        for process in process_list:
            process.start()
        try:
            while True:
                key = getkey()
                if key == 'esc':
                    for process in process_list:
                        process.kill()
                    ctrl.execute(Stop())
                    camera.stop_sign.value = True
                    camera_process.join()
                    break
                else:
                    msg_queue.put(key)
        except (KeyboardInterrupt, SystemExit):
            camera.stop_sign.value = True
            camera_process.join()
            os.system('stty sane')
            log.info('stopping.')
