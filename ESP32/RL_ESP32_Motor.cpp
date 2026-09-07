#include "RL_ESP32_Motor.h"
#include "Arduino.h"

Motor :: Motor(uint8_t num ,uint8_t Pin_A,uint8_t Pin_B)
{
    setMotornum(num,Pin_A,Pin_B);    
}
Motor :: ~Motor()
{
    
} 

void Motor::setMotornum(uint8_t num,uint8_t Pin_A,uint8_t Pin_B)
{    
    switch (num)
    {
	case 1:
      Dire_Pin = Pin_A;
     Speed_Pin = Pin_B;
     MCPWM_TIMER = MCPWM_TIMER_0;
     MCPWM_UNIT=MCPWM_UNIT_0;
     MCPWMXA=MCPWM0A;
     MCPWMXB=MCPWM0B;
	    break;
	case 2:
      Dire_Pin = Pin_A;
     Speed_Pin = Pin_B;
     MCPWM_TIMER = MCPWM_TIMER_1;
     MCPWM_UNIT=MCPWM_UNIT_0;
      MCPWMXA=MCPWM1A;
     MCPWMXB=MCPWM1B;
	    break;
  case 3:
       Dire_Pin = Pin_A;
     Speed_Pin = Pin_B;
     MCPWM_TIMER = MCPWM_TIMER_2;
     MCPWM_UNIT=MCPWM_UNIT_0;
    MCPWMXA=MCPWM2A;
     MCPWMXB=MCPWM2B;
      break;  
  case 4:
      Dire_Pin = Pin_A;
     Speed_Pin = Pin_B;
     MCPWM_TIMER = MCPWM_TIMER_0;
     MCPWM_UNIT=MCPWM_UNIT_1;
      MCPWMXA=MCPWM0A;
     MCPWMXB=MCPWM0B;
      break;  
  case 5:
      Dire_Pin = Pin_A;
     Speed_Pin = Pin_B;
     MCPWM_TIMER = MCPWM_TIMER_1;
     MCPWM_UNIT=MCPWM_UNIT_1;
      MCPWMXA=MCPWM1A;
     MCPWMXB=MCPWM1B;
      break;    
  case 6:
      Dire_Pin = Pin_A;
     Speed_Pin = Pin_B;
     MCPWM_TIMER = MCPWM_TIMER_2;
     MCPWM_UNIT=MCPWM_UNIT_1;
     MCPWMXA=MCPWM2A;
     MCPWMXB=MCPWM2B;
      break;    	
	default:
	    break;
    }
   
}

void Motor :: mcpwm_begin()
{  
   
  mcpwm_gpio_init(MCPWM_UNIT, MCPWMXA,  Dire_Pin);
  mcpwm_gpio_init(MCPWM_UNIT, MCPWMXB,  Speed_Pin);
  mcpwm_config_t pwm_config;
  pwm_config.frequency = 1000;    //frequency = 500Hz,    
  pwm_config.cmpr_a = 0;    //duty cycle of PWMxA = 0
  pwm_config.cmpr_b = 0;    //duty cycle of PWMxB = 0
  pwm_config.counter_mode = MCPWM_UP_COUNTER;
  pwm_config.duty_mode = MCPWM_DUTY_MODE_0;
  mcpwm_init(MCPWM_UNIT, MCPWM_TIMER, &pwm_config);

  }

  

void Motor :: Motor_Speed(float duty_cycle)
{
  if(duty_cycle>0)
    {
      mcpwm_set_signal_low(MCPWM_UNIT, MCPWM_TIMER, MCPWM_OPR_A);
      mcpwm_set_duty(MCPWM_UNIT, MCPWM_TIMER, MCPWM_OPR_B, duty_cycle);
      mcpwm_set_duty_type(MCPWM_UNIT, MCPWM_TIMER, MCPWM_OPR_B, MCPWM_DUTY_MODE_0);
    }else if(duty_cycle==0)
    {
      mcpwm_set_signal_high(MCPWM_UNIT, MCPWM_TIMER, MCPWM_OPR_A);
      mcpwm_set_signal_high(MCPWM_UNIT, MCPWM_TIMER, MCPWM_OPR_B);
    }

     else{
      mcpwm_set_signal_low(MCPWM_UNIT, MCPWM_TIMER, MCPWM_OPR_B);
      mcpwm_set_duty(MCPWM_UNIT, MCPWM_TIMER, MCPWM_OPR_A, -duty_cycle);
      mcpwm_set_duty_type(MCPWM_UNIT, MCPWM_TIMER, MCPWM_OPR_A, MCPWM_DUTY_MODE_0);
    }
}



