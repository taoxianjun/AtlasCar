#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""华为云 IoTDA 设备侧 MQTT 客户端。

鉴权规则（一机一密）：
    ClientId = {device_id}_0_{sign_type}_{timestamp}
    Username = {device_id}
    Password = HMAC-SHA256(key=timestamp, msg=device_secret) 的十六进制串
其中 timestamp 为 UTC 时间，格式 YYYYMMDDHH；sign_type 为 0 表示不校验时间戳，
1 表示校验（设备时钟与平台偏差需在允许范围内）。
"""

import hashlib
import hmac
import json
import ssl
import time

import paho.mqtt.client as mqtt

# paho-mqtt 2.x 与 1.x 差异较大：2.x 要求 CallbackAPIVersion，回调签名也不同。
# 这里自动检测版本，统一按 2.x 原生 API（VERSION2）工作，1.x 时回退旧签名。
def _detect_paho_major():
    """探测 paho-mqtt 主版本号。

    ⚠️ 不能直接读 ``mqtt.__version__``：``paho.mqtt.client`` 模块本身**没有**
    ``__version__`` 属性（版本在 ``paho.mqtt`` 包上），getattr 会永远拿默认值
    '1.0.0'，导致 2.x 环境下静默退回已废弃的 VERSION1 兼容层
    （实测 paho 2.1.0 会打 DeprecationWarning: Callback API version 1 is deprecated）。
    因此这里以「能力探测」为主：2.x 才引入 CallbackAPIVersion。
    """
    if hasattr(mqtt, 'CallbackAPIVersion'):
        return 2
    try:
        from importlib.metadata import version as _pkg_version
        return int(_pkg_version('paho-mqtt').split('.')[0])
    except Exception:
        import paho.mqtt as _paho_mqtt
        return int(getattr(_paho_mqtt, '__version__', '1.0.0').split('.')[0])


PAHO_MAJOR = _detect_paho_major()


try:
    from src.utils.logger import logger_instance as log
except Exception:
    # 降级：运行环境缺少 CANN/acl（如本地调试、或 CANN 异常）时，
    # MQTT 连接能力不应被日志模块拖垮，使用标准库 logging 兜底。
    import logging
    log = logging.getLogger('iot_client')
    if not log.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        log.addHandler(_h)
    log.setLevel(logging.INFO)

# IoTDA 系统预置 Topic
TOPIC_COMMAND_SUB = '$oc/devices/{device_id}/sys/commands/#'
TOPIC_COMMAND_RESP = '$oc/devices/{device_id}/sys/commands/response/request_id={request_id}'
TOPIC_MESSAGE_DOWN = '$oc/devices/{device_id}/sys/messages/down'
TOPIC_MESSAGE_UP = '$oc/devices/{device_id}/sys/messages/up'
TOPIC_PROPERTIES_REPORT = '$oc/devices/{device_id}/sys/properties/report'


class IoTDAClient:
    """与华为云 IoTDA 保持长连接，接收命令并上报状态。"""

    def __init__(self, device_id, host, secret=None,
                 port=1883, ca_cert=None, sign_type=0, keepalive=120,
                 password=None, client_id=None):
        self.device_id = device_id
        self.secret = secret
        self.host = host
        self.port = int(port)
        self.ca_cert = ca_cert
        self.sign_type = int(sign_type)
        self.keepalive = int(keepalive)

        # 由使用方注册：command_handler(command_name, paras) -> (result_code, paras)
        self.command_handler = None
        self.connected = False

        # 命令去重：华为云 IoTDA 在收不到「完成响应」时会重发同一条命令
        # （通常最多数次）。同一 request_id 视为同一条命令，重复投递只执行一次，
        # 避免如 capture 连拍被放大 N 倍。保留窗口 30s，过期记录自动清理。
        self._seen_requests = {}  # request_id -> (timestamp, result_code, resp_paras, command_name)

        # 鉴权凭据两种来源：
        #  1) 直接复用控制台生成的静态 password（一机一密，sign_type=0 不校验时间戳，长期有效）
        #  2) 否则用 secret 按 HMAC-SHA256(timestamp, secret) 动态生成
        if password:
            username = device_id
            # sign_type=0 时不校验时间戳，client_id 内的时间戳填文档值或当前时间均可
            resolved_client_id = client_id or f'{device_id}_0_{self.sign_type}_{time.strftime("%Y%m%d%H", time.gmtime())}'
            resolved_password = password
        elif secret:
            resolved_client_id, username, resolved_password = self._build_credentials()
            if client_id:
                resolved_client_id = client_id
        else:
            raise ValueError('secret 与 password 至少需提供一个'
                             '（建议填 password，直接复用控制台「MQTT连接参数」里的静态密码）')

        self._client = self._new_client(resolved_client_id)
        self._client.username_pw_set(username, resolved_password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        # 断线后按 1s -> 32s 退避重连，保证车在弱网下能自愈
        self._client.reconnect_delay_set(min_delay=1, max_delay=32)

        if self.ca_cert:
            self._client.tls_set(ca_certs=self.ca_cert, cert_reqs=ssl.CERT_REQUIRED,
                                 tls_version=ssl.PROTOCOL_TLSv1_2)
        elif self.port == 8883:
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)

    def _build_credentials(self):
        timestamp = time.strftime('%Y%m%d%H', time.gmtime())
        client_id = f'{self.device_id}_0_{self.sign_type}_{timestamp}'
        password = hmac.new(timestamp.encode('utf-8'),
                            self.secret.encode('utf-8'),
                            digestmod=hashlib.sha256).hexdigest()
        return client_id, self.device_id, password

    @staticmethod
    def _new_client(client_id):
        # 优先使用 paho-mqtt 2.x 原生 API（VERSION2），避免 VERSION1 兼容层
        # 在 2.x 下可能引发认证/回调异常；1.x 无该参数则回退旧构造函数。
        if PAHO_MAJOR >= 2:
            return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                               client_id=client_id, protocol=mqtt.MQTTv311)
        return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

    def connect(self):
        # 用异步连接，配合 loop_forever(retry_first_connection=True)，
        # 这样小车开机时即使 WiFi 还没就绪也能自动重试而不是直接退出
        log.info(f'connecting to IoTDA {self.host}:{self.port} as {self.device_id}')
        self._client.connect_async(self.host, self.port, self.keepalive)

    def loop_start(self):
        self._client.loop_start()

    def loop_forever(self):
        self._client.loop_forever(retry_first_connection=True)

    def stop(self):
        try:
            self._client.disconnect()
        finally:
            self._client.loop_stop()

    def report_properties(self, service_id, properties):
        """上报设备属性，可在控制台/应用侧查看小车实时状态。"""
        payload = {
            'services': [{
                'service_id': service_id,
                'properties': properties,
                'event_time': time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
            }]
        }
        self._publish(TOPIC_PROPERTIES_REPORT.format(device_id=self.device_id), payload)

    def report_message(self, content):
        self._publish(TOPIC_MESSAGE_UP.format(device_id=self.device_id), content)

    def _publish(self, topic, payload, qos=0):
        if not self.connected:
            return
        try:
            self._client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=qos)
        except Exception as exc:
            log.warn(f'publish to {topic} failed: {exc}')

    @staticmethod
    def _rc_value(rc):
        """兼容 paho 1.x 的 int rc 与 2.x 的 ReasonCode 对象。"""
        try:
            return int(rc)
        except Exception:
            return rc

    def _on_connect(self, client, userdata, flags, rc, *args):
        rc = self._rc_value(rc)
        if rc != 0:
            # rc=4 用户名或密码错误，rc=5 未授权，通常是设备ID/密钥/时间戳不匹配
            log.error(f'IoTDA connect failed, rc={rc}')
            return
        self.connected = True
        # 订阅失败必须显式检查：权限/topic 非法时若静默忽略，小车将永远收不到命令
        rc1, _ = client.subscribe(TOPIC_COMMAND_SUB.format(device_id=self.device_id), qos=1)
        rc2, _ = client.subscribe(TOPIC_MESSAGE_DOWN.format(device_id=self.device_id), qos=1)
        if rc1 != 0 or rc2 != 0:
            log.error(f'subscribe failed: command_sub_rc={rc1}, message_down_rc={rc2}')
        else:
            log.info('IoTDA connected, command topic subscribed')

    def _on_disconnect(self, client, userdata, *args):
        # 回调签名跨版本不一致，按位置硬解会错位：
        #   1.x (VERSION1 兼容层): (rc)
        #   2.x (VERSION2)       : (flags, rc, properties)
        if PAHO_MAJOR >= 2 and len(args) >= 2:
            rc = args[1]
        elif args:
            rc = args[0]
        else:
            rc = 0
        self.connected = False
        log.warn(f'IoTDA disconnected, rc={self._rc_value(rc)}')

    def _on_message(self, client, userdata, msg, *args):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.error(f'invalid payload on {msg.topic}: {exc}')
            return

        log.info(f'recv {msg.topic} -> {payload}')
        request_id = self._parse_request_id(msg.topic)

        # ---- 命令去重（应对平台重发）----
        if request_id:
            now = time.time()
            # 清理 30s 前的记录，避免无限增长
            self._seen_requests = {k: v for k, v in self._seen_requests.items()
                                   if now - v[0] < 30}
            if request_id in self._seen_requests:
                _ts, rc0, rp0, cn0 = self._seen_requests[request_id]
                log.warn(f'duplicate command redelivery, skip execute: '
                         f'{payload.get("command_name", "")} request_id={request_id}')
                # 仍回响应，让平台结束重试（不重执行，避免 capture 等被放大 N 倍）
                self._publish(
                    TOPIC_COMMAND_RESP.format(device_id=self.device_id, request_id=request_id),
                    {'result_code': rc0, 'response_name': cn0, 'paras': rp0},
                    qos=1,
                )
                return

        if self.command_handler is None:
            return
        try:
            command_name = payload.get('command_name', '')
            paras = payload.get('paras', {}) or {}
            result_code, resp_paras = self.command_handler(command_name, paras)
        except Exception as exc:
            log.error(f'command handler error: {exc}')
            result_code, command_name, resp_paras = 1, payload.get('command_name', ''), {'error': str(exc)}

        # 只有命令下发（带 request_id）才需要回响应，消息下发不需要。
        # 响应用 qos=1：避免丢包导致云端重发命令、小车重复执行动作。
        if request_id:
            self._publish(
                TOPIC_COMMAND_RESP.format(device_id=self.device_id, request_id=request_id),
                {'result_code': result_code, 'response_name': command_name, 'paras': resp_paras},
                qos=1,
            )
            # 记录本次结果，供平台重发时直接复用响应、且不重复执行
            self._seen_requests[request_id] = (time.time(), result_code, resp_paras, command_name)

    @staticmethod
    def _parse_request_id(topic):
        flag = 'request_id='
        idx = topic.find(flag)
        if idx < 0:
            return ''
        return topic[idx + len(flag):]
