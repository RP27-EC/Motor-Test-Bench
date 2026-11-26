#pragma once
#include <cstdint>

namespace motor_test {
struct Frame {
    uint32_t id;
    uint32_t tick;
    uint8_t bytes[8];
};
void StartCan();
void SelectPort(uint32_t port);
bool Receive(Frame& frame);
bool Send(uint32_t id, const uint8_t (&data)[8], uint8_t length = 8);
bool Pending();
bool Transmitted();
bool BusOff();
void Abort();
void Recover();
void ApplicationEntryPoint();
}
