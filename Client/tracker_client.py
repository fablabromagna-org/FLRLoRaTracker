import math
import re
import time
import subprocess
import sys
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from xml.etree import ElementTree as ET

from tracker_route import save_signal_map


PROJECT_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = PROJECT_DIR / "sessioni"
RECORDINGS_DIR = PROJECT_DIR / "Registrazioni"


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
        self.route_viewer = None
        self.state = "idle"
        self.pending = b""
        self.sync_line = True
        self.rx = None
        self.markers = {}
        self.transfer = None
        self.transfer_file = None
        self.device_files = []
        self.device_recording = None
        self.wire_scale_nine = False
        self.segments, self.samples = [[]], []
        self.last_sample = self.path = self.followed_rx = None
        self.centered = False
        root.title("TrackerLoRa")
        root.geometry("1280x750")
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
        ttk.Button(toolbar, text="APRI SESSIONE", command=self.open_session).pack(
            side="left", padx=4)
        ttk.Button(toolbar, text="COLLEGA", command=self.connect).pack(side="left", padx=4)
        ttk.Button(toolbar, text="LEGGI PICO", command=self.list_recordings).pack(side="left", padx=4)
        ttk.Button(toolbar, text="REGISTRAZIONI", command=self.open_recording).pack(side="left", padx=4)
        self.rec_label = tk.Label(root, text="REC device · stato sconosciuto",
                                 font=("Segoe UI", 16, "bold"), anchor="w")
        self.rec_label.pack(fill="x", padx=10)
        self.status = tk.StringVar()
        self.received = tk.StringVar(value="In attesa di pacchetti LoRa")
        self.sequence = tk.StringVar(value="—")
        summary = ttk.Frame(root, padding=(10, 4))
        summary.pack(fill="x")
        counter = ttk.Frame(summary)
        counter.pack(side="right")
        ttk.Label(counter, text="PROGRESSIVO TX", anchor="e").pack(fill="x")
        ttk.Label(counter, textvariable=self.sequence, anchor="e",
                  font=("Segoe UI", 38, "bold")).pack(fill="x")
        details = ttk.Frame(summary)
        details.pack(side="left", fill="x", expand=True, padx=(0, 16))
        self.signal_bar = tk.Canvas(details, width=270, height=28, highlightthickness=0)
        self.signal_bar.pack(anchor="w")
        self.draw_signal()
        ttk.Label(details, textvariable=self.received, font=("Segoe UI", 16, "bold"),
                  justify="left").pack(anchor="w")
        ttk.Label(root, textvariable=self.status, padding=(10, 4)).pack(fill="x")
        ttk.Label(root, text="Blu: RX e percorso   Rosso: TX   Arancione: pacchetti LoRa"
                           "   |   © OpenStreetMap contributors", padding=8).pack(side="bottom")
        self.map = map_widget(root)
        self.map.pack(fill="both", expand=True)
        self.set_state("idle", "Seleziona la porta COM del ricevitore")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.poll)

    def draw_signal(self, quality=None):
        bar = self.signal_bar
        bar.delete("all")
        bar.create_rectangle(0, 0, 270, 28, fill="#e5e7eb", outline="")
        if quality is not None:
            color = "#4ade80" if quality >= 6 else "#facc15" if quality >= 2 else "#f87171"
            bar.create_rectangle(0, 0, max(4, 30 * quality), 28, fill=color, outline="")
        bar.create_text(135, 14, text="—" if quality is None else f"{quality}/9",
                        fill="#111827", font=("Segoe UI", 14, "bold"))

    def set_state(self, state, status):
        self.state = state
        for button, enabled in zip(self.buttons, (
                state != "running", state == "running", state != "idle")):
            button.configure(state="normal" if enabled else "disabled")
        self.ports.configure(state="normal" if state == "idle" else "disabled")
        self.status.set(status)

    def connect(self):
        if self.port is not None:
            return
        try:
            self.port = self.serial.Serial(self.ports.get().strip(), 115200,
                                           timeout=0, write_timeout=1)
            self.port.dtr = True
            self.pending = b""
            self.sync_line = True
            self.port.write(b"STATUS\n")
            self.status.set("RX collegato")
        except (OSError, ValueError) as error:
            if self.port is not None:
                self.port.close()
                self.port = None
            messagebox.showerror("Collegamento RX", str(error))

    def set_rec(self, recording):
        self.device_recording = recording
        text = "● REC sul device" if recording else "REC device · fermo"
        if recording is None:
            text = "REC device · stato sconosciuto"
        self.rec_label.configure(text=text, fg="#dc2626" if recording else "#475569")

    def cancel_transfer(self):
        if self.transfer_file is not None:
            self.transfer_file.close()
            self.transfer_file = None
        self.transfer = None

    def list_recordings(self):
        if self.transfer:
            return
        self.connect()
        if self.port is None:
            return
        if self.device_recording:
            messagebox.showinfo("Pico", "Premi il pulsante sul device per terminare REC.")
            return
        try:
            self.device_files = []
            self.port.write(b"LIST\n")
            self.transfer = "list"
            self.transfer_deadline = time.monotonic() + 15
            self.status.set("Lettura elenco registrazioni dal Pico…")
        except OSError as error:
            messagebox.showerror("Pico", str(error))

    def choose_device_recording(self):
        if not self.device_files:
            messagebox.showinfo("Pico", "Nessuna registrazione presente sul device.")
            return
        window = tk.Toplevel(self.root)
        window.title("Registrazioni sul Pico")
        files = tk.Listbox(window, width=50, height=12)
        files.pack(fill="both", expand=True, padx=10, pady=10)
        for name, size in self.device_files:
            files.insert("end", f"{name} · {size} byte")
        files.selection_set(len(self.device_files) - 1)

        def download():
            selected = files.curselection()
            if not selected or self.transfer:
                return
            name, self.expected_bytes = self.device_files[selected[0]]
            try:
                RECORDINGS_DIR.mkdir(exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                self.download_path = RECORDINGS_DIR / f"{stamp}-{name.lstrip('/')}"
                self.transfer_file = self.download_path.with_suffix(".part").open("xb")
                self.transfer = "wait"
                self.transfer_deadline = time.monotonic() + 15
                self.port.write(f"GET {name}\n".encode("ascii"))
                window.destroy()
                self.status.set("Download della registrazione…")
            except OSError as error:
                self.cancel_transfer()
                messagebox.showerror("Pico", str(error))

        ttk.Button(window, text="SCARICA E VISUALIZZA", command=download).pack(pady=10)

    def device_line(self, line):
        if line.startswith("# log_started") or line == "# recording=1":
            self.set_rec(True)
        elif line == "# recording=0":
            self.set_rec(False)
        elif line == "# log_stopped":
            self.set_rec(False)
            self.root.after(100, self.list_recordings)
        elif line in ("# log_write_error", "# log_open_error"):
            self.set_rec(False)
            self.status.set("Errore di registrazione sul device")
        if not self.transfer:
            return False
        if line in ("# file not found", "# stop recording first or check storage"):
            self.cancel_transfer()
            messagebox.showerror("Pico", line.lstrip("# "))
            return True
        if self.transfer == "list":
            match = re.fullmatch(r"# /?(session\d{4}\.csv) (\d+)", line)
            if match:
                self.transfer_deadline = time.monotonic() + 15
                self.device_files.append(("/" + match[1], int(match[2])))
            if line == "# END LIST":
                self.transfer = None
                self.choose_device_recording()
            return False
        if line == "# BEGIN CSV" and self.transfer == "wait":
            self.transfer_deadline = time.monotonic() + 15
            self.transfer = "csv"
            return True
        if self.transfer == "csv":
            if line == "# END CSV":
                size = self.transfer_file.tell()
                self.cancel_transfer()
                if size != self.expected_bytes:
                    messagebox.showerror("Pico", "Download incompleto. Il file .part è conservato.")
                    return True
                self.download_path.with_suffix(".part").replace(self.download_path)
                self.show_recording(self.download_path)
            else:
                self.transfer_deadline = time.monotonic() + 15
                self.transfer_file.write((line + "\r\n").encode("ascii"))
            return True
        return False

    def open_recording(self):
        if not RECORDINGS_DIR.exists():
            messagebox.showinfo("Registrazioni", "Usa LEGGI PICO per scaricare una registrazione.")
            return
        filename = filedialog.askopenfilename(
            parent=self.root, title="Apri registrazione", initialdir=RECORDINGS_DIR,
            filetypes=[("Registrazione Pico", "*.csv")])
        if filename:
            self.show_recording(Path(filename))

    def show_recording(self, filename):
        from tracker_recordings import read_recording
        try:
            segments, samples, has_rx = read_recording(filename)
            if not samples:
                messagebox.showinfo("Registrazione", "CSV salvato. Nessuna posizione GPS valida.")
                return
            base = filename.with_suffix("")
            save_route(base, segments, samples)
            if not has_rx:
                tree = ET.parse(base.with_suffix(".gpx"))
                tree.find(".//{*}trk/{*}name").text = "Percorso TX · GPS RX assente nel CSV"
                tree.write(base.with_suffix(".gpx"), encoding="utf-8", xml_declaration=True)
            self.launch_route(base.with_suffix(".gpx"))
            self.status.set(f"Registrazione salvata in Registrazioni/{filename.name}")
        except (OSError, ValueError, ET.ParseError) as error:
            messagebox.showerror("Registrazione", str(error))

    def start(self):
        if self.state == "idle":
            device = self.ports.get().strip()
            if not device:
                messagebox.showerror("START", "Seleziona la porta COM del ricevitore")
                return
            try:
                if self.port is None:
                    self.connect()
                if self.port is None:
                    return
                SESSIONS_DIR.mkdir(exist_ok=True)
                self.base = SESSIONS_DIR / datetime.now().strftime("giro-%Y%m%d-%H%M%S-%f")
                self.log = self.base.with_suffix(".log").open("xb")
            except (OSError, ValueError) as error:
                if self.port is not None:
                    self.port.close()
                    self.port = None
                messagebox.showerror("START", str(error))
                return
            self.segments, self.samples = [[]], []
            self.received.set("In attesa di pacchetti LoRa")
            self.sequence.set("—")
            self.draw_signal()
            self.last_sample = None
            self.map.delete_all_marker()
            self.map.delete_all_path()
            self.markers.clear()
            self.centered = False
            self.followed_rx = None
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
            if self.log is not None:
                self.log.close()
                self.log = None
            self.pending = b""
            self.sync_line = True
            save_route(self.base, self.segments, self.samples)
            save_signal_map(self.base.with_suffix(".gpx"))
        except OSError as error:
            self.buttons[0].configure(state="disabled")
            self.buttons[1].configure(state="disabled")
            self.status.set("Salvataggio incompleto · premi STOP per riprovare")
            messagebox.showerror("STOP", str(error))
            return False
        self.set_state("idle", f"Sessione salvata · sessioni/{self.base.name} (.log, .gpx, .svg, .html)")
        return True

    def open_session(self):
        if not SESSIONS_DIR.is_dir():
            messagebox.showinfo("Apri sessione", "Non ci sono ancora sessioni salvate.")
            return
        gpx = filedialog.askopenfilename(
            parent=self.root, title="Apri sessione TrackerLoRa",
            initialdir=SESSIONS_DIR, filetypes=[("Sessione TrackerLoRa", "*.gpx")])
        if not gpx:
            return
        self.launch_route(Path(gpx))

    def launch_route(self, gpx):
        try:
            save_signal_map(Path(gpx))
            viewer = subprocess.Popen([
                sys.executable, str(PROJECT_DIR / "tracker_route.py"), "--serve", str(gpx)])
        except (OSError, ValueError, ET.ParseError) as error:
            messagebox.showerror("Apri sessione", str(error))
            return
        self.close_route_viewer()
        self.route_viewer = viewer

    def close_route_viewer(self):
        if self.route_viewer is not None and self.route_viewer.poll() is None:
            self.route_viewer.terminate()

    def close(self):
        if self.stop():
            self.cancel_transfer()
            if self.port is not None:
                self.port.close()
            self.close_route_viewer()
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
                        decoded = line.decode("ascii", errors="replace").strip()
                        consumed = self.device_line(decoded)
                        if not consumed and (active or self.state == "idle") and self.sync_line:
                            self.process(decoded)
                        self.sync_line = True
                    if self.pending and self.state == "paused":
                        self.sync_line = False
            if self.transfer and time.monotonic() > self.transfer_deadline:
                self.cancel_transfer()
                messagebox.showerror("Pico", "Trasferimento scaduto. Riprova LEGGI PICO.")
        except OSError as error:
            self.cancel_transfer()
            self.stop()
            if self.port is not None:
                self.port.close()
                self.port = None
            self.set_rec(None)
            messagebox.showerror("Lettura RX", str(error))
        finally:
            self.root.after(50, self.poll)

    def marker(self, name, position):
        if name in self.markers:
            self.markers[name].set_position(*position)
        else:
            self.markers[name] = self.map.set_dot(name, position)
        if not self.centered:
            self.map.set_position(*position)
            self.map.set_zoom(15)
            self.centered = True
        elif name == "RX" and position != self.followed_rx:
            self.map.set_position(*position)
        if name == "RX":
            self.followed_rx = position

    def process(self, line):
        now = datetime.now(timezone.utc)
        if line.startswith("rx_ms,"):
            self.wire_scale_nine = "quality_0_9" in line
            return
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
            self.marker("RX", position)
            segment = self.segments[-1]
            if not segment or distance(segment[-1][0], position) >= 3:
                segment.append(self.rx)
                if self.path is not None:
                    self.path.add_position(*position)
                    self.path.draw()
                elif len(segment) == 2:
                    self.path = self.map.set_path([fix[0] for fix in segment])
            return

        fields = line.split(",")
        if len(fields) not in (9, 12):
            return
        try:
            int(fields[0])
            sequence, quality = int(fields[1]), int(fields[4])
            if not self.wire_scale_nine:
                quality = max(0, quality - 1)
            if not 0 <= quality <= 9:
                return
            if fields[5] == "fix":
                self.marker("TX", coordinates(fields[6], fields[7]))
        except ValueError:
            return
        fresh_rx = self.rx is not None and (now - self.rx[3]).total_seconds() <= 5
        try:
            meters = float(fields[8])
        except ValueError:
            meters = math.nan
        if not math.isfinite(meters) or meters < 0:
            range_text = "n/d"
        elif meters >= 1000:
            range_text = f"{meters / 1000:.2f} km".replace(".", ",")
        else:
            range_text = f"{meters:.0f} m"
        self.sequence.set(f"#{sequence}")
        self.draw_signal(quality)
        self.received.set(f"Distanza RX–TX: {range_text}\n"
                          f"GPS TX: {fields[5]}   ·   GPS RX: {'fix' if fresh_rx else 'in attesa'}")
        if not fresh_rx:
            return
        position, altitude, speed, _ = self.rx
        if self.last_sample is not None:
            if (speed is not None and speed < 1) or distance(self.last_sample, position) < 3:
                return
        height = f"{altitude:.1f} m" if altitude is not None else "n/d"
        label = f"TX #{sequence} | Segnale {quality}/9 | Altitudine RX {height}"
        self.samples.append(((position, altitude, speed, now), label))
        self.last_sample = position
        self.map.set_dot("packet", position, command=lambda _: self.status.set(label))


if __name__ == "__main__":
    import serial
    from serial.tools import list_ports
    from tracker_map import TrackerMap

    window = tk.Tk()
    Client(window, serial, list_ports, TrackerMap)
    window.mainloop()
