import math
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, ttk
from xml.etree import ElementTree as ET


def coordinates(lat, lon):
    point = float(lat), float(lon)
    if not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180):
        raise ValueError("Coordinate fuori intervallo")
    return point


def distance(a, b):
    lat_a, lat_b = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((lat_b - lat_a) / 2) ** 2 +
         math.cos(lat_a) * math.cos(lat_b) *
         math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 12742000 * math.asin(math.sqrt(min(1, h)))


def save_route(base, segments, samples):
    gpx = ET.Element("gpx", version="1.1", creator="TrackerLoRa",
                     xmlns="http://www.topografix.com/GPX/1/1")

    def point(parent, tag, fix):
        position, altitude, speed, stamp = fix
        node = ET.SubElement(parent, tag, lat=str(position[0]), lon=str(position[1]))
        if altitude is not None:
            ET.SubElement(node, "ele").text = str(altitude)
        ET.SubElement(node, "time").text = stamp.isoformat().replace("+00:00", "Z")
        return node

    for fix, label in samples:
        node = point(gpx, "wpt", fix)
        ET.SubElement(node, "name").text = label
    track = ET.SubElement(gpx, "trk")
    ET.SubElement(track, "name").text = "Percorso RX"
    for segment in filter(None, segments):
        node = ET.SubElement(track, "trkseg")
        for fix in segment:
            point(node, "trkpt", fix)
    ET.ElementTree(gpx).write(base.with_suffix(".gpx"), encoding="utf-8",
                              xml_declaration=True)

    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                     width="1000", height="700", viewBox="0 0 1000 700")
    ET.SubElement(svg, "rect", width="1000", height="700", fill="#f1f5f9")
    ET.SubElement(svg, "text", x="20", y="25").text = (
        "Percorso RX | Puntini: passa il mouse per i dettagli"
        if any(segments) else "Nessuna posizione RX registrata")
    positions = [fix[0] for segment in segments for fix in segment]
    positions.extend(fix[0] for fix, _ in samples)
    if positions:
        north = max(lat for lat, _ in positions)
        west = min(lon for _, lon in positions)
        factor = math.cos(math.radians(north))
        width = (max(lon for _, lon in positions) - west) * factor
        height = north - min(lat for lat, _ in positions)
        scale = min(940 / max(width, 0.00001), 610 / max(height, 0.00001))

        def project(position):
            lat, lon = position
            return (500 + ((lon - west) * factor - width / 2) * scale,
                    365 + (north - lat - height / 2) * scale)

        for segment in filter(None, segments):
            xy = [project(fix[0]) for fix in segment]
            ET.SubElement(svg, "polyline", points=" ".join(
                f"{x:.2f},{y:.2f}" for x, y in xy), fill="none",
                stroke="#2563eb", attrib={"stroke-width": "3"})
            x, y = xy[0]
            ET.SubElement(svg, "circle", cx=str(x), cy=str(y), r="3", fill="#2563eb")
        for fix, label in samples:
            x, y = project(fix[0])
            dot = ET.SubElement(svg, "circle", cx=str(x), cy=str(y), r="5", fill="#ea580c")
            ET.SubElement(dot, "title").text = label
    ET.ElementTree(svg).write(base.with_suffix(".svg"), encoding="utf-8",
                              xml_declaration=True)


class Client:
    def __init__(self, root, serial, list_ports, map_widget):
        self.root = root
        self.serial = serial
        self.port = self.log = None
        self.state = "idle"
        self.pending = b""
        self.sync_line = True
        self.rx = None
        self.markers = {}
        root.title("TrackerLoRa")
        root.geometry("1000x700")
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="COM (115200)").pack(side="left")
        self.ports = ttk.Combobox(toolbar, width=12)
        self.ports.pack(side="left", padx=8)
        self.ports.configure(postcommand=lambda: self.ports.configure(
            values=[port.device for port in list_ports.comports()]))
        available = list_ports.comports()
        if available:
            preferred = next((port for port in available if port.vid is not None),
                             available[0])
            self.ports.set(preferred.device)
        self.buttons = []
        for label, action in (("START", self.start), ("PAUSA", self.pause),
                              ("STOP", self.stop)):
            button = ttk.Button(toolbar, text=label, command=action)
            button.pack(side="left", padx=4)
            self.buttons.append(button)
        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, padding=8).pack(fill="x")
        ttk.Label(root, text="Blu: RX e percorso   Rosso: TX   Arancione: pacchetti LoRa"
                           "   |   © OpenStreetMap contributors", padding=8).pack(side="bottom")
        self.map = map_widget(root)
        self.map.pack(fill="both", expand=True)
        self.set_state("idle", "Seleziona la porta COM del ricevitore")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.poll)

    def set_state(self, state, status):
        self.state = state
        for button, enabled in zip(self.buttons, (
                state != "running", state == "running", state != "idle")):
            button.configure(state="normal" if enabled else "disabled")
        self.ports.configure(state="normal" if state == "idle" else "disabled")
        self.status.set(status)

    def start(self):
        if self.state == "idle":
            device = self.ports.get().strip()
            if not device:
                messagebox.showerror("START", "Seleziona la porta COM del ricevitore")
                return
            try:
                self.port = self.serial.Serial(device, 115200, timeout=0)
                folder = Path(__file__).resolve().parent / "sessioni"
                folder.mkdir(exist_ok=True)
                self.base = folder / datetime.now().strftime("giro-%Y%m%d-%H%M%S-%f")
                self.log = self.base.with_suffix(".log").open("xb")
            except (OSError, ValueError) as error:
                if self.port is not None:
                    self.port.close()
                    self.port = None
                messagebox.showerror("START", str(error))
                return
            self.segments, self.samples = [[]], []
            self.last_sample = None
            self.map.delete_all_marker()
            self.map.delete_all_path()
            self.markers.clear()
            self.centered = False
        else:
            self.segments.append([])
        self.path = None
        self.rx = None
        self.set_state("running", "Registrazione attiva · in attesa dei dati GPS")

    def pause(self):
        if self.pending:
            self.sync_line = False
        self.set_state("paused", "In pausa · premi START per riprendere")

    def stop(self):
        if self.state == "idle":
            return True
        try:
            if self.port is not None:
                self.port.close()
                self.port = None
            if self.log is not None:
                self.log.close()
                self.log = None
            self.pending = b""
            self.sync_line = True
            save_route(self.base, self.segments, self.samples)
        except OSError as error:
            self.buttons[0].configure(state="disabled")
            self.buttons[1].configure(state="disabled")
            self.status.set("Salvataggio incompleto · premi STOP per riprovare")
            messagebox.showerror("STOP", str(error))
            return False
        self.set_state("idle", f"Sessione salvata · sessioni/{self.base.name} (.log, .gpx, .svg)")
        return True

    def close(self):
        if self.stop():
            self.root.destroy()

    def poll(self):
        try:
            if self.port is not None:
                data = self.port.read(8192)
                if data:
                    active = self.state == "running"
                    if active:
                        self.log.write(data)
                        self.log.flush()
                    lines = (self.pending + data).split(b"\n")
                    self.pending = lines.pop()
                    for line in lines:
                        if active and self.sync_line:
                            self.process(line.decode("ascii", errors="replace").strip())
                        self.sync_line = True
                    if self.pending and not active:
                        self.sync_line = False
        except OSError as error:
            self.stop()
            messagebox.showerror("Lettura RX", str(error))
        finally:
            self.root.after(50, self.poll)

    def marker(self, name, position, color):
        if name in self.markers:
            self.markers[name].set_position(*position)
        else:
            self.markers[name] = self.map.set_marker(
                *position, text=name, marker_color_circle=color, marker_color_outside=color)
        if not self.centered:
            self.map.set_position(*position)
            self.map.set_zoom(15)
            self.centered = True

    def process(self, line):
        now = datetime.now(timezone.utc)
        if line.startswith("# rx_gps="):
            fields = dict(word.split("=", 1) for word in line.split() if "=" in word)
            try:
                if fields["rx_gps"] != "fix":
                    raise ValueError
                position = coordinates(fields["lat"], fields["lon"])
                altitude = float(fields["altitude_m"]) if "altitude_m" in fields else None
                speed = float(fields["speed_kmh"]) if "speed_kmh" in fields else None
            except (KeyError, ValueError):
                self.rx = None
                return
            self.rx = position, altitude, speed, now
            self.marker("RX", position, "#2563eb")
            segment = self.segments[-1]
            if not segment or distance(segment[-1][0], position) >= 3:
                segment.append(self.rx)
                if self.path is not None:
                    self.path.add_position(position)
                elif len(segment) == 2:
                    self.path = self.map.set_path([fix[0] for fix in segment])
            return

        fields = line.split(",")
        if len(fields) != 9:
            return
        try:
            int(fields[0])
            sequence, quality = int(fields[1]), int(fields[4])
            if not 1 <= quality <= 10:
                return
            if fields[5] == "fix":
                self.marker("TX", coordinates(fields[6], fields[7]), "#dc2626")
        except ValueError:
            return
        fresh_rx = self.rx is not None and (now - self.rx[3]).total_seconds() <= 5
        self.status.set(f"TX #{sequence} · Segnale {quality}/10 · GPS TX: {fields[5]}"
                        f" · {'GPS RX disponibile' if fresh_rx else 'In attesa di GPS RX'}")
        if not fresh_rx:
            return
        position, altitude, speed, _ = self.rx
        if self.last_sample is not None:
            if (speed is not None and speed < 1) or distance(self.last_sample, position) < 3:
                return
        height = f"{altitude:.1f} m" if altitude is not None else "n/d"
        label = f"TX #{sequence} | Segnale {quality}/10 | Altitudine RX {height}"
        self.samples.append(((position, altitude, speed, now), label))
        self.last_sample = position
        self.map.set_marker(*position, marker_color_circle="#ea580c",
                            marker_color_outside="#ea580c",
                            command=lambda _: self.status.set(label))


if __name__ == "__main__":
    import serial
    from serial.tools import list_ports
    from tracker_map import TrackerMap

    window = tk.Tk()
    Client(window, serial, list_ports, TrackerMap)
    window.mainloop()
