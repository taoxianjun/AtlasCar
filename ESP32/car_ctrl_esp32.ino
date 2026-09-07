#include <RL_ESP32_Motor.h>
#include <ESP32_Servo.h>

enum {
  M0 = 0,
  M1,
  M2,
  M3,
  S1,
  S2,
  US
};

// typedef short short;

const int BUFFER_SIZE = 7 * sizeof(short);

// 定义电机引脚
Motor motors[] = { Motor(1, 12, 13), Motor(2, 14, 15), Motor(3, 16, 17), Motor(4, 18, 19) };
// 创建舵机实例
Servo servo_25;
Servo servo_26;

short status[] = { 0, 0, 0, 0, 110, 90 };


short check_val = -12345;

void set_motor(short* speeds) {
  short curr_speeds[] = { status[M0], status[M1], status[M2], status[M3] };

  for (int i = 0; i < 4; i++) {
    if (speeds[i] != curr_speeds[i]) {
      motors[i].Motor_Speed(speeds[i]);
      status[i] = speeds[i];
    }
  }
}

// 舵机转动
void set_servo(short* angles) {
  short curr_angles[] = { status[S1], status[S2] };
  if (curr_angles[0] != angles[0]) {
    servo_25.write(angles[0]);
    status[S1] = angles[0];
  }

  if (curr_angles[1] != angles[1]) {
    servo_26.write(angles[1]);
    status[S2] = angles[1];
  }
}

const int TrigPin = 4;
const int EchoPin = 5;
const float SoundSpeed = 0.034;
TaskHandle_t Task1;
bool stop = false;

void Task1code(void* pvParameters) {
  while (true) {
    digitalWrite(TrigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(TrigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(TrigPin, LOW);
    long duration = pulseIn(EchoPin, HIGH);

    float distance = duration * SoundSpeed / 2;
    if (distance > 1) {
      if (distance < 10) {
        stop = true;
        short stopped[] = { 0, 0, 0, 0 };
        set_motor(stopped);
      } else {
        stop = false;
      }
    }
    delay(100);
  }
}

void setup() {

  Serial.begin(115200);
  for (int i = 0; i < 4; i++) {
    motors[i].mcpwm_begin();
  }

  servo_25.attach(25, 500, 2500);
  servo_26.attach(26, 500, 2500);

  pinMode(TrigPin, OUTPUT);  // Sets the trigPin as an Output
  pinMode(EchoPin, INPUT);

  short init_speeds[] = { 0, 0, 0, 0 };
  short init_angles[] = { 110, 90 };
  set_motor(init_speeds);
  set_servo(init_angles);

  xTaskCreatePinnedToCore(
    Task1code,        /* Task function. */
    "Task1",          /* name of task. */
    10000,            /* Stack size of task */
    NULL,             /* parameter of the task */
    tskIDLE_PRIORITY, /* priority of the task */
    &Task1,           /* Task handle to keep track of created task */
    0);               /* pin task to core 0 */
}


void loop() {
  if (Serial.available() > 0) {
    short curr_status[] = { 0, 0, 0, 0, 110, 90, 1 };
    Serial.readBytes((char*)curr_status, BUFFER_SIZE);

    short speeds[] = { curr_status[M0], curr_status[M1], curr_status[M2], curr_status[M3] };
    short angles[] = { curr_status[S1], curr_status[S2] };
    short check = curr_status[US];

    if (!(check ^ check_val)) {
      if (stop) {
        Serial.println("FAIL");
      } else {
        set_motor(speeds);
        set_servo(angles);
        Serial.println("SUCC");
      }
    }
  }
}