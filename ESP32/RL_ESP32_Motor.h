/**********************************************************
      Make in goouuu.com
	  Maker:MDC
***********************************************************/
#ifndef RL_ESP32_Motor_H
#define RL_ESP32_Motor_H


#include <stdio.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_attr.h"

#include "driver/mcpwm.h"
#include "soc/mcpwm_reg.h"
#include "soc/mcpwm_struct.h"



class Motor
{
  private:
          int  pin;   
          int  Dire_Pin;
          int  Speed_Pin;

          void setMotornum(uint8_t num,uint8_t Pin_A,uint8_t Pin_B);

          mcpwm_io_signals_t  MCPWMXA;
          mcpwm_io_signals_t  MCPWMXB;
          mcpwm_unit_t  MCPWM_UNIT;          
          mcpwm_timer_t MCPWM_TIMER;

  public:  //公共方法
     Motor(uint8_t num,uint8_t Pin_A,uint8_t Pin_B);//构造函数
     ~Motor();//析构函数

     
     void mcpwm_begin();
     
     void Motor_Speed(float duty_cycle);
    
};


 

#endif
