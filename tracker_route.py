"""Create an interactive signal map from a TrackerLoRa GPX export."""

import argparse
from bisect import bisect_left
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import webbrowser
from xml.etree import ElementTree as ET


def timestamp(point):
    time = point.findtext("{*}time")
    if not time:
        raise ValueError("Il GPX contiene un punto senza orario.")
    return datetime.fromisoformat(time.replace("Z", "+00:00")).timestamp()


def position(point):
    return [float(point.get("lat", "")), float(point.get("lon", ""))]


def save_signal_map(gpx_path):
    root = ET.parse(gpx_path)
    samples = []
    for waypoint in root.findall("{*}wpt"):
        label = waypoint.findtext("{*}name", "")
        match = re.search(r"Segnale (10|[0-9])/(9|10)", label)
        if match:
            score = int(match[1])
            if match[2] == "10":
                score = max(0, score - 1)
            samples.append((timestamp(waypoint), score, label))
    samples.sort()
    times = [sample[0] for sample in samples]

    edges = []
    points = []
    for segment in root.findall(".//{*}trkseg"):
        track = [(timestamp(point), position(point)) for point in segment]
        points.extend(pos for _, pos in track)
        for (start, a), (end, b) in zip(track, track[1:]):
            midpoint = (start + end) / 2
            i = bisect_left(times, midpoint)
            nearby = [sample for sample in samples[max(0, i - 1):i + 1]
                      if start - 5 <= sample[0] <= end + 5]
            quality, label = None, "Nessuna misura recente"
            if nearby and end - start <= 15:
                time, score, detail = min(nearby, key=lambda item: abs(item[0] - midpoint))
                if abs(time - midpoint) <= 5:
                    quality, label = score, detail
            edges.append([a, b, quality, label])
    data = json.dumps({"edges": edges, "points": points,
                       "name": root.findtext(".//{*}trk/{*}name", "Percorso RX")}).replace("<", "\\u003c")
    output = gpx_path.with_suffix(".html")
    output.write_text(PAGE.replace("__ROUTE_DATA__", data), encoding="utf-8")
    return output


def serve_signal_map(report):
    from tracker_tiles import tile_session

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = report.read_bytes()
                content_type = "text/html; charset=utf-8"
            else:
                match = re.fullmatch(r"/tiles/(\d{1,2})/(\d{1,6})/(\d{1,6})\.png", self.path)
                if not match:
                    self.send_error(404)
                    return
                z, x, y = map(int, match.groups())
                if z > 19 or max(x, y) >= 2 ** z:
                    self.send_error(404)
                    return
                try:
                    with tile_session() as session:
                        tile = session.get(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                                           timeout=5)
                        tile.raise_for_status()
                    body = tile.content
                    content_type = "image/png"
                except OSError:
                    self.send_error(502)
                    return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"{url} — Ctrl+C per chiudere", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


PAGE = """<!doctype html>
<html lang="it">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TrackerLoRa | Segnale lungo il percorso</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
 integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<style>
body { margin: 0; height: 100vh; display: flex; flex-direction: column;
       color: #17212e; font: 15px system-ui, sans-serif; }
header { padding: 12px 16px; background: #fff; }
h1 { font-size: 19px; margin: 0 0 6px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; }
.legend span::before { content: ''; display: inline-block; width: 18px;
 height: 5px; margin-right: 5px; border-radius: 4px; background: var(--color); vertical-align: middle; }
#map { flex: 1; background: #e9eef3; }
#hint { margin: 6px 0 0; color: #4b5563; font-size: 13px; }
</style>
<header>
<h1>TrackerLoRa · Segnale lungo il percorso</h1>
<div class="legend" id="legend"></div>
<p id="hint">Clicca sul tracciato per vedere il pacchetto associato.</p>
</header>
<div id="map" aria-label="Mappa del tragitto RX"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
 integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
const route = __ROUTE_DATA__;
const bands = [
  [2, '#dc2626', '0–1 Debole'],
  [6, '#eab308', '2–5 Medio'],
  [10, '#16803c', '6–9 Forte'],
  [null, '#64748b', 'Senza misura recente']
];
const legend = document.querySelector('#legend');
const hint = document.querySelector('#hint');
document.querySelector('h1').textContent = 'TrackerLoRa · ' + route.name;
for (const [, color, label] of bands) {
  const item = document.createElement('span');
  item.style.setProperty('--color', color);
  item.textContent = label;
  legend.append(item);
}
if (!route.points.length) {
  hint.textContent = 'Nessuna posizione RX registrata.';
} else if (!window.L) {
  hint.textContent = 'Mappa non caricata. Controlla la connessione Internet.';
} else {
  const map = L.map('map', {preferCanvas: true});
  if (location.protocol === 'file:') {
    hint.textContent = 'Per vedere le strade, apri questa sessione con tracker_route.py --serve.';
  } else {
    L.tileLayer('/tiles/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).on('tileerror', () => {
      hint.textContent = 'Cartografia non disponibile. Il tracciato resta consultabile.';
    }).addTo(map);
  }
  for (const [a, b] of route.edges) {
    L.polyline([a, b], {color: '#fff', weight: 9, interactive: false}).addTo(map);
  }
  for (const [a, b, score, label] of route.edges) {
    const color = score === null ? '#64748b' : bands.find(([limit]) => score < limit)[1];
    const detail = document.createElement('span');
    detail.textContent = label;
    L.polyline([a, b], {color, weight: 6}).bindPopup(detail).addTo(map);
  }
  if (!route.edges.length) {
    L.circleMarker(route.points[0], {radius: 4}).addTo(map);
  }
  map.fitBounds(route.points, {padding: [24, 24], maxZoom: 16});
  L.control.scale({imperial: false}).addTo(map);
}
</script>
</html>
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gpx", type=Path)
    parser.add_argument("--serve", action="store_true", help="Apri la mappa nel browser")
    args = parser.parse_args()
    report = save_signal_map(args.gpx)
    if args.serve:
        serve_signal_map(report)
    else:
        print(report)
