#include <RL_ESP32_Motor.h>
#include <ESP32_Servo.h>
#include <HardwareSerial.h>
#include <ArduinoJson.h>


// 定义电机引脚
Motor Esp32_Motor_1(1,12,13);
Motor Esp32_Motor_2(2,14,15);
Motor Esp32_Motor_3(3,16,17);
Motor Esp32_Motor_4(4,18,19);

// 创建舵机实例
Servo servo_25;
Servo servo_26;

//定义超声波测距引脚
const int trigPin = 4;
const int echoPin = 5;

float distance;
int speed;

// 小车前进
void advance(int speed = speed) {
  Esp32_Motor_1.Motor_Speed(speed);
  Esp32_Motor_2.Motor_Speed(speed);
  Esp32_Motor_3.Motor_Speed((-speed));
  Esp32_Motor_4.Motor_Speed((-speed));
}


// 小车后退
void back(int speed = speed) {
  Esp32_Motor_1.Motor_Speed((-speed));
  Esp32_Motor_2.Motor_Speed((-speed));
  Esp32_Motor_3.Motor_Speed(speed);
  Esp32_Motor_4.Motor_Speed(speed);
}

// 小车停止
void stop() {
  Esp32_Motor_1.Motor_Speed(0);
  Esp32_Motor_2.Motor_Speed(0);
  Esp32_Motor_3.Motor_Speed(0);
  Esp32_Motor_4.Motor_Speed(0);
}


// 小车左转
void left(int speed = speed, float degree = 0.25) {
  Esp32_Motor_1.Motor_Speed(speed);
  Esp32_Motor_2.Motor_Speed(speed);
  Esp32_Motor_3.Motor_Speed((-speed * (1 + degree)));
  Esp32_Motor_4.Motor_Speed((-speed * (1 + degree)));
}

// 小车右转
void right(int speed = speed, float degree = 0.25) {
  Esp32_Motor_1.Motor_Speed(speed * (1 + degree));
  Esp32_Motor_2.Motor_Speed(speed * (1 + degree));
  Esp32_Motor_3.Motor_Speed((-speed));
  Esp32_Motor_4.Motor_Speed((-speed));
}

// 逆时针旋转
void anticlockwise(int speed = speed) {
  Esp32_Motor_1.Motor_Speed((-speed));
  Esp32_Motor_2.Motor_Speed((-speed));
  Esp32_Motor_3.Motor_Speed((-speed));
  Esp32_Motor_4.Motor_Speed((-speed));
}

// 顺时针旋转
void clockwise(int speed = speed) {
  Esp32_Motor_1.Motor_Speed((speed));
  Esp32_Motor_2.Motor_Speed((speed));
  Esp32_Motor_3.Motor_Speed((speed));
  Esp32_Motor_4.Motor_Speed((speed));
}

// 向左平移
void left_tran(int speed = speed) {
  Esp32_Motor_1.Motor_Speed((-speed));
  Esp32_Motor_2.Motor_Speed((speed));
  Esp32_Motor_3.Motor_Speed((speed));
  Esp32_Motor_4.Motor_Speed((-speed));
}

// 斜向左前方
void left_oblique(int speed = speed) {
  Esp32_Motor_1.Motor_Speed(0);
  Esp32_Motor_2.Motor_Speed((speed));
  Esp32_Motor_3.Motor_Speed(0);
  Esp32_Motor_4.Motor_Speed((-speed));
}

// 向右平移
void right_tran(int speed = speed) {
  Esp32_Motor_1.Motor_Speed((speed));
  Esp32_Motor_2.Motor_Speed((-speed));
  Esp32_Motor_3.Motor_Speed((-speed));
  Esp32_Motor_4.Motor_Speed((speed));
}

// 斜向右前方
void right_oblique(int speed = speed) {
  Esp32_Motor_1.Motor_Speed((speed));
  Esp32_Motor_2.Motor_Speed(0);
  Esp32_Motor_3.Motor_Speed((-speed));
  Esp32_Motor_4.Motor_Speed(0);
}

// 舵机转动
void servoset(int d1 = 90, int d2 = 100){
  servo_25.write(d1);
  delay(100);
  servo_26.write(d2);
}

// 超声波测距
float checkDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  float distance = pulseIn(echoPin, HIGH) / 58.00;   //echo time conversion into a distance
  delay(10);
  return distance;
}

String messageIn;
HardwareSerial mySerial1(1);

void setup(){

  mySerial1.begin(115200,SERIAL_8N1,32,33); // 自定义32，33引脚为串口
  speed = 32;
  Esp32_Motor_1.mcpwm_begin();
  Esp32_Motor_2.mcpwm_begin();
  Esp32_Motor_3.mcpwm_begin();
  Esp32_Motor_4.mcpwm_begin();

  servo_25.attach(25,500,2500);
  servo_26.attach(26,500,2500);

  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  distance = 0;
}

void loop(){
    //声明c串口通信字符串变量
    String rx_buffer = "";
    while (mySerial1.available() > 0) //串口接收到数据
    {
        rx_buffer += char(mySerial1.read());
        delay(2);
    }

    if (rx_buffer.length() > 0)
    {
        DynamicJsonDocument  jsonBuffer(400);
        deserializeJson(jsonBuffer, rx_buffer); // 解析Json数据
        JsonObject doc = jsonBuffer.as<JsonObject>();

        int speed_0 = doc["speed"][0]; // "0/1/2"
        int speed_1 = doc["speed"][1];
        const char* carmove = doc["carmove"][0]; // "STOP/ADVANCE/LEFT/..."
        float degree = doc["carmove"][1];
        int servo_0 = doc["servo"][0];
        int servo_1 = doc["servo"][1];
        int checkdistance = doc["checkdistance"]; // "1/0"

        // 执行速度调节
        if (speed_0 == 0 and 0 <= speed_1 <= 100)
            speed = speed_1;
        else if(speed_0 == 1)
            speed = speed + 10;
        else if (speed_0 == -1)
            speed = speed - 10;

        // 执行运动控制
        messageIn = carmove;
        if (messageIn == "ADVANCE")
            advance(speed);
        else if (messageIn == "BACK")
            back(speed);
        else if (messageIn == "STOP")
            stop();
        else if (messageIn == "LEFT" and 0 < degree <= 2)
            left(speed, degree);
        else if (messageIn == "RIGHT" and 0 < degree <= 2)
            right(speed, degree);
        else if (messageIn == "LEFT_TRAN")
            left_tran(speed);
        else if (messageIn == "RIGHT_TRAN")
            right_tran(speed);
        else if (messageIn == "ANTICLOCKWISE")
            anticlockwise(speed);
        else if (messageIn == "CLOCKWISE")
            clockwise(speed);
        else if (messageIn == "LEFT_OBLIQUE")
            left_oblique(speed);
        else if (messageIn == "RIGHT_OBLIQUE")
            right_oblique(speed);

        // 执行舵机控制
        servoset(servo_0, servo_1);

        // 执行超声波测距
        if (checkdistance == 1){
            distance = checkDistance();
            // 返回Json数据
            DynamicJsonDocument data(256);
            data["distance"] = distance;
            char json_string[256];
            serializeJson(data, json_string); // 打包成Json串
            mySerial1.println(json_string); // 串口输出
        }

    }

}