#include "Tracker.h"

void initLinkAlerts() {
  if (kRgbEnabled) {
    for (uint8_t pin : {kLedRedPin, kLedGreenPin, kLedBluePin}) {
      pinMode(pin, OUTPUT);
      digitalWrite(pin, LOW);
    }
  }
  if (kBeeperEnabled) {
    pinMode(kBeeperPin, OUTPUT);
    digitalWrite(kBeeperPin, LOW);
  }
}

void pollLinkAlerts() {
  static bool previousLink = false;
  static bool previouslyReceived = false;
  static bool secondBeepPending = false;
  static uint32_t lostAt = 0;
  const uint32_t now = millis();
  if (kRgbEnabled) {
    const uint8_t quality = lastQuality > 0 ? lastQuality - 1 : 0;
    const bool lost = hasReceivedPacket && !linkActive;
    const bool blink = (now / 400) % 2 == 0;
    digitalWrite(kLedRedPin, linkActive ? quality < 6 : lost && blink);
    digitalWrite(kLedGreenPin, linkActive && quality >= 2);
    digitalWrite(kLedBluePin, !hasReceivedPacket && blink);
  }
  if (linkActive != previousLink) {
    secondBeepPending = false;
    if (kBeeperEnabled && !linkActive && previouslyReceived) {
      tone(kBeeperPin, 900, 150);
      lostAt = now;
      secondBeepPending = true;
    } else if (kBeeperEnabled && linkActive && previouslyReceived) {
      tone(kBeeperPin, 1800, 100);
    }
    previousLink = linkActive;
  }
  if (kBeeperEnabled && secondBeepPending && now - lostAt >= 300) {
    tone(kBeeperPin, 900, 150);
    secondBeepPending = false;
  }
  previouslyReceived = hasReceivedPacket;
}
