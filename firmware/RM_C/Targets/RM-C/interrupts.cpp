#include "main.h"
extern TIM_HandleTypeDef htim2; ///< HAL独立毫秒时基TIM2。
extern "C" {
void CAN1_RX0_IRQHandler(void) { HAL_CAN_IRQHandler(&hcan1); }
void CAN2_RX0_IRQHandler(void) { HAL_CAN_IRQHandler(&hcan2); }
void TIM2_IRQHandler(void) { HAL_TIM_IRQHandler(&htim2); }
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *tim) {
    if (tim->Instance==TIM2) HAL_IncTick();
}
void NMI_Handler(void) { Error_Handler(); }
void HardFault_Handler(void) { Error_Handler(); }
void MemManage_Handler(void) { Error_Handler(); }
void BusFault_Handler(void) { Error_Handler(); }
void UsageFault_Handler(void) { Error_Handler(); }
void SVC_Handler(void) {}
void DebugMon_Handler(void) {}
void PendSV_Handler(void) {}
void SysTick_Handler(void) {} // HAL时基使用TIM2，未启动SysTick。
}
