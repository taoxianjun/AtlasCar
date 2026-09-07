# -*- coding: utf-8 -*-
"""
carControl.py使用说明：
========
import carControl
1.速度设置 speed(value: 'str|int')
    设置速度为 0~100的任意数值：carControl.speed(50)
    加速（v+10）：carControl.speed('up')
    减速(v-10)：carControl.speed('down')
    注意：小车电机有起始转速，不同场地因摩擦力不同最低启动速度也不同，第一版道路场景中 直行的启动速度为>=32，左平移则>=46

2.方向控制 move(value, degree=0)
    moveList = ['ADVANCE', #前进
                'BACK', #后退
                'STOP', #停车
                'LEFT_TRAN', #左平移
                'RIGHT_TRAN', #右平移
                'CLOCKWISE', #顺时针旋转
                'ANTICLOCKWISE', #逆时针旋转
                'LEFT_OBLIQUE', #左斜45°前移
                'RIGHT_OBLIQUE'] #右斜45°前移
    简单的方向控制：carControl.move(value in moveList)
    左右转向需加上转角幅度 degree：carControl.move('LEFT'/'RIGHT', 0.5)
    degree代表转向幅度，取值0~2，数值与转向幅度成正比

3.舵机控制 servo(d1, d2)
    d1、d2为两个舵机转角，0~180: carControl.servo(90, 90)
    d1为相机垂直方向的角度，d1=90°约为水平；d2为相机水平方向的角度，d2=90°为正前方
    小车摄像头平视前方为[90，90]，道路循迹行驶合适的视角为[110, 90]

4、超声波测距 check_distance()，将返回超声波模块正前方第一个障碍物的距离值，可测范围5~500，单位cm
    carControl.check_distance()

5、小车执行连续的两个命令的时间间隔约为0.08s，可连续发送指令，无需再设置等待时间.
"""
import json
import serial

# 初始化默认串口信息
speedInfo = {'speed': [-100, -100]}
moveInfo = {'carmove': ['RELEX', 0]}
servoInfo = {'servo': [-1, -1]}
checkDistanceInfo = {'checkdistance': 0}

ser = serial.Serial('/dev/ttyAMA1', 115200)  # A200 DK与小车间的接口定义
# ser = serial.Serial('COM5',115200)  # windos串口设置


# 串口发送Json数据
def send_data_to_serial():
    # 将所有数据打包成Json格式
    data = dict(
        list(speedInfo.items()) + list(moveInfo.items()) + list(servoInfo.items()) + list(checkDistanceInfo.items()))
    json_data = json.dumps(data)
    ser.write(json_data.encode())  # 将Json格式的数据发送至串口


def speed(value: 'str|int'):
    if value == 'up':
        speedInfo['speed'] = [1, 10]
    elif value == 'down':
        speedInfo['speed'] = [-1, 10]
    else:
        speedInfo['speed'] = [0, value]
    send_data_to_serial()
    return read_serial()


def move(value, degree=0):
    moveList = ['ADVANCE', 'BACK', 'STOP', 'LEFT_TRAN', 'RIGHT_TRAN', 'CLOCKWISE', 'ANTICLOCKWISE', 'LEFT_OBLIQUE',
                'RIGHT_OBLIQUE']
    if value in moveList:
        moveInfo['carmove'] = [value, 0]
    elif value in ['LEFT', 'RIGHT'] and 0 < degree <= 2:
        moveInfo['carmove'] = [value, degree]
    send_data_to_serial()
    return read_serial()


def servo(d1, d2):
    if 0 <= d1 <= 180 and 0 <= d2 <= 180:
        servoInfo['servo'] = [d1, d2]
    send_data_to_serial()
    return read_serial()


def check_distance():
    checkDistanceInfo['checkdistance'] = 1
    send_data_to_serial()
    # 获取串口返回的distance值
    distance = read_serial("distance")
    return distance


# 读取串口返回信息
def read_serial(kind="speed"):
    data = json.loads(ser.readline())
    if kind == "distance":
        return data["distance"]
    else:
        return data["speed"]  # 默认返回speed
