#include "Tracker.h"

void showRadioStatus(uint32_t number, const char* status, int16_t error,
                     uint8_t quality) {
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
