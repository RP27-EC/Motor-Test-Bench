#include "main.h"
CAN_HandleTypeDef hcan1 {},hcan2 {}; ///< C板两路bxCAN句柄。
namespace {
void Init(CAN_HandleTypeDef &can,CAN_TypeDef *instance) {
    can.Instance=instance;can.Init.Prescaler=3;can.Init.Mode=CAN_MODE_NORMAL;
    can.Init.SyncJumpWidth=CAN_SJW_1TQ;can.Init.TimeSeg1=CAN_BS1_10TQ;can.Init.TimeSeg2=CAN_BS2_3TQ;
    can.Init.AutoBusOff=ENABLE;can.Init.AutoRetransmission=ENABLE;can.Init.TransmitFifoPriority=ENABLE;
    if(HAL_CAN_Init(&can)!=HAL_OK) Error_Handler();
}
}
extern "C" void MX_CAN1_Init() { Init(hcan1,CAN1); }
extern "C" void MX_CAN2_Init() { Init(hcan2,CAN2); }
extern "C" void HAL_MspInit() { __HAL_RCC_SYSCFG_CLK_ENABLE();__HAL_RCC_PWR_CLK_ENABLE();HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4); }
extern "C" void HAL_CAN_MspInit(CAN_HandleTypeDef *can) {
    __HAL_RCC_CAN1_CLK_ENABLE(); // CAN2使用共享CAN1时钟。
    GPIO_InitTypeDef gpio {};gpio.Mode=GPIO_MODE_AF_PP;gpio.Pull=GPIO_NOPULL;gpio.Speed=GPIO_SPEED_FREQ_VERY_HIGH;
    IRQn_Type irq=CAN1_RX0_IRQn;
    switch(reinterpret_cast<uintptr_t>(can->Instance)) {
    case CAN1_BASE:
        __HAL_RCC_GPIOD_CLK_ENABLE();gpio.Pin=GPIO_PIN_0|GPIO_PIN_1;gpio.Alternate=GPIO_AF9_CAN1;HAL_GPIO_Init(GPIOD,&gpio);break;
    case CAN2_BASE:
        __HAL_RCC_CAN2_CLK_ENABLE();__HAL_RCC_GPIOB_CLK_ENABLE();gpio.Pin=GPIO_PIN_5|GPIO_PIN_6;gpio.Alternate=GPIO_AF9_CAN2;HAL_GPIO_Init(GPIOB,&gpio);irq=CAN2_RX0_IRQn;break;
    default:Error_Handler();
    }
    HAL_NVIC_SetPriority(irq,5,0);HAL_NVIC_EnableIRQ(irq);
}
