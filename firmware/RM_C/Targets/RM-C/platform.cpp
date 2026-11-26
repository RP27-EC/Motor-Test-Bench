/** @brief C板最小启动入口，业务控制使用C++，不创建RTOS或无关外设。 */
#include "main.h"
#include "can_bus.hpp"
int main() {
    HAL_Init();SystemClock_Config();
    __HAL_RCC_CAN1_CLK_ENABLE();__HAL_RCC_CAN2_CLK_ENABLE();
    __HAL_RCC_CAN1_FORCE_RESET();__HAL_RCC_CAN2_FORCE_RESET();
    __HAL_RCC_CAN1_RELEASE_RESET();__HAL_RCC_CAN2_RELEASE_RESET();
    MX_CAN1_Init();MX_CAN2_Init();
    motor_test::ApplicationEntryPoint();
    Error_Handler();
}
extern "C" void Error_Handler(void) { __disable_irq();while (true) {} }
