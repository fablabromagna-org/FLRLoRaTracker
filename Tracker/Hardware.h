#pragma once
#include <Arduino.h>

// 0 = Pico + Waveshare Pico-LoRa-SX1262 shield.
// 1 = Waveshare RP2040-LoRa-HF integrated board (TX).
#ifndef TRACKER_HARDWARE
#define TRACKER_HARDWARE 0
#endif
static_assert(TRACKER_HARDWARE == 0 || TRACKER_HARDWARE == 1, "Invalid TRACKER_HARDWARE");
constexpr bool kIntegratedLoRa = TRACKER_HARDWARE == 1;

// Both boards connect the SX1262 to SPI1.
constexpr uint8_t kRadioSckPin = kIntegratedLoRa ? 14 : 10;
constexpr uint8_t kRadioMosiPin = kIntegratedLoRa ? 15 : 11;
constexpr uint8_t kRadioMisoPin = kIntegratedLoRa ? 24 : 12;
constexpr uint8_t kRadioCsPin = kIntegratedLoRa ? 13 : 3;
constexpr uint8_t kRadioResetPin = kIntegratedLoRa ? 23 : 15;
constexpr uint8_t kRadioDio1Pin = kIntegratedLoRa ? 16 : 20;
constexpr uint8_t kRadioBusyPin = kIntegratedLoRa ? 18 : 2;
// Additional active-low RF control on the integrated board.
constexpr uint8_t kRadioAntennaSwitchPin = 17;
