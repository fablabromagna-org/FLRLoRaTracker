#include <Arduino.h>
#include <Adafruit_SSD1306.h>
#include <SPI.h>
#include <Wire.h>
#include <RadioLib.h>
#include <TinyGPSPlus.h>
#include <LittleFS.h>
#include <pico/time.h>

// Set true on the transmitter and false on the receiver.
constexpr bool kTransmitter = true;
constexpr uint32_t kIntervalMs = 3000;
constexpr uint32_t kGpsBaud = 9600;
constexpr uint32_t kGpsFreshMs = 5000;
constexpr uint32_t kLinkTimeoutMs = 3 * kIntervalMs;
constexpr size_t kSequenceSize = 4;
constexpr size_t kStatusSize = 5;
constexpr size_t kPositionSize = 13;
constexpr uint8_t kDisplayHeight = 64;
enum GpsStatus : uint8_t { NoData, NoFix, Fix, Legacy };
const char* const gpsLabels[] = {"no_data", "no_fix", "fix", "unknown"};
TinyGPSPlus gps;
auto& gpsSerial = kTransmitter ? Serial2 : Serial1;
constexpr uint8_t kPpsPin = 16;
constexpr uint8_t kLogButtonPin = 17;
constexpr char kCsvHeader[] = "rx_ms,seq,rssi_dbm,snr_db,quality_0_9,gps,lat,lon,distance_m,rx_lat,rx_lon,rx_altitude_m";
File sessionLog;
bool storageReady = false;
bool logError = false;
uint32_t lastLogFlushMs = 0;
volatile uint32_t ppsCount = 0;
bool gpsSeen = false;
uint32_t lastNmeaMs = 0;
uint32_t lastRxMs = 0;
bool linkActive = false;
bool hasReceivedPacket = false;
uint32_t lastReceivedSequence = 0;
uint32_t validPackets = 0;
uint32_t crcErrors = 0;
uint32_t invalidPackets = 0;
uint32_t observedIntervalMs = kIntervalMs;
uint8_t lastQuality = 0;
char lastRxMetrics[96] = {};

Adafruit_SSD1306* oled = nullptr;

Module module(3, 20, 15, 2, SPI1);
SX1262 radio(&module);

uint32_t sequence = 0;
uint32_t lastTxMs = 0;
volatile bool packetReady = false;
volatile uint64_t packetTimeMs = 0;

void showRadioStatus(uint32_t number, const char* status, int16_t error = RADIOLIB_ERR_NONE,
                     uint8_t quality = 0) {
  if (!oled) {
    return;
  }
  oled->clearDisplay();
  oled->setCursor(0, 0);
  oled->setTextSize(2);
  oled->print(kTransmitter ? "LoRa TX" : sessionLog ? "FLR REC" : "FLR RX");
  oled->setCursor(0, 16);
  // Scale down only when the full sequence would exceed the display width.
  const uint8_t numberSize = number < 100000 ? 4 :
                             number < 10000000 ? 3 : 2;
  const uint8_t rxNumberSize = number < 100000 ? 2 : 1;
  oled->setTextSize(kTransmitter ? numberSize : rxNumberSize);
  oled->print(number);
  if (!kTransmitter) {
    oled->print("/100");
    oled->setTextSize(2);
    oled->setCursor(116, 16);
    oled->print(quality > 0 ? quality - 1 : 0);
  }
  oled->setCursor(0, kTransmitter ? 48 : 32);
  oled->setTextSize(1);
  if (!kTransmitter) {
    if (logError) {
      oled->setCursor(110, 8);
      oled->print("ERR");
    }
    oled->setCursor(0, 32);
  }
  oled->print(status);
  if (error != RADIOLIB_ERR_NONE) {
    oled->print(' ');
    oled->print(error);
  }
  oled->display();
}

void initDisplay() {
  // Accept both header pins 6/7 and GPIO numbers GP6/GP7.
  TwoWire* buses[] = {&Wire, &Wire1};
  for (size_t i = 0; i < 2; ++i) {
    TwoWire& bus = *buses[i];
    bus.setSDA(4 + 2 * i);
    bus.setSCL(5 + 2 * i);
    bus.begin();
    for (uint8_t address : {0x3C, 0x3D}) {
      bus.beginTransmission(address);
      if (bus.endTransmission() == 0) {
        static Adafruit_SSD1306 display(128, kDisplayHeight, &bus, -1);
        if (display.begin(SSD1306_SWITCHCAPVCC, address, false, false)) {
          oled = &display;
          oled->setTextColor(SSD1306_WHITE);
        }
        return;
      }
    }
    bus.end();
  }
}

void onPacket() {
  packetTimeMs = time_us_64() / 1000;
  packetReady = true;
}

void onPps() {
  ++ppsCount;
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

void writeLog(const char* line) {
  if (sessionLog && sessionLog.println(line) != strlen(line) + 2) {
    sessionLog.close();
    logError = true;
    Serial.println("# log_write_error");
  }
}

void pollLogButton() {
  static bool raw = HIGH;
  static bool stable = HIGH;
  static uint32_t changedAt = 0;
  const bool level = digitalRead(kLogButtonPin);
  const uint32_t now = millis();
  if (level != raw) {
    raw = level;
    changedAt = now;
  }
  if (stable == raw || now - changedAt < 40) {
    return;
  }
  stable = raw;
  if (stable == HIGH) {
    return;
  }
  if (sessionLog) {
    sessionLog.close();
    Serial.println("# log_stopped");
    showRadioStatus(lastReceivedSequence, "Log saved");
    return;
  }
  if (storageReady) {
    char path[24];
    for (unsigned id = 1; id <= 9999; ++id) {
      snprintf(path, sizeof(path), "/session%04u.csv", id);
      if (!LittleFS.exists(path)) {
        sessionLog = LittleFS.open(path, "w");
        if (sessionLog) {
          logError = false;
          writeLog(kCsvHeader);
          if (sessionLog) {
            sessionLog.flush();
            lastLogFlushMs = now;
            Serial.print("# log_started ");
            Serial.println(path);
            showRadioStatus(lastReceivedSequence, "Log started");
            return;
          }
        }
        break;
      }
    }
  }
  logError = true;
  Serial.println("# log_open_error");
  showRadioStatus(lastReceivedSequence, "Log unavailable");
}

void pollLogCommands() {
  static char command[32];
  static size_t length = 0;
  static bool overflow = false;
  while (Serial.available()) {
    const char ch = Serial.read();
    if (ch != '\r' && ch != '\n') {
      if (length < sizeof(command) - 1) {
        command[length++] = ch;
      } else {
        overflow = true;
      }
      continue;
    }
    command[length] = '\0';
    if (!overflow && length != 0) {
      if (strcmp(command, "STATUS") == 0) {
        Serial.println(sessionLog ? "# recording=1" : "# recording=0");
      } else if (!storageReady || sessionLog) {
        Serial.println("# stop recording first or check storage");
      } else if (strcmp(command, "LIST") == 0) {
        Dir dir = LittleFS.openDir("/");
        while (dir.next()) {
          Serial.print("# ");
          Serial.print(dir.fileName());
          Serial.print(' ');
          Serial.println(dir.fileSize());
        }
        Serial.println("# END LIST");
      } else if (strncmp(command, "GET /session", 12) == 0 &&
                 strlen(command) == 20 &&
                 strspn(command + 12, "0123456789") == 4 &&
                 strcmp(command + 16, ".csv") == 0) {
        File input = LittleFS.open(command + 4, "r");
        if (input) {
          Serial.println("# BEGIN CSV");
          uint8_t buffer[128];
          while (Serial && input.available()) {
            const size_t count = input.read(buffer, sizeof(buffer));
            if (count == 0 || Serial.write(buffer, count) != count) {
              break;
            }
          }
          Serial.println("# END CSV");
        } else {
          Serial.println("# file not found");
        }
      } else {
        Serial.println("# commands: LIST | GET /session0001.csv");
      }
    }
    length = 0;
    overflow = false;
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
  if (!linkActive) {
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

  if (oled) {
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

  if (sessionLog) {
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

void loop() {
  pollGps();
  if (kTransmitter) {
    transmitPacket();
  } else {
    // Show that RX is ready even if no LoRa packets have arrived yet.
    static bool headerWritten = false;
    if (!Serial) {
      headerWritten = false;
    } else if (!headerWritten) {
      Serial.println(kCsvHeader);
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
