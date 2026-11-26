cmake_minimum_required(VERSION 3.22)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_CXX_COMPILER arm-none-eabi-g++)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
# 显式绑定交叉编译辅助工具，避免Windows在中文目录下回退搜索宿主工具。
find_program(ARM_GCC_EXECUTABLE NAMES arm-none-eabi-gcc REQUIRED)
get_filename_component(ARM_GCC_BIN "${ARM_GCC_EXECUTABLE}" DIRECTORY)
foreach(tool AR RANLIB STRIP LINKER NM OBJDUMP OBJCOPY READELF ADDR2LINE)
    string(TOLOWER "${tool}" name)
    if(tool STREQUAL "LINKER")
        set(name ld)
    endif()
    if(CMAKE_HOST_WIN32)
        set(suffix .exe)
    else()
        set(suffix "")
    endif()
    set(CMAKE_${tool} "${ARM_GCC_BIN}/arm-none-eabi-${name}${suffix}" CACHE FILEPATH "ARM tool" FORCE)
endforeach()

project(motor_bench_f407 LANGUAGES C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
add_executable(FIRMWARE.elf
    "../common/main.cpp"
    "../common/can_bus.cpp"
    "../common/pid.cpp"
    "Targets/RM-C/Core/Src/stm32f4xx_hal_timebase_tim.c"
    "Targets/RM-C/Core/Src/system_stm32f4xx.c"
    "Targets/RM-C/can.cpp"
    "Targets/RM-C/clock.c"
    "Targets/RM-C/interrupts.cpp"
    "Targets/RM-C/platform.cpp"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_can.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c"
    "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c"
    "Targets/RM-C/startup.s"
)
target_include_directories(FIRMWARE.elf PRIVATE
    "../common"
    "Targets/RM-C/Core/Inc"
    "Drivers/STM32F4xx_HAL_Driver/Inc"
    "Drivers/STM32F4xx_HAL_Driver/Inc/Legacy"
    "Drivers/CMSIS/Include"
    "Drivers/CMSIS/Device/ST/STM32F4xx/Include"
)
target_compile_definitions(FIRMWARE.elf PRIVATE USE_HAL_DRIVER STM32F407xx HSE_VALUE=12000000U)
set(MCU -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)
target_compile_options(FIRMWARE.elf PRIVATE ${MCU} -g3 -gdwarf-4 -O2 -fdata-sections -ffunction-sections -Wall -Wextra -Wno-unused-parameter $<$<COMPILE_LANGUAGE:CXX>:-fno-exceptions;-fno-rtti;-fno-threadsafe-statics>)
target_link_options(FIRMWARE.elf PRIVATE ${MCU} -T "${CMAKE_CURRENT_SOURCE_DIR}/Targets/RM-C/firmware.ld" --specs=nano.specs --specs=nosys.specs -Wl,--gc-sections,--print-memory-usage "-Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/FIRMWARE.map")
target_link_libraries(FIRMWARE.elf PRIVATE m)
add_custom_command(TARGET FIRMWARE.elf POST_BUILD COMMAND arm-none-eabi-objcopy -O ihex $<TARGET_FILE:FIRMWARE.elf> "${CMAKE_CURRENT_BINARY_DIR}/FIRMWARE.hex")

if(DEFINED BENCH_BUILD_ID)
    target_compile_definitions(FIRMWARE.elf PRIVATE BENCH_BUILD_ID=${BENCH_BUILD_ID}U)
endif()
