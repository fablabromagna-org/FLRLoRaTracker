"""Import recordings stored by the Pico, including older nine-column CSV files."""
import csv
import math
from datetime import datetime, timedelta, timezone


def read_recording(path):
    from tracker_client import coordinates, distance

    segments, samples = [[]], []
    previous_ms = None
    last = None
    has_rx = False
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            try:
                ms = int(row["rx_ms"])
                quality = int(row.get("quality_0_9", row.get("quality", "")))
                if "quality_0_9" not in row:
                    quality = max(0, quality - 1)
                if not 0 <= quality <= 9:
                    raise ValueError("Segnale fuori intervallo")
                rx = bool(row.get("rx_lat") and row.get("rx_lon"))
                if rx:
                    position = coordinates(row["rx_lat"], row["rx_lon"])
                    has_rx = True
                elif "rx_lat" in row:
                    continue
                elif row.get("gps") == "fix":
                    position = coordinates(row["lat"], row["lon"])
                else:
                    continue
                altitude = float(row["rx_altitude_m"]) if row.get("rx_altitude_m") else None
                if altitude is not None and not math.isfinite(altitude):
                    altitude = None
                stamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms)
                sequence = int(row["seq"])
            except (KeyError, ValueError, OverflowError) as error:
                raise ValueError(f"CSV non valido alla riga {source.line_num}: {error}") from error
            if previous_ms is not None and (ms < previous_ms or ms - previous_ms > 15000):
                segments.append([])
                last = None
            previous_ms = ms
            if last is not None and distance(last, position) < 3:
                continue
            fix = (position, altitude, None, stamp)
            segments[-1].append(fix)
            height = f"{altitude:.1f} m" if altitude is not None else "n/d"
            label = (f"TX #{sequence} | Segnale {quality}/9 | Altitudine RX {height}"
                     f" | Tempo dall'avvio {ms / 1000:.1f} s")
            samples.append((fix, label))
            last = position
    return segments, samples, has_rx
