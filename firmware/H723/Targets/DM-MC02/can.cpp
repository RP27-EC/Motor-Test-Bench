/** @brief 妙板三路经典CAN，独立消息RAM分区，1Mbps，自动重传。 */
#include "main.h"
FDCAN_HandleTypeDef hfdcan1 {}; ///< CAN1：PD0 RX、PD1 TX。
FDCAN_HandleTypeDef hfdcan2 {}; ///< CAN2：PB5 RX、PB6 TX。
FDCAN_HandleTypeDef hfdcan3 {}; ///< CAN3：PD12 RX、PD13 TX。
namespace {
void InitPort(FDCAN_HandleTypeDef &can,FDCAN_GlobalTypeDef *instance,uint32_t offset) {
    can.Instance=instance;
    can.Init.FrameFormat=FDCAN_FRAME_CLASSIC;
    can.Init.Mode=FDCAN_MODE_NORMAL;
    can.Init.AutoRetransmission=ENABLE;
    can.Init.TransmitPause=DISABLE;
    can.Init.ProtocolException=DISABLE;
    // PLL2Q=120MHz，120MHz/[6*(1+14+5)]=1Mbps，采样点75%。
    can.Init.NominalPrescaler=6;
    can.Init.NominalSyncJumpWidth=1;
    can.Init.NominalTimeSeg1=14;
    can.Init.NominalTimeSeg2=5;
    can.Init.DataPrescaler=6;
    can.Init.DataSyncJumpWidth=1;
    can.Init.DataTimeSeg1=14;
    can.Init.DataTimeSeg2=5;
    can.Init.MessageRAMOffset=offset; // 单位为32位字；各端口预留256字，实际各用97字。
    can.Init.StdFiltersNbr=1;
    can.Init.ExtFiltersNbr=0;
    can.Init.RxFifo0ElmtsNbr=16;
    can.Init.RxFifo0ElmtSize=FDCAN_DATA_BYTES_8;
    can.Init.RxFifo1ElmtsNbr=0;
    can.Init.RxFifo1ElmtSize=FDCAN_DATA_BYTES_8;
    can.Init.RxBuffersNbr=0;
    can.Init.RxBufferSize=FDCAN_DATA_BYTES_8;
    can.Init.TxEventsNbr=0;
    can.Init.TxBuffersNbr=0;
    can.Init.TxFifoQueueElmtsNbr=8;
    can.Init.TxFifoQueueMode=FDCAN_TX_FIFO_OPERATION;
    can.Init.TxElmtSize=FDCAN_DATA_BYTES_8;
    if (HAL_FDCAN_Init(&can)!=HAL_OK) Error_Handler();
}
}
extern "C" void BoardCanInit(void) {
    // FDCAN复位信号三路共用，只允许在全部初始化前复位一次。
    __HAL_RCC_FDCAN_CLK_ENABLE();
    __HAL_RCC_FDCAN_FORCE_RESET();
    __HAL_RCC_FDCAN_RELEASE_RESET();
    InitPort(hfdcan1,FDCAN1,0);
    FDCAN_ClkCalUnitTypeDef ccu {}; ///< 共用时钟校准单元：旁路校准、不分频。
    ccu.ClockCalibration=FDCAN_CLOCK_CALIBRATION_DISABLE;
    ccu.ClockDivider=FDCAN_CLOCK_DIV1;
    if (HAL_FDCAN_ConfigClockCalibration(&hfdcan1,&ccu)!=HAL_OK) Error_Handler();
    InitPort(hfdcan2,FDCAN2,256);
    InitPort(hfdcan3,FDCAN3,512);
}
extern "C" void HAL_FDCAN_MspInit(FDCAN_HandleTypeDef *can) {
    GPIO_InitTypeDef gpio {}; ///< 所选CAN口的GPIO复用参数。
    GPIO_TypeDef *port=nullptr; ///< 物理引脚所属GPIO端口。
    IRQn_Type irq=FDCAN1_IT0_IRQn; ///< FIFO0使用的中断线。
    __HAL_RCC_FDCAN_CLK_ENABLE();
    gpio.Mode=GPIO_MODE_AF_PP;
    gpio.Pull=GPIO_NOPULL;
    gpio.Speed=GPIO_SPEED_FREQ_VERY_HIGH;
    switch (reinterpret_cast<uintptr_t>(can->Instance)) {
    case FDCAN1_BASE:
        __HAL_RCC_GPIOD_CLK_ENABLE();port=GPIOD;
        gpio.Pin=GPIO_PIN_0|GPIO_PIN_1;gpio.Alternate=GPIO_AF9_FDCAN1;
        irq=FDCAN1_IT0_IRQn;break;
    case FDCAN2_BASE:
        __HAL_RCC_GPIOB_CLK_ENABLE();port=GPIOB;
        gpio.Pin=GPIO_PIN_5|GPIO_PIN_6;gpio.Alternate=GPIO_AF9_FDCAN2;
        irq=FDCAN2_IT0_IRQn;break;
    case FDCAN3_BASE:
        __HAL_RCC_GPIOD_CLK_ENABLE();port=GPIOD;
        gpio.Pin=GPIO_PIN_12|GPIO_PIN_13;gpio.Alternate=GPIO_AF5_FDCAN3;
        irq=FDCAN3_IT0_IRQn;break;
    default:Error_Handler();return;
    }
    HAL_GPIO_Init(port,&gpio);
    HAL_NVIC_SetPriority(irq,5,0);
    HAL_NVIC_EnableIRQ(irq);
}
