/** @brief H723最小HAL配置：24MHz晶振，仅启动时钟、GPIO和FDCAN。 */
#pragma once
#define HAL_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
#define HAL_FDCAN_MODULE_ENABLED
#define HAL_CORTEX_MODULE_ENABLED
#define HAL_FLASH_MODULE_ENABLED
#define HAL_PWR_MODULE_ENABLED
#define HAL_DMA_MODULE_ENABLED
#ifndef HSE_VALUE
#define HSE_VALUE 24000000U
#endif
#define HSE_STARTUP_TIMEOUT 100U
#define HSI_VALUE 64000000U
#define CSI_VALUE 4000000U
#define LSI_VALUE 32000U
#define LSE_VALUE 32768U
#define LSE_STARTUP_TIMEOUT 5000U
#define EXTERNAL_CLOCK_VALUE 12288000U
#define VDD_VALUE 3300U
#define TICK_INT_PRIORITY 15U
#define USE_RTOS 0U
#define USE_SD_TRANSCEIVER 0U
#define USE_HAL_FDCAN_REGISTER_CALLBACKS 0U
#define assert_param(expr) ((void)0U)
#include "stm32h7xx_hal_rcc.h"
#include "stm32h7xx_hal_gpio.h"
#include "stm32h7xx_hal_dma.h"
#include "stm32h7xx_hal_cortex.h"
#include "stm32h7xx_hal_flash.h"
#include "stm32h7xx_hal_pwr.h"
#include "stm32h7xx_hal_fdcan.h"
