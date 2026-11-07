#include "Tracker.h"

void onPps() {
  ++ppsCount;
}

void pollGps() {
  while (gpsSerial.available()) {
    if (gps.encode(gpsSerial.read())) {
      gpsSeen = true;
      lastNmeaMs = millis();
    }
  }
}

GpsStatus localGpsStatus() {
  if (!gpsSeen || millis() - lastNmeaMs > kGpsFreshMs) {
    return NoData;
  }
  return gps.location.isValid() && gps.location.age() <= kGpsFreshMs ? Fix : NoFix;
}

void reportRxGps() {
  static uint32_t lastReportMs = 0;
  static uint32_t previousPpsCount = 0;
  const uint32_t now = millis();
  if (now - lastReportMs < kIntervalMs) {
    return;
  }
  lastReportMs = now;
  const uint32_t pulses = ppsCount;
  const GpsStatus status = localGpsStatus();
  if (kAnemometer) {
    showWindStatus();
  } else if (!linkActive) {
    char message[64];
    if (hasReceivedPacket) {
      snprintf(message, sizeof(message), "No RX for %lu s\nRX GPS %s",
               static_cast<unsigned long>((now - lastRxMs) / 1000), gpsLabels[status]);
    } else {
      snprintf(message, sizeof(message), "Waiting for LoRa\nRX GPS %s", gpsLabels[status]);
    }
    showRadioStatus(lastReceivedSequence, message);
  } else {
    showRadioStatus(lastReceivedSequence, lastRxMetrics, RADIOLIB_ERR_NONE, lastQuality);
  }
  if (Serial) {
    Serial.print("# rx_gps=");
    Serial.print(gpsLabels[status]);
    Serial.print(" chars=");
    Serial.print(gps.charsProcessed());
    Serial.print(" nmea_ok=");
    Serial.print(gps.passedChecksum());
    Serial.print(" pps_3s=");
    Serial.print(pulses - previousPpsCount);
    if (gps.satellites.isValid() && gps.satellites.age() <= kGpsFreshMs) {
      Serial.print(" satellites=");
      Serial.print(gps.satellites.value());
    }
    if (gps.hdop.isValid() && gps.hdop.age() <= kGpsFreshMs) {
      Serial.print(" hdop=");
      Serial.print(gps.hdop.hdop(), 2);
    }
    if (gps.time.isValid() && gps.time.age() <= kGpsFreshMs) {
      char utc[10];
      snprintf(utc, sizeof(utc), "%02u:%02u:%02u", unsigned(gps.time.hour()),
               unsigned(gps.time.minute()), unsigned(gps.time.second()));
      Serial.print(" utc_nmea=");
      Serial.print(utc);
    }
    if (status == Fix) {
      Serial.print(" lat=");
      Serial.print(gps.location.lat(), 6);
      Serial.print(" lon=");
      Serial.print(gps.location.lng(), 6);
      Serial.print(" fix_age_ms=");
      Serial.print(gps.location.age());
      if (gps.altitude.isValid() && gps.altitude.age() <= kGpsFreshMs) {
        Serial.print(" altitude_m=");
        Serial.print(gps.altitude.meters(), 1);
      }
      if (gps.speed.isValid() && gps.speed.age() <= kGpsFreshMs) {
        Serial.print(" speed_kmh=");
        Serial.print(gps.speed.kmph(), 1);
      }
      if (gps.course.isValid() && gps.course.age() <= kGpsFreshMs) {
        Serial.print(" course_deg=");
        Serial.print(gps.course.deg(), 1);
      }
    }
    Serial.println();
    Serial.print("# rx_radio valid=");
    Serial.print(validPackets);
    Serial.print(" crc_errors=");
    Serial.print(crcErrors);
    Serial.print(" invalid=");
    Serial.print(invalidPackets);
    Serial.print(" last_seq=");
    Serial.print(lastReceivedSequence);
    Serial.print(" age_ms=");
    if (hasReceivedPacket) {
      Serial.print(now - lastRxMs);
    } else {
      Serial.print("none");
    }
    Serial.print(" irq=");
    Serial.print(radio.getIrqFlags(), HEX);
    Serial.print(" dio1=");
    Serial.print(digitalRead(20));
    Serial.print(" interval_ms=");
    Serial.print(observedIntervalMs);
    Serial.println();
  }
  previousPpsCount = pulses;
}
