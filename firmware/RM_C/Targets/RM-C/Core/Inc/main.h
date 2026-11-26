#pragma once
#ifdef __cplusplus
extern "C" {
#endif
#include "stm32f4xx_hal.h"
void Error_Handler(void);
void SystemClock_Config(void);
void MX_CAN1_Init(void);
void MX_CAN2_Init(void);
extern CAN_HandleTypeDef hcan1,hcan2;
#ifdef __cplusplus
}
#endif
