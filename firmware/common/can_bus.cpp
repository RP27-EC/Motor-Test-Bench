#include "main.h"
#include "can_bus.hpp"
#include <initializer_list>

namespace motor_test {
namespace {
constexpr unsigned Capacity = 128;
volatile Frame queue[Capacity];
volatile unsigned head, tail;
volatile uint32_t selectedPort = 1;
uint32_t lastTxMask;

#if defined(STM32F407xx)
CAN_HandleTypeDef* Handle() { return selectedPort == 2 ? &hcan2 : &hcan1; }
#else
FDCAN_HandleTypeDef* Handle() {
    if (selectedPort == 2) return &hfdcan2;
    if (selectedPort == 3) return &hfdcan3;
    return &hfdcan1;
}
#endif

void Push(uint32_t id, const uint8_t* bytes) {
    const auto next = (head + 1) % Capacity;
    if (next == tail) return;
    queue[head].id = id;
    queue[head].tick = HAL_GetTick();
    for (unsigned i = 0; i < 8; ++i) queue[head].bytes[i] = bytes[i];
    __DMB();
    head = next;
}
}

void StartCan() {
#if defined(STM32F407xx)
    for (auto* can : {&hcan1, &hcan2}) {
        CAN_FilterTypeDef filter{};
        filter.FilterBank = can == &hcan1 ? 0 : 14;
        filter.SlaveStartFilterBank = 14;
        filter.FilterMode = CAN_FILTERMODE_IDMASK;
        filter.FilterScale = CAN_FILTERSCALE_32BIT;
        filter.FilterMaskIdLow = 6;
        filter.FilterFIFOAssignment = CAN_RX_FIFO0;
        filter.FilterActivation = ENABLE;
        if (HAL_CAN_ConfigFilter(can, &filter) != HAL_OK || HAL_CAN_Start(can) != HAL_OK ||
            HAL_CAN_ActivateNotification(can, CAN_IT_RX_FIFO0_MSG_PENDING) != HAL_OK) Error_Handler();
    }
#else
    for (auto* can : {&hfdcan1, &hfdcan2, &hfdcan3}) {
        FDCAN_FilterTypeDef filter{};
        filter.IdType = FDCAN_STANDARD_ID;
        filter.FilterType = FDCAN_FILTER_MASK;
        filter.FilterConfig = FDCAN_FILTER_TO_RXFIFO0;
        if (HAL_FDCAN_ConfigFilter(can, &filter) != HAL_OK ||
            HAL_FDCAN_ConfigGlobalFilter(can, FDCAN_REJECT, FDCAN_REJECT, FDCAN_REJECT_REMOTE, FDCAN_REJECT_REMOTE) != HAL_OK ||
            HAL_FDCAN_Start(can) != HAL_OK ||
            HAL_FDCAN_ActivateNotification(can, FDCAN_IT_RX_FIFO0_NEW_MESSAGE, 0) != HAL_OK) Error_Handler();
    }
#endif
}

void SelectPort(uint32_t port) {
    const auto mask = __get_PRIMASK();
    __disable_irq();
    selectedPort = port;
    lastTxMask = 0;
    head = 0;
    tail = 0;
    __set_PRIMASK(mask);
}

bool Receive(Frame& frame) {
    const auto index = tail;
    if (head == index) return false;
    frame.id = queue[index].id;
    frame.tick = queue[index].tick;
    for (unsigned i = 0; i < 8; ++i) frame.bytes[i] = queue[index].bytes[i];
    __DMB();
    tail = (index + 1) % Capacity;
    return true;
}

bool Pending() {
#if defined(STM32F407xx)
    return HAL_CAN_GetTxMailboxesFreeLevel(Handle()) != 3;
#else
    return Handle()->Instance->TXBRP != 0;
#endif
}

bool Transmitted() {
#if defined(STM32F407xx)
    return lastTxMask && (Handle()->Instance->TSR & lastTxMask) != 0;
#else
    return lastTxMask && (Handle()->Instance->TXBTO & lastTxMask) != 0;
#endif
}

bool BusOff() {
#if defined(STM32F407xx)
    return (Handle()->Instance->ESR & CAN_ESR_BOFF) != 0;
#else
    return (Handle()->Instance->PSR & FDCAN_PSR_BO) != 0;
#endif
}

void Abort() {
#if defined(STM32F407xx)
    HAL_CAN_AbortTxRequest(Handle(), CAN_TX_MAILBOX0 | CAN_TX_MAILBOX1 | CAN_TX_MAILBOX2);
#else
    const auto pending = Handle()->Instance->TXBRP;
    if (pending) HAL_FDCAN_AbortTxRequest(Handle(), pending);
#endif
}

void Recover() {
#if !defined(STM32F407xx)
    if (BusOff() && !Pending()) CLEAR_BIT(Handle()->Instance->CCCR, FDCAN_CCCR_INIT);
#endif
}

bool Send(uint32_t id, const uint8_t (&data)[8], uint8_t length) {
    if (id > 0x7ff || (length != 4 && length != 8) || BusOff()) return false;
    auto* can = Handle();
#if defined(STM32F407xx)
    if (!HAL_CAN_GetTxMailboxesFreeLevel(can)) return false;
    CAN_TxHeaderTypeDef header{};
    header.StdId = id;
    header.IDE = CAN_ID_STD;
    header.RTR = CAN_RTR_DATA;
    header.DLC = length;
    uint32_t mailbox;
    if (!Pending()) can->Instance->TSR = CAN_TSR_RQCP0 | CAN_TSR_RQCP1 | CAN_TSR_RQCP2;
    if (HAL_CAN_AddTxMessage(can, &header, const_cast<uint8_t*>(data), &mailbox) != HAL_OK) return false;
    lastTxMask = mailbox == CAN_TX_MAILBOX0 ? CAN_TSR_TXOK0 :
                 mailbox == CAN_TX_MAILBOX1 ? CAN_TSR_TXOK1 : CAN_TSR_TXOK2;
    return true;
#else
    if (!HAL_FDCAN_GetTxFifoFreeLevel(can)) return false;
    FDCAN_TxHeaderTypeDef header{};
    header.Identifier = id;
    header.IdType = FDCAN_STANDARD_ID;
    header.TxFrameType = FDCAN_DATA_FRAME;
    header.DataLength = length == 4 ? FDCAN_DLC_BYTES_4 : FDCAN_DLC_BYTES_8;
    header.FDFormat = FDCAN_CLASSIC_CAN;
    header.BitRateSwitch = FDCAN_BRS_OFF;
    if (HAL_FDCAN_AddMessageToTxFifoQ(can, &header, const_cast<uint8_t*>(data)) != HAL_OK) return false;
    lastTxMask = HAL_FDCAN_GetLatestTxFifoQRequestBuffer(can);
    return true;
#endif
}

#if defined(STM32F407xx)
void OnReceive(CAN_HandleTypeDef* can) {
    uint8_t bytes[8];
    CAN_RxHeaderTypeDef rx{};
    for (unsigned n = 0; n < 16 && HAL_CAN_GetRxFifoFillLevel(can, CAN_RX_FIFO0); ++n) {
        if (HAL_CAN_GetRxMessage(can, CAN_RX_FIFO0, &rx, bytes) != HAL_OK) break;
        if (can == Handle() && rx.IDE == CAN_ID_STD && rx.RTR == CAN_RTR_DATA && rx.DLC == 8) Push(rx.StdId, bytes);
    }
}
#else
void OnReceive(FDCAN_HandleTypeDef* can) {
    uint8_t bytes[64];
    FDCAN_RxHeaderTypeDef rx{};
    for (unsigned n = 0; n < 16 && HAL_FDCAN_GetRxFifoFillLevel(can, FDCAN_RX_FIFO0); ++n) {
        if (HAL_FDCAN_GetRxMessage(can, FDCAN_RX_FIFO0, &rx, bytes) != HAL_OK) break;
        if (can == Handle() && rx.IdType == FDCAN_STANDARD_ID && rx.RxFrameType == FDCAN_DATA_FRAME &&
            rx.DataLength == FDCAN_DLC_BYTES_8 && rx.FDFormat == FDCAN_CLASSIC_CAN) Push(rx.Identifier, bytes);
    }
}
#endif
}

#if defined(STM32F407xx)
extern "C" void HAL_CAN_RxFifo0MsgPendingCallback(CAN_HandleTypeDef* can) { motor_test::OnReceive(can); }
#else
extern "C" void HAL_FDCAN_RxFifo0Callback(FDCAN_HandleTypeDef* can, uint32_t flags) {
    if (flags & FDCAN_IT_RX_FIFO0_NEW_MESSAGE) motor_test::OnReceive(can);
}
#endif
