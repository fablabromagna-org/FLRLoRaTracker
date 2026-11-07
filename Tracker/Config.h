#pragma once
#include <Arduino.h>

// 0 = TX with anemometer, 1 = RX, 2 = RX with calibration anemometer.
#ifndef TRACKER_ROLE
#define TRACKER_ROLE 1
#endif
static_assert(TRACKER_ROLE >= 0 && TRACKER_ROLE <= 2, "Invalid TRACKER_ROLE");
constexpr bool kTransmitter = TRACKER_ROLE == 0;
#include "Hardware.h"
static_assert(!kIntegratedLoRa || kTransmitter,
              "RP2040-LoRa-HF profile supports TX only; set TRACKER_ROLE=0");
constexpr bool kAnemometer = TRACKER_ROLE == 2;
constexpr bool kHasLocalAnemometer = kTransmitter || kAnemometer;
constexpr uint8_t kWindPin = 27;  // GP27 / ADC1 on both boards.
constexpr uint32_t kWindReadMs = 10;
constexpr uint32_t kWindSampleMs = 1000;
constexpr float kAdcReferenceV = 3.3f;
constexpr uint8_t kBatteryPin = A0;  // GP26, Waveshare BATTERY_AD.
// RP2040-LoRa-HF needs an external divider before enabling this input.
constexpr bool kBatteryMonitorEnabled = !kIntegratedLoRa;
// Waveshare schematic R17=200k, R18=100k, R19=0R (optional on some revisions).
constexpr float kBatteryDividerRatio = 3.0f;
constexpr float kBatteryMinValidV = 2.5f;
constexpr float kBatteryMaxValidV = 4.35f;
// Provisional slope fitted to the 2026-11-07 road test.
// Stationary zero measured on this RX with the final wiring.
constexpr float kWindSlope = 16.8f;
constexpr float kWindZeroV = 0.021f;
constexpr uint32_t kIntervalMs = 3000;
constexpr uint32_t kGpsBaud = 9600;
constexpr uint32_t kGpsFreshMs = 5000;
constexpr uint32_t kLinkTimeoutMs = 3 * kIntervalMs;
// Optional common-cathode RGB LED and passive piezo. Enable after wiring.
constexpr bool kRgbEnabled = false;
constexpr bool kBeeperEnabled = false;
constexpr uint8_t kLedRedPin = 18;
constexpr uint8_t kLedGreenPin = 19;
constexpr uint8_t kLedBluePin = 21;
constexpr uint8_t kBeeperPin = 22;
constexpr size_t kSequenceSize = 4;
constexpr size_t kStatusSize = 5;
constexpr size_t kPositionSize = 13;
// Extensions contain wind in 0.01 m/s and voltage in millivolts, little-endian.
constexpr size_t kWindExtensionSize = 4;
constexpr size_t kBatteryExtensionSize = 2;
constexpr size_t kTelemetryExtensionSize = kWindExtensionSize + kBatteryExtensionSize;
constexpr size_t kMaxPayloadSize = kPositionSize + kTelemetryExtensionSize;
constexpr uint16_t kMissingWindValue = 0xFFFF;
constexpr uint32_t kWindFreshMs = 2 * kWindSampleMs;
constexpr uint8_t kDisplayHeight = 64;
enum GpsStatus : uint8_t { NoData, NoFix, Fix, Legacy };
constexpr uint8_t kPpsPin = 16;
constexpr uint8_t kLogButtonPin = 17;
constexpr char kCsvHeader[] = "rx_ms,seq,rssi_dbm,snr_db,quality_0_9,gps,lat,lon,distance_m,rx_lat,rx_lon,rx_altitude_m,wind_ms,wind_volts,record_type,utc,tx_battery_v,rx_battery_v";
