#include "Tracker.h"

String gpsUtc() {
  if (gps.date.isValid() && gps.time.isValid() &&
      gps.date.age() <= kGpsFreshMs && gps.time.age() <= kGpsFreshMs) {
    char utc[24];
    snprintf(utc, sizeof(utc), "%04u-%02u-%02uT%02u:%02u:%02uZ",
             unsigned(gps.date.year()), unsigned(gps.date.month()), unsigned(gps.date.day()),
             unsigned(gps.time.hour()), unsigned(gps.time.minute()), unsigned(gps.time.second()));
    return String(utc);
  }
  return String();
}

void pollRxLog() {
  static uint32_t lastSampleMs = 0;
  const uint32_t now = millis();
  if (!sessionLog || kAnemometer || now - lastSampleMs < 1000) {
    return;
  }
  lastSampleMs = now;
  const bool fix = localGpsStatus() == Fix;
  const String lat = fix ? String(gps.location.lat(), 6) : String();
  const String lon = fix ? String(gps.location.lng(), 6) : String();
  const String altitude = fix && gps.altitude.isValid() && gps.altitude.age() <= kGpsFreshMs
      ? String(gps.altitude.meters(), 1) : String();
  char line[160];
  snprintf(line, sizeof(line), "%llu,,,,,,,,,%s,%s,%s,,,gps,",
           static_cast<unsigned long long>(time_us_64() / 1000),
           lat.c_str(), lon.c_str(), altitude.c_str());
  String record(line);
  record += gpsUtc();
  record += ',';
  if (linkActive && receivedBatteryValid) {
    record += String(receivedBatteryVolts, 3);
  }
  record += ',';
  if (battery.valid) {
    record += String(battery.volts, 3);
  }
  writeLog(record.c_str());
}

static bool sessionPath(const char* path) {
  return strlen(path) == 16 && strncmp(path, "/session", 8) == 0 &&
         strspn(path + 8, "0123456789") == 4 && strcmp(path + 12, ".csv") == 0;
}

static uint32_t fileChecksum(File& file) {
  uint32_t crc = 0xFFFFFFFF;
  uint8_t buffer[128];
  while (file.available()) {
    const size_t count = file.read(buffer, sizeof(buffer));
    if (count == 0) {
      break;
    }
    for (size_t index = 0; index < count; ++index) {
      crc ^= buffer[index];
      for (unsigned bit = 0; bit < 8; ++bit) {
        crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
      }
    }
    yield();
  }
  return ~crc;
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
          writeLog(sessionHeader());
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
  static char command[96];
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
      } else if (strcmp(command, "MEM") == 0) {
        FSInfo info;
        if (LittleFS.info(info)) {
          Serial.printf("# MEM %lu %lu\n", (unsigned long)info.totalBytes,
                        (unsigned long)info.usedBytes);
        } else {
          Serial.println("# memory_error");
        }
      } else if (strncmp(command, "CHECK ", 6) == 0 && sessionPath(command + 6)) {
        File input = LittleFS.open(command + 6, "r");
        if (input) {
          const unsigned long size = input.size();
          const unsigned long crc = fileChecksum(input);
          input.close();
          Serial.printf("# CHECK %s %lu %08lx\n", command + 6, size, crc);
        } else {
          Serial.println("# file not found");
        }
      } else if (strncmp(command, "DEL ", 4) == 0) {
        char path[24], extra;
        unsigned long expectedCrc, expectedSize;
        if (sscanf(command + 4, "%23s %lx %lu %c", path, &expectedCrc, &expectedSize,
                   &extra) == 3 && sessionPath(path)) {
          File input = LittleFS.open(path, "r");
          if (input) {
            const bool sizeMatches = input.size() == expectedSize;
            const bool matches = sizeMatches && fileChecksum(input) == expectedCrc;
            input.close();
            if (matches && LittleFS.remove(path)) {
              Serial.printf("# DELETED %s\n", path);
            } else {
              Serial.println("# delete_error");
            }
          } else {
            Serial.println("# file not found");
          }
        } else {
          Serial.println("# delete_error");
        }
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
