#include "Tracker.h"

void setup() {
  Serial.begin(115200);
  initDisplay();
  showRadioStatus(0, "Starting...");
  SPI1.setSCK(10);
  SPI1.setTX(11);
  SPI1.setRX(12);
  SPI1.begin();

  // MHz, kHz, SF, CR denominator, sync word, dBm, preamble, TCXO V.
  checkRadio(radio.begin(869.525, 125.0, 9, 5,
                        RADIOLIB_SX126X_SYNC_WORD_PRIVATE, 14, 8, 1.7));
  checkRadio(radio.setCRC(2));

  gpsSerial.setTX(kTransmitter ? 8 : 0);
  gpsSerial.setRX(kTransmitter ? 9 : 1);
  gpsSerial.setFIFOSize(512);
  gpsSerial.begin(kGpsBaud);
  if (kHasLocalAnemometer) {
    analogReadResolution(12);
  }
  if (kTransmitter) {
    lastTxMs = millis() - kIntervalMs;
  } else {
    pinMode(kLogButtonPin, INPUT_PULLUP);
    storageReady = LittleFS.begin();
    logError = !storageReady;
    pinMode(kPpsPin, INPUT_PULLDOWN);
    attachInterrupt(digitalPinToInterrupt(kPpsPin), onPps, RISING);
    radio.setPacketReceivedAction(onPacket);
    checkRadio(radio.startReceive());
    showRadioStatus(0, "Waiting for packets");
  }
}

void loop() {
  pollGps();
  if (kHasLocalAnemometer) {
    pollAnemometer();
  }
  if (kTransmitter) {
    transmitPacket();
  } else {
    // Show that RX is ready even if no LoRa packets have arrived yet.
    static bool headerWritten = false;
    if (!Serial) {
      headerWritten = false;
    } else if (!headerWritten) {
      Serial.println(kCsvHeader);
      if (kAnemometer) {
        Serial.print("# wind_header=");
        Serial.println(sessionHeader());
      }
      headerWritten = true;
    }
    pollLogButton();
    pollLogCommands();
    receivePacket();
    if (sessionLog && millis() - lastLogFlushMs >= 15000) {
      sessionLog.flush();
      lastLogFlushMs = millis();
    }
    const uint32_t timeoutMs = max(kLinkTimeoutMs, 3 * observedIntervalMs);
    if (linkActive && millis() - lastRxMs >= timeoutMs) {
      linkActive = false;
    }
    reportRxGps();
  }
  delay(1);
}
