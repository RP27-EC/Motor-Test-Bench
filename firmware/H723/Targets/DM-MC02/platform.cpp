/** @brief 妙板最小入口；SysTick提供1ms时基，不创建RTOS或其他外设。 */
#include "main.h"
#include "can_bus.hpp"
int main() {
    // 电机测试保持调试域时钟，便于运行中连接和读取内存。
    SET_BIT(DBGMCU->CR,DBGMCU_CR_DBG_CKD1EN|DBGMCU_CR_DBG_CKD3EN|DBGMCU_CR_DBG_SLEEPD1);
    CLEAR_BIT(SCB->SCR,SCB_SCR_SLEEPDEEP_Msk|SCB_SCR_SLEEPONEXIT_Msk);
    SCB_EnableICache();
    HAL_Init();
    // 在复位默认HSI时钟下预留连接窗口；此时尚未初始化CAN或输出控制帧。
    HAL_Delay(1000);
    SystemClock_Config();
    PeriphCommonClock_Config();
    BoardCanInit();
    motor_test::ApplicationEntryPoint();
    Error_Handler();
}
extern "C" void HAL_MspInit(void) { HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4); }
extern "C" void Error_Handler(void) { __disable_irq();while (true) {} }
