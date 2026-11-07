#include "Tracker.h"

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
