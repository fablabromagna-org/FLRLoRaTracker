#pragma once
#include "Config.h"
#include <Arduino.h>
#include <Adafruit_SSD1306.h>
#include <SPI.h>
#include <Wire.h>
#include <RadioLib.h>
#include <TinyGPSPlus.h>
#include <LittleFS.h>
#include <pico/time.h>

extern const char* const gpsLabels[];
extern TinyGPSPlus gps;
extern SerialUART& gpsSerial;
extern File sessionLog;
extern bool storageReady;
extern bool logError;
extern uint32_t lastLogFlushMs;
extern volatile uint32_t ppsCount;
extern bool gpsSeen;
extern uint32_t lastNmeaMs;
extern uint32_t lastRxMs;
extern bool linkActive;
extern bool hasReceivedPacket;
extern uint32_t lastReceivedSequence;
extern uint32_t validPackets;
extern uint32_t crcErrors;
extern uint32_t invalidPackets;
extern uint32_t observedIntervalMs;
extern uint8_t lastQuality;
extern bool receivedWindValid;
extern bool receivedVoltageValid;
extern float receivedWindMs;
extern float receivedWindVolts;
extern int16_t lastTxStatus;
extern bool receivedBatteryValid;
extern float receivedBatteryVolts;
extern char lastRxMetrics[96];
extern Adafruit_SSD1306* oled;
extern Module module;
extern SX1262 radio;
extern uint32_t sequence;
extern uint32_t lastTxMs;
extern volatile bool packetReady;
extern volatile uint64_t packetTimeMs;

void showRadioStatus(uint32_t number, const char* status, int16_t error = RADIOLIB_ERR_NONE,
                     uint8_t quality = 0);
void initDisplay();
void onPacket();
void onPps();
void checkRadio(int16_t status);
void setup();
void writeLog(const char* line);
void pollLogButton();
void pollLogCommands();
void pollRxLog();
String gpsUtc();
void initLinkAlerts();
void pollLinkAlerts();
void writeUint32(uint8_t* bytes, uint32_t value);
uint32_t readUint32(const uint8_t* bytes);
uint8_t radioQuality(float rssi, float snr);
void pollGps();
GpsStatus localGpsStatus();
void reportRxGps();
void transmitPacket();
void printPacket(Print& output, uint64_t receivedMs, uint32_t receivedSequence,
                 float rssi, float snr, uint8_t quality, GpsStatus gpsStatus,
                 double latitude, double longitude, bool hasDistance, double distanceM);
void receivePacket();
void loop();

struct WindSample {
  uint64_t sampleMs = 0;
  uint32_t count = 0;
  uint32_t windowMs = 0;
  uint32_t adcSamples = 0;
  uint16_t adcMin = 0;
  uint16_t adcMax = 0;
  float adcMean = 0;
  float volts = 0;
  float metersPerSecond = 0;
};
extern WindSample wind;
const char* sessionHeader();
void pollAnemometer();
void showWindStatus();
bool localWindValid();

struct BatteryReading {
  bool valid = false;
  float volts = 0;
  float adcVolts = 0;
};
extern BatteryReading battery;
void pollBattery();
