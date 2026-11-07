#include "Tracker.h"

const char* const gpsLabels[] = {"no_data", "no_fix", "fix", "unknown"};
TinyGPSPlus gps;
SerialUART& gpsSerial = kTransmitter ? Serial2 : Serial1;
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
