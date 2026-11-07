#include "Tracker.h"

BatteryReading battery;

void pollBattery() {
  if (!kBatteryMonitorEnabled) {
    return;
  }
  static bool sampled = false;
  static uint32_t lastSampleMs = 0;
  static uint32_t lastReportMs = 0;
  const uint32_t now = millis();
  if (sampled && now - lastSampleMs < 1000) {
    return;
  }
  sampled = true;
  lastSampleMs = now;
  // Allow the ADC to settle after switching from the anemometer input.
  analogRead(kBatteryPin);
  delayMicroseconds(20);
  uint32_t sum = 0;
  for (unsigned i = 0; i < 16; ++i) {
    sum += analogRead(kBatteryPin);
  }
  battery.adcVolts = float(sum) / 16 * kAdcReferenceV / 4095;
  battery.volts = battery.adcVolts * kBatteryDividerRatio;
  battery.valid = battery.volts >= kBatteryMinValidV && battery.volts <= kBatteryMaxValidV;
  if (kHasLocalAnemometer) {
    // Discard the first conversion back on A1 before the next wind sample.
    analogRead(kWindPin);
    delayMicroseconds(20);
  }
  if (Serial && now - lastReportMs >= kIntervalMs) {
    lastReportMs = now;
    Serial.print("# battery_v=");
    if (battery.valid) {
      Serial.print(battery.volts, 3);
    } else {
      Serial.print("unavailable");
    }
    Serial.print(" battery_adc_v=");
    Serial.println(battery.adcVolts, 4);
  }
}
