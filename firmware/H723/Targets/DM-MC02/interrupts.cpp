/** @brief 三路FDCAN接收中断和HAL毫秒节拍；无RTOS中断分发。 */
#include "main.h"
extern "C" {
void FDCAN1_IT0_IRQHandler(void) { HAL_FDCAN_IRQHandler(&hfdcan1); }
void FDCAN2_IT0_IRQHandler(void) { HAL_FDCAN_IRQHandler(&hfdcan2); }
void FDCAN3_IT0_IRQHandler(void) { HAL_FDCAN_IRQHandler(&hfdcan3); }
void SysTick_Handler(void) { HAL_IncTick(); }
void NMI_Handler(void) { Error_Handler(); }
void HardFault_Handler(void) { Error_Handler(); }
void MemManage_Handler(void) { Error_Handler(); }
void BusFault_Handler(void) { Error_Handler(); }
void UsageFault_Handler(void) { Error_Handler(); }
void SVC_Handler(void) {}
void DebugMon_Handler(void) {}
void PendSV_Handler(void) {}
}
