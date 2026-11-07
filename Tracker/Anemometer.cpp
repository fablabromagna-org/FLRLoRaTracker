#include "Tracker.h"

WindSample wind;

const char* sessionHeader() {
  return kAnemometer
      ? "sample_ms,window_ms,adc_samples,adc_mean,adc_min,adc_max,volts,wind_ms_provisional,"
        "gps_status,fix_age_ms,speed_age_ms,gps_kmh,gps_ms,course_deg,lat,lon,altitude_m,"
        "hdop,satellites,utc,pps_count,radio_seq,radio_age_ms,quality_0_9"
      : kCsvHeader;
}

void showWindStatus() {
  if (!oled) {
    return;
  }
  oled->clearDisplay();
  oled->setTextSize(2);
  oled->setCursor(0, 0);
  oled->print(sessionLog ? "FLR REC" : "FLR RX");
  oled->setCursor(0, 16);
  oled->setTextSize(lastReceivedSequence < 10000000 ? 2 : 1);
  oled->print(lastReceivedSequence);
  oled->print('/');
  if (wind.count) {
    oled->print(wind.metersPerSecond, 0);
  } else {
    oled->print("--");
  }
  oled->setTextSize(2);
  oled->setCursor(116, 16);
  oled->print(linkActive && lastQuality ? lastQuality - 1 : 0);
  oled->setTextSize(1);
  oled->setCursor(0, 32);
  oled->print("Wind ");
  oled->print(wind.metersPerSecond, 2);
  oled->println(" m/s");
  oled->print("GPS ");
  const bool speedValid = localGpsStatus() == Fix && gps.speed.isValid() &&
                          gps.speed.age() <= kGpsFreshMs;
  if (speedValid) {
    oled->print(gps.speed.kmph(), 1);
  } else {
    oled->print("--");
  }
  oled->println(" km/h");
  oled->print(gpsLabels[localGpsStatus()]);
  oled->print(" Sat ");
  if (gps.satellites.isValid() && gps.satellites.age() <= kGpsFreshMs) {
    oled->println(gps.satellites.value());
  } else {
    oled->println("--");
  }
  oled->print("ADC ");
  oled->print(wind.volts, 3);
  oled->print("V");
  if (logError) {
    oled->print(" LOG ERR");
  } else if (wind.adcMax == 4095) {
    oled->print(" SAT");
  }
  oled->display();
}

static void emitWindSample() {
  const GpsStatus status = localGpsStatus();
  const bool fix = status == Fix;
  const bool speedValid = fix && gps.speed.isValid() && gps.speed.age() <= kGpsFreshMs;
  const bool courseValid = fix && gps.course.isValid() && gps.course.age() <= kGpsFreshMs;
  const bool altitudeValid = fix && gps.altitude.isValid() && gps.altitude.age() <= kGpsFreshMs;
  const bool hdopValid = gps.hdop.isValid() && gps.hdop.age() <= kGpsFreshMs;
  const bool satsValid = gps.satellites.isValid() && gps.satellites.age() <= kGpsFreshMs;
  char utc[24] = {};
  if (fix && gps.date.isValid() && gps.date.age() <= kGpsFreshMs &&
      gps.time.isValid() && gps.time.age() <= kGpsFreshMs) {
    snprintf(utc, sizeof(utc), "%04u-%02u-%02uT%02u:%02u:%02uZ",
             unsigned(gps.date.year()), unsigned(gps.date.month()), unsigned(gps.date.day()),
             unsigned(gps.time.hour()), unsigned(gps.time.minute()), unsigned(gps.time.second()));
  }
  // Keep unavailable GPS fields empty. Zero is a valid stationary speed.
  const String fixAge = fix ? String(gps.location.age()) : String();
  const String speedAge = speedValid ? String(gps.speed.age()) : String();
  const String kmh = speedValid ? String(gps.speed.kmph(), 3) : String();
  const String ms = speedValid ? String(gps.speed.mps(), 3) : String();
  const String course = courseValid ? String(gps.course.deg(), 2) : String();
  const String lat = fix ? String(gps.location.lat(), 6) : String();
  const String lon = fix ? String(gps.location.lng(), 6) : String();
  const String altitude = altitudeValid ? String(gps.altitude.meters(), 2) : String();
  const String hdop = hdopValid ? String(gps.hdop.hdop(), 2) : String();
  const String sats = satsValid ? String(gps.satellites.value()) : String();
  const String radioSeq = hasReceivedPacket ? String(lastReceivedSequence) : String();
  const String radioAge = hasReceivedPacket ? String(millis() - lastRxMs) : String();
  char line[512];
  const int length = snprintf(
      line, sizeof(line),
      "%llu,%lu,%lu,%.2f,%u,%u,%.5f,%.3f,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%lu,%s,%s,%u",
      static_cast<unsigned long long>(wind.sampleMs),
      static_cast<unsigned long>(wind.windowMs),
      static_cast<unsigned long>(wind.adcSamples),
      double(wind.adcMean), unsigned(wind.adcMin), unsigned(wind.adcMax),
      double(wind.volts), double(wind.metersPerSecond), gpsLabels[status],
      fixAge.c_str(), speedAge.c_str(), kmh.c_str(), ms.c_str(), course.c_str(),
      lat.c_str(), lon.c_str(), altitude.c_str(), hdop.c_str(), sats.c_str(), utc,
      static_cast<unsigned long>(ppsCount), radioSeq.c_str(), radioAge.c_str(),
      unsigned(linkActive && lastQuality ? lastQuality - 1 : 0));
  if (length < 0 || size_t(length) >= sizeof(line)) {
    return;
  }
  writeLog(line);
  if (Serial) {
    Serial.print("# wind=");
    Serial.println(line);
  }
}

void pollAnemometer() {
  static uint32_t lastReadMs = 0;
  static uint32_t windowStartMs = millis();
  static uint32_t sum = 0;
  static uint32_t samples = 0;
  static uint16_t minimum = 4095;
  static uint16_t maximum = 0;
  const uint32_t now = millis();
  if (now - lastReadMs >= kWindReadMs) {
    lastReadMs = now;
    const uint16_t value = analogRead(kWindPin);
    sum += value;
    ++samples;
    minimum = min(minimum, value);
    maximum = max(maximum, value);
  }
  if (now - windowStartMs < kWindSampleMs || samples == 0) {
    return;
  }
  wind.sampleMs = time_us_64() / 1000;
  ++wind.count;
  wind.windowMs = now - windowStartMs;
  wind.adcSamples = samples;
  wind.adcMin = minimum;
  wind.adcMax = maximum;
  wind.adcMean = float(sum) / samples;
  wind.volts = wind.adcMean * kAdcReferenceV / 4095.0f;
  wind.metersPerSecond = max(0.0f, kWindSlope * (wind.volts - kWindZeroV));
  windowStartMs = now;
  sum = 0;
  samples = 0;
  minimum = 4095;
  maximum = 0;
  emitWindSample();
  showWindStatus();
}
