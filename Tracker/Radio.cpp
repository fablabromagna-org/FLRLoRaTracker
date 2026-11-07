#include "Tracker.h"

void onPacket() {
  packetTimeMs = time_us_64() / 1000;
  packetReady = true;
}

void checkRadio(int16_t status) {
  if (status != RADIOLIB_ERR_NONE) {
    showRadioStatus(sequence, "Radio error", status);
    for (;;) {
      Serial.print("# radio_error=");
      Serial.println(status);
      delay(1000);
    }
  }
}

void writeUint32(uint8_t* bytes, uint32_t value) {
  for (size_t i = 0; i < 4; ++i) {
    bytes[i] = static_cast<uint8_t>(value >> (8 * i));
  }
}

uint32_t readUint32(const uint8_t* bytes) {
  uint32_t value = 0;
  for (size_t i = 0; i < 4; ++i) {
    value |= static_cast<uint32_t>(bytes[i]) << (8 * i);
  }
  return value;
}

uint8_t radioQuality(float rssi, float snr) {
  // Map both measurements to 0..1 and use the weaker of the two.
  const float strength = constrain((rssi + 125.0f) / 60.0f, 0.0f, 1.0f);
  const float clarity = constrain((snr + 12.5f) / 22.5f, 0.0f, 1.0f);
  return 1 + static_cast<uint8_t>(9 * min(strength, clarity) + 0.5f);
}

void transmitPacket() {
  const uint32_t now = millis();
  if (now - lastTxMs < kIntervalMs) {
    return;
  }
  lastTxMs = now;
  ++sequence;

  const GpsStatus gpsStatus = localGpsStatus();
  uint8_t payload[kPositionSize];
  writeUint32(payload, sequence);
  payload[4] = gpsStatus;
  if (gpsStatus == Fix) {
    // Store coordinates as unsigned, offset microdegrees.
    writeUint32(payload + 5, (gps.location.lat() + 90.0) * 1000000 + 0.5);
    writeUint32(payload + 9, (gps.location.lng() + 180.0) * 1000000 + 0.5);
  }
  const int16_t status = radio.transmit(payload, gpsStatus == Fix ? kPositionSize : kStatusSize);
  if (status == RADIOLIB_ERR_NONE) {
    char displayStatus[40];
    snprintf(displayStatus, sizeof(displayStatus), "Sent OK\nGPS %s", gpsLabels[gpsStatus]);
    showRadioStatus(sequence, displayStatus);
    Serial.print("# tx_seq=");
    Serial.print(sequence);
    Serial.print(" gps=");
    Serial.print(gpsLabels[gpsStatus]);
    Serial.print(" chars=");
    Serial.println(gps.charsProcessed());
  } else {
    showRadioStatus(sequence, "TX error", status);
    Serial.print("# tx_error=");
    Serial.println(status);
  }
}

void printPacket(Print& output, uint64_t receivedMs, uint32_t receivedSequence,
                 float rssi, float snr, uint8_t quality, GpsStatus gpsStatus,
                 double latitude, double longitude, bool hasDistance, double distanceM) {
  char timestamp[24];
  snprintf(timestamp, sizeof(timestamp), "%llu",
           static_cast<unsigned long long>(receivedMs));
  output.print(timestamp);
  output.print(',');
  output.print(receivedSequence);
  output.print(',');
  output.print(rssi, 1);
  output.print(',');
  output.print(snr, 2);
  output.print(',');
  output.print(quality > 0 ? quality - 1 : 0);
  output.print(',');
  output.print(gpsLabels[gpsStatus]);
  output.print(',');
  if (gpsStatus == Fix) {
    output.print(latitude, 6);
  }
  output.print(',');
  if (gpsStatus == Fix) {
    output.print(longitude, 6);
  }
  output.print(',');
  if (hasDistance) {
    output.print(distanceM, 1);
  }
  output.print(',');
  if (localGpsStatus() == Fix) {
    output.print(gps.location.lat(), 6);
    output.print(',');
    output.print(gps.location.lng(), 6);
    output.print(',');
    if (gps.altitude.isValid() && gps.altitude.age() <= kGpsFreshMs) {
      output.print(gps.altitude.meters(), 1);
    }
  } else {
    output.print(",,");
  }
  output.println();
}

void receivePacket() {
  noInterrupts();
  const bool ready = packetReady;
  const uint64_t receivedMs = packetTimeMs;
  packetReady = false;
  interrupts();
  if (!ready) {
    return;
  }

  uint8_t payload[kPositionSize];
  const size_t length = radio.getPacketLength();
  const int16_t status = radio.readData(payload, sizeof(payload));
  const float rssi = radio.getRSSI();
  const float snr = radio.getSNR();
  checkRadio(radio.startReceive());

  if (status == RADIOLIB_ERR_CRC_MISMATCH) {
    ++crcErrors;
    return;
  }
  if (status != RADIOLIB_ERR_NONE ||
      (length != kSequenceSize && length != kStatusSize && length != kPositionSize)) {
    ++invalidPackets;
    return;
  }

  GpsStatus gpsStatus = Legacy;
  double latitude = 0;
  double longitude = 0;
  if (length == kPositionSize && payload[4] == Fix) {
    const uint32_t lat = readUint32(payload + 5);
    const uint32_t lon = readUint32(payload + 9);
    if (lat > 180000000 || lon > 360000000) {
      ++invalidPackets;
      return;
    }
    gpsStatus = Fix;
    latitude = lat / 1000000.0 - 90.0;
    longitude = lon / 1000000.0 - 180.0;
  } else if (length == kStatusSize && payload[4] <= NoFix) {
    gpsStatus = static_cast<GpsStatus>(payload[4]);
  } else if (length != kSequenceSize) {
    ++invalidPackets;
    return;
  }
  const uint32_t receivedSequence = readUint32(payload);
  const uint8_t quality = radioQuality(rssi, snr);
  const GpsStatus rxGpsStatus = localGpsStatus();
  const bool hasDistance = gpsStatus == Fix && rxGpsStatus == Fix;
  const double distanceM = hasDistance
      ? TinyGPSPlus::distanceBetween(gps.location.lat(), gps.location.lng(), latitude, longitude)
      : 0;
  const uint32_t now = millis();
  if (hasReceivedPacket && receivedSequence == lastReceivedSequence + 1) {
    const uint32_t interval = now - lastRxMs;
    // Learn the interval only from consecutive sequences, within five minutes.
    if (interval > 0 && interval <= 300000) {
      observedIntervalMs = interval;
    }
  }
  lastRxMs = now;
  lastReceivedSequence = receivedSequence;
  hasReceivedPacket = true;
  ++validPackets;
  lastQuality = quality;
  linkActive = true;

  if (oled && !kAnemometer) {
    char metrics[96];
    const int used = snprintf(metrics, sizeof(metrics), "%.0f dBm / %.1f dB\n",
                              static_cast<double>(rssi), static_cast<double>(snr));
    if (gpsStatus == Fix) {
      snprintf(metrics + used, sizeof(metrics) - used, "Lat %.6f\nLon %.6f", latitude, longitude);
      const size_t end = strlen(metrics);
      if (hasDistance) {
        snprintf(metrics + end, sizeof(metrics) - end, "\nDist %.0f m", distanceM);
      } else {
        snprintf(metrics + end, sizeof(metrics) - end, "\nRX GPS %s",
                 gpsLabels[rxGpsStatus]);
      }
    } else {
      snprintf(metrics + used, sizeof(metrics) - used, "TX GPS %s\nRX GPS %s",
               gpsLabels[gpsStatus], gpsLabels[rxGpsStatus]);
    }
    snprintf(lastRxMetrics, sizeof(lastRxMetrics), "%s", metrics);
    showRadioStatus(receivedSequence, lastRxMetrics, RADIOLIB_ERR_NONE, quality);
  }

  if (sessionLog && !kAnemometer) {
    printPacket(sessionLog, receivedMs, receivedSequence, rssi, snr, quality,
                gpsStatus, latitude, longitude, hasDistance, distanceM);
    if (sessionLog.getWriteError()) {
      sessionLog.close();
      logError = true;
      Serial.println("# log_write_error");
    }
  }
  if (Serial) {
    printPacket(Serial, receivedMs, receivedSequence, rssi, snr, quality,
                gpsStatus, latitude, longitude, hasDistance, distanceM);
  }
}
