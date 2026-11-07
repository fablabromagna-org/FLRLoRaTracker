"""Import recordings stored by the Pico, including older nine-column CSV files."""
import csv
import math
from datetime import datetime, timedelta, timezone


def read_recording(path):
    from tracker_client import coordinates, distance

    segments, samples = [[]], []
    previous_ms = None
    last = None
    last_sample = None
    has_rx = False
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        wind_format = "sample_ms" in columns
        required = ({"sample_ms", "gps_status", "lat", "lon", "quality_0_9"}
                    if wind_format else {"rx_ms", "seq", "gps", "lat", "lon"})
        if not required <= columns:
            raise ValueError("Formato CSV non riconosciuto. Colonne mancanti: " +
                             ", ".join(sorted(required - columns)))
        clock_origin = datetime(1970, 1, 1, tzinfo=timezone.utc)
        for row in reader:
            try:
                ms = int(row["sample_ms"] if wind_format else row["rx_ms"])
                if row.get("utc"):
                    utc = datetime.fromisoformat(row["utc"].replace("Z", "+00:00"))
                    if utc.tzinfo is None:
                        raise ValueError("Orario UTC senza fuso orario")
                    clock_origin = utc - timedelta(milliseconds=ms)
                gps_only = row.get("record_type") == "gps"
                quality = None if gps_only else int(row.get("quality_0_9", row.get("quality", "")))
                if not gps_only and "quality_0_9" not in row:
                    quality = max(0, quality - 1)
                if not gps_only and not 0 <= quality <= 9:
                    raise ValueError("Segnale fuori intervallo")
                rx = wind_format or bool(row.get("rx_lat") and row.get("rx_lon"))
                if wind_format:
                    has_rx = True
                    if row["gps_status"] != "fix":
                        continue
                    position = coordinates(row["lat"], row["lon"])
                elif rx:
                    position = coordinates(row["rx_lat"], row["rx_lon"])
                    has_rx = True
                elif "rx_lat" in row:
                    continue
                elif row.get("gps") == "fix":
                    position = coordinates(row["lat"], row["lon"])
                else:
                    continue
                altitude_text = row.get("altitude_m") if wind_format else row.get("rx_altitude_m")
                altitude = float(altitude_text) if altitude_text else None
                if altitude is not None and not math.isfinite(altitude):
                    altitude = None
                stamp = clock_origin + timedelta(milliseconds=ms)
                sequence_text = row.get("radio_seq") if wind_format else row["seq"]
                sequence = int(sequence_text) if sequence_text else None
                speed = float(row["gps_kmh"]) if wind_format and row.get("gps_kmh") else None
            except (KeyError, TypeError, ValueError, OverflowError) as error:
                raise ValueError(f"CSV non valido alla riga {reader.line_num}: {error}") from error
            if previous_ms is not None and (ms < previous_ms or ms - previous_ms > 15000):
                segments.append([])
                last = None
                last_sample = None
            previous_ms = ms
            fix = (position, altitude, speed, stamp)
            if last is None or distance(last, position) >= 3:
                segments[-1].append(fix)
                last = position
            if gps_only or (last_sample is not None and distance(last_sample, position) < 3):
                continue
            height = f"{altitude:.1f} m" if altitude is not None else "n/d"
            packet = f"TX #{sequence}" if sequence is not None else "TX non ricevuto"
            label = (f"{packet} | Segnale {quality}/9 | Altitudine RX {height}"
                     f" | Tempo dall'avvio {ms / 1000:.1f} s")
            if wind_format:
                label += (f" | GPS {row.get('gps_kmh') or 'n/d'} km/h"
                          f" | Vento provvisorio {row.get('wind_ms_provisional') or 'n/d'} m/s")
            samples.append((fix, label))
            last_sample = position
    return segments, samples, has_rx
