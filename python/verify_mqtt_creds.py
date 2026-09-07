#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MQTT 接入自检脚本（不依赖小车其他模块，单独可跑）。

用途：在开发者套件上运行，验证三件事
  1. 凭据是否与华为云 IoTDA 一致（支持两种模式：
        - password 直连：直接复用控制台「MQTT连接参数」里的静态密码
        - secret 动态：用 secret + 当前时间戳按 HMAC-SHA256 生成）
  2. 到 IoTDA 端点的 TCP 网络是否可达
  3. 用生成的凭据能否真正完成 MQTT CONNECT（打印 rc 返回码）

运行方式（在开发者套件 /home/car/python 目录下）：
  python3 verify_mqtt_creds.py                 # 读 cloud_config.json
  python3 verify_mqtt_creds.py --config x.json # 指定配置文件
  IOT_DEVICE_ID=xxx IOT_PASSWORD=yyy python3 verify_mqtt_creds.py  # 用环境变量

拿到打印出的 client_id / username / password 后，可与华为云控制台
「设备详情 → MQTT连接参数」里的值逐字对比；一致则算法无误。
"""
import argparse
import hashlib
import hmac
import json
import os
import socket
import ssl
import sys
import time


def load_config(path):
    config = {
        'device_id': '',
        'secret': '',
        'password': '',
        'client_id': '',
        'host': 'iot-mqtts.cn-north-4.myhuaweicloud.com',
        'port': 1883,
        'ca_cert': '',
        'sign_type': 0,
    }
    if path and os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            config.update(json.load(f))
    # 环境变量优先
    for key, env in (('device_id', 'IOT_DEVICE_ID'),
                     ('secret', 'IOT_DEVICE_SECRET'),
                     ('password', 'IOT_PASSWORD'),
                     ('client_id', 'IOT_CLIENT_ID'),
                     ('host', 'IOT_SERVER'),
                     ('port', 'IOT_PORT'),
                     ('ca_cert', 'IOT_CA_CERT')):
        if os.environ.get(env):
            config[key] = os.environ[env]
    return config


def build_credentials(device_id, secret, sign_type):
    """用 secret 动态生成（与 iot_client.py 一致）。"""
    timestamp = time.strftime('%Y%m%d%H', time.gmtime())
    client_id = f'{device_id}_0_{sign_type}_{timestamp}'
    password = hmac.new(timestamp.encode('utf-8'),
                        secret.encode('utf-8'),
                        digestmod=hashlib.sha256).hexdigest()
    return client_id, device_id, password, timestamp


def resolve_credentials(device_id, secret, password, client_id, sign_type):
    """与 iot_client.py 完全一致的凭据解析：优先用直接提供的 password。

    重要：华为云静态 password 是用 clientId 中的时间戳算出的
    HMAC-SHA256(timestamp, secret)，因此 password 必须与 clientId 时间戳同源。
    使用静态 password 时务必同时配置配套的 client_id（来自控制台 MQTT 连接参数），
    否则代码用当前时间生成 clientId，会导致时间戳错位、平台校验 rc=4。
    """
    ts = time.strftime('%Y%m%d%H', time.gmtime())
    if password:
        cid = client_id or f'{device_id}_0_{sign_type}_{ts}'
        if not client_id:
            print('  [警告] 使用静态 password 但未配置 client_id，'
                  'clientId 将用当前时间生成，可能与 password 时间戳不一致导致 rc=4！')
        return cid, device_id, password, ts, '静态 password（直接复用控制台）'
    if secret:
        cid, username, pw = build_credentials(device_id, secret, sign_type)
        if client_id:
            cid = client_id
        return cid, username, pw, ts, '动态计算（secret + 时间戳）'
    raise ValueError('secret 与 password 至少提供一个')


def test_tcp(host, port, timeout=5):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, ''
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _rc_value(rc):
    """兼容 paho 1.x 的 int rc 与 2.x 的 ReasonCode 对象。"""
    try:
        return int(rc)
    except Exception:
        return rc


def test_mqtt(host, port, client_id, username, password, ca_cert):
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return 'SKIP', 'paho-mqtt 未安装，跳过真实连接测试（请先 pip install paho-mqtt）'

    paho_major = int(getattr(mqtt, '__version__', '1.0.0').split('.')[0])
    if paho_major >= 2:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=client_id, protocol=mqtt.MQTTv311)
    else:
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

    client.username_pw_set(username, password)
    if ca_cert:
        client.tls_set(ca_certs=ca_cert, cert_reqs=ssl.CERT_REQUIRED,
                       tls_version=ssl.PROTOCOL_TLSv1_2)
    elif int(port) == 8883:
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)

    result = {'rc': None}

    def on_connect(c, u, f, rc, *args):
        result['rc'] = _rc_value(rc)
        c.disconnect()

    client.on_connect = on_connect
    try:
        client.connect(host, int(port), keepalive=120)
        client.loop_start()
        for _ in range(80):  # 最多等 8s（TLS 握手较慢）
            if result['rc'] is not None:
                break
            time.sleep(0.1)
        client.loop_stop()
    except Exception as exc:  # noqa: BLE001
        return 'ERR', str(exc)

    rc = result['rc']
    if rc is None:
        return 'TIMEOUT', '连接未在 8s 内返回结果（可能网络不通或被防火墙拦截）'
    meanings = {
        0: '连接成功',
        1: '协议版本错误',
        2: 'clientId 格式错误',
        3: '服务器不可用',
        4: '用户名或密码错误（device_id/secret/算法有误，或静态 password 已过期）',
        5: '未授权',
    }
    return rc, meanings.get(rc, f'未知返回码 {rc}')


def main():
    ap = argparse.ArgumentParser(description='MQTT 凭据与连通性自检')
    ap.add_argument('--config', default='cloud_config.json', help='配置文件路径')
    args = ap.parse_args()

    cfg = load_config(args.config)
    dev, sec, pw, cid_cfg, host, port, ca, sign = (
        cfg.get('device_id', ''), cfg.get('secret', ''),
        cfg.get('password', ''), cfg.get('client_id', ''),
        cfg.get('host', ''), int(cfg.get('port', 1883)),
        cfg.get('ca_cert', ''), int(cfg.get('sign_type', 0)),
    )

    print('=' * 60)
    print('1) 配置检查')
    print('=' * 60)
    if not dev or not (sec or pw):
        print('[FAIL] device_id / (secret 或 password) 为空，请填写 cloud_config.json '
              '或设置 IOT_DEVICE_ID / IOT_DEVICE_SECRET / IOT_PASSWORD')
        return 1
    print(f'  host      = {host}')
    print(f'  port      = {port}')
    print(f'  sign_type = {sign}')
    print(f'  ca_cert   = {ca or "(空，使用系统默认 CA 或 8883 内置 TLS)"}')
    print(f'  鉴权模式  = {"静态 password" if pw else "动态 secret"}')

    print()
    print('=' * 60)
    print('2) 凭据生成（请与华为云控制台「MQTT连接参数」逐字对比）')
    print('=' * 60)
    try:
        client_id, username, password, ts, mode = resolve_credentials(dev, sec, pw, cid_cfg, sign)
    except ValueError as exc:
        print(f'  [FAIL] {exc}')
        return 1
    print(f'  生成方式  = {mode}')
    print(f'  时间戳    = {ts}  (UTC, YYYYMMDDHH)')
    print(f'  ClientId  = {client_id}')
    print(f'  Username  = {username}')
    print(f'  Password  = {password}')
    print(f'  Password 长度 = {len(password)}')
    print(f'  Password 前16字节(hex) = {password[:16].encode("utf-8").hex()}')

    print()
    print('=' * 60)
    print('3) TCP 网络连通性测试')
    print('=' * 60)
    ok, err = test_tcp(host, port)
    if ok:
        print(f'  [OK] 能 TCP 连接到 {host}:{port}')
    else:
        print(f'  [FAIL] 无法连接 {host}:{port} -> {err}')
        print('         检查：DK 是否能上外网 / DNS 是否能解析 / 防火墙是否放行')

    print()
    print('=' * 60)
    print('4) MQTT CONNECT 真实连接测试')
    print('=' * 60)
    rc, msg = test_mqtt(host, port, client_id, username, password, ca)
    if rc == 0:
        print(f'  [OK] MQTT 连接成功：{msg}')
    elif rc == 'SKIP':
        print(f'  [SKIP] {msg}')
    else:
        print(f'  [结果 {rc}] {msg}')

    print()
    print('=' * 60)
    if rc == 0 and ok:
        print('结论：凭据算法正确 + 网络可达 + MQTT 可连接，正式运行 main.py --mode mqtt 即可上线。')
    elif rc == 0 or ok:
        print('结论：部分通过，请按上面 [FAIL] 项逐一排查。')
    else:
        print('结论：未通过。先确保 TCP 可达，再核对 device_id/password 与控制台一致。')

    if rc == 4:
        print()
        print('!!! rc=4 排查建议（按概率排序）：')
        print('  1) 华为云控制台 → 设备详情 → MQTT连接参数 → 重新生成静态密码，')
        print('     把新的 password 更新到 DK 的 cloud_config.json 中再试。')
        print('  2) 检查本机/其他机器是否还在占用该设备的同一个 MQTT 连接；')
        print('     同一设备同一时间通常只能有一个在线连接。')
        print('  3) 确认 cloud_config.json 中 password 没有换行/空格/截断（看上面的长度和 hex）。')
    print('=' * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
