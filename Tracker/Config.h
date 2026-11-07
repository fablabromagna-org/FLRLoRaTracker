#pragma once
#include <Arduino.h>

// 0 = TX with anemometer, 1 = RX, 2 = RX with calibration anemometer.
#ifndef TRACKER_ROLE
#define TRACKER_ROLE 1
#endif
static_assert(TRACKER_ROLE >= 0 && TRACKER_ROLE <= 2, "Invalid TRACKER_ROLE");
constexpr bool kTransmitter = TRACKER_ROLE == 0;
constexpr bool kAnemometer = TRACKER_ROLE == 2;
constexpr bool kHasLocalAnemometer = kTransmitter || kAnemometer;
constexpr uint8_t kWindPin = A1;  // GP27, physical pin 32.
constexpr uint32_t kWindReadMs = 10;
constexpr uint32_t kWindSampleMs = 1000;
constexpr float kAdcReferenceV = 3.3f;
// Provisional slope fitted to the 2026-11-07 road test.
// Stationary zero measured on this RX with the final wiring.
constexpr float kWindSlope = 16.8f;
constexpr float kWindZeroV = 0.021f;
constexpr uint32_t kIntervalMs = 3000;
constexpr uint32_t kGpsBaud = 9600;
constexpr uint32_t kGpsFreshMs = 5000;
constexpr uint32_t kLinkTimeoutMs = 3 * kIntervalMs;
constexpr size_t kSequenceSize = 4;
constexpr size_t kStatusSize = 5;
constexpr size_t kPositionSize = 13;
// Extensions contain wind in 0.01 m/s and voltage in millivolts, little-endian.
constexpr size_t kWindExtensionSize = 4;
constexpr size_t kMaxPayloadSize = kPositionSize + kWindExtensionSize;
constexpr uint16_t kMissingWindValue = 0xFFFF;
constexpr uint32_t kWindFreshMs = 2 * kWindSampleMs;
constexpr uint8_t kDisplayHeight = 64;
enum GpsStatus : uint8_t { NoData, NoFix, Fix, Legacy };
constexpr uint8_t kPpsPin = 16;
constexpr uint8_t kLogButtonPin = 17;
constexpr char kCsvHeader[] = "rx_ms,seq,rssi_dbm,snr_db,quality_0_9,gps,lat,lon,distance_m,rx_lat,rx_lon,rx_altitude_m,wind_ms,wind_volts";
