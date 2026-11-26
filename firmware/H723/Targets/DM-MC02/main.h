/** @brief 妙板DM-MC02/H723的最小板级接口。 */
#pragma once
#include "stm32h7xx_hal.h"
#define MOTOR_TEST_SYSTEM_CLOCK_HZ 480000000U ///< 系统主频，不要求CPU_FREQ_BOOST选项。
#ifdef __cplusplus
extern "C" {
#endif
extern FDCAN_HandleTypeDef hfdcan1, hfdcan2, hfdcan3; ///< 三路物理CAN控制器。
void SystemClock_Config(void);
void PeriphCommonClock_Config(void);
void BoardCanInit(void);
void Error_Handler(void);
#ifdef __cplusplus
}
#endif
