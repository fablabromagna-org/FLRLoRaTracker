import math
import re
import time
import zlib
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from xml.etree import ElementTree as ET

from PIL import Image, ImageTk

from tracker_route import read_signal_route, save_signal_map
from tracker_memory import MemoryManager, local_recording


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
        self.reviewing = False
        self.state = "idle"
        self.pending = b""
        self.sync_line = True
        self.rx = None
        self.markers = {}
        self.transfer = None
        self.transfer_file = None
        self.device_files = []
        self.download_queue = []
        self.download_count = 0
        self.download_skipped = 0
        self.sync_on_stop = False
        self.device_recording = None
        self.wire_scale_nine = False
        self.segments, self.samples = [[]], []
        self.last_sample = self.path = self.followed_rx = None
        self.centered = False
        self.battery_values = {"RX": None, "TX": None}
        self.battery_timeout = {"RX": 10.0, "TX": 9.0}
        self.memory = MemoryManager(self, RECORDINGS_DIR)
        root.title("TrackerLoRa")
        root.geometry("1280x800")
        root.minsize(1100, 680)
        root.configure(background="#edf1f5")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#edf1f5")
        style.configure("TLabel", background="#edf1f5", foreground="#263449",
                        font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
        style.configure("TLabelframe", background="#edf1f5", bordercolor="#d2dae3")
        style.configure("TLabelframe.Label", background="#edf1f5",
                        foreground="#526176", font=("Segoe UI", 9, "bold"))
        style.configure("Card.TFrame", background="white")
        style.configure("Card.TLabel", background="white")
        style.configure("Title.TLabel", background="white",
                        foreground="#17283d", font=("Segoe UI", 19, "bold"))
        header = ttk.Frame(root, style="Card.TFrame", padding=(16, 10))
        header.pack(fill="x")
        logo_path = PROJECT_DIR.parent / "images" / "logo_fablabromagna.png"
        if logo_path.exists():
            with Image.open(logo_path) as image:
                image = image.convert("RGBA")
                image.thumbnail((210, 64), Image.Resampling.LANCZOS)
                self.logo = ImageTk.PhotoImage(image)
            ttk.Label(header, image=self.logo, style="Card.TLabel").pack(side="right")
        ttk.Label(header, text="TrackerLoRa", style="Title.TLabel").pack(anchor="w")
        self.view_title = tk.StringVar(value="Ricezione in tempo reale")
        ttk.Label(header, textvariable=self.view_title, style="Card.TLabel").pack(anchor="w")

        toolbar = ttk.Frame(root, padding=(12, 8))
        toolbar.pack(fill="x")
        connection = ttk.LabelFrame(toolbar, text="RICEVITORE", padding=(8, 5))
        connection.pack(side="left", padx=(0, 8))
        ttk.Label(connection, text="COM").pack(side="left")
        self.ports = ttk.Combobox(connection, width=8)
        self.ports.pack(side="left", padx=6)
        self.ports.configure(postcommand=lambda: self.ports.configure(
            values=[port.device for port in list_ports.comports()]))
        available = list_ports.comports()
        usb_ports = [port for port in available if port.vid is not None]
        if len(usb_ports) == 1:
            self.ports.set(usb_ports[0].device)
        elif not usb_ports and len(available) == 1:
            self.ports.set(available[0].device)
        self.connection_button = ttk.Button(
            connection, text="Connetti", command=self.toggle_connection)
        self.connection_button.pack(side="left")
        ttk.Button(connection, text="LIVE", command=self.show_live).pack(side="left", padx=(4, 0))
        ttk.Button(connection, text="REGISTRAZIONI", command=self.download_recordings).pack(
            side="left", padx=(4, 0))
        ttk.Button(connection, text="GESTISCI MEMORIA", command=self.memory.open).pack(
            side="left", padx=(4, 0))
        self.rec_label = tk.Label(connection, text="REC · sconosciuto",
                                 background="#edf1f5", foreground="#475569",
                                 font=("Segoe UI", 10, "bold"), width=18, anchor="w")
        self.rec_label.pack(side="left", padx=(10, 0))
        recording = ttk.LabelFrame(toolbar, text="Sessioni lanciate da PC", padding=(8, 5))
        recording.pack(side="left", padx=(0, 8))
        self.buttons = []
        for label, action in (("START", self.start), ("PAUSA", self.pause),
                              ("STOP", self.stop)):
            button = ttk.Button(recording, text=label, command=action, width=7)
            button.pack(side="left", padx=2)
            self.buttons.append(button)
        ttk.Button(recording, text="SESSIONI", command=self.open_session).pack(
            side="left", padx=(8, 2))

        self.status = tk.StringVar()
        self.received = tk.StringVar(value="In attesa di pacchetti LoRa")
        self.sequence = tk.StringVar(value="—")
        self.info_panel = ttk.Frame(root, style="Card.TFrame", padding=(16, 8))
        self.info_panel.pack(fill="x", padx=12, pady=(0, 8))
        self.live_summary = ttk.Frame(self.info_panel, style="Card.TFrame")
        self.live_summary.pack(fill="x")
        counter = ttk.Frame(self.live_summary, style="Card.TFrame")
        counter.pack(side="right", padx=(20, 0))
        ttk.Label(counter, text="PROGRESSIVO TX", style="Card.TLabel",
                  anchor="e").pack(fill="x")
        ttk.Label(counter, textvariable=self.sequence, anchor="e",
                  style="Card.TLabel", font=("Segoe UI", 38, "bold")).pack(fill="x")
        details = ttk.Frame(self.live_summary, style="Card.TFrame")
        details.pack(side="left", fill="x", expand=True)
        ttk.Label(details, text="SEGNALE LoRa", style="Card.TLabel").pack(anchor="w")
        self.signal_bar = tk.Canvas(details, width=270, height=28,
                                    background="white", highlightthickness=0)
        self.signal_bar.pack(anchor="w", pady=(3, 4))
        self.draw_signal()
        ttk.Label(details, textvariable=self.received, style="Card.TLabel",
                  font=("Segoe UI", 14, "bold"), justify="left").pack(anchor="w")
        self.battery_text = tk.StringVar(value="Batteria RX: n/d   ·   Batteria TX: n/d")
        ttk.Label(details, textvariable=self.battery_text, style="Card.TLabel",
                  font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(4, 0))
        self.route_info = tk.StringVar()
        self.route_summary = ttk.Label(self.info_panel, textvariable=self.route_info,
                                        style="Card.TLabel", font=("Segoe UI", 14, "bold"),
                                        justify="left")
        legend = ttk.Frame(root, padding=(16, 0, 16, 6))
        legend.pack(fill="x")
        ttk.Label(legend, text="Segnale   ", font=("Segoe UI", 10, "bold")).pack(side="left")
        for text, color in (("6–9 Forte", "#16a34a"), ("2–5 Medio", "#eab308"),
                            ("0–1 Debole", "#dc2626"), ("Senza misura recente", "#64748b")):
            tk.Label(legend, text="━━", fg=color, bg="#edf1f5",
                     font=("Segoe UI", 14, "bold")).pack(side="left")
            ttk.Label(legend, text=text, padding=(2, 0, 12, 0)).pack(side="left")

        footer = ttk.Frame(root, padding=(14, 5))
        footer.pack(side="bottom", fill="x")
        self.footer_legend = tk.StringVar(
            value="Blu RX  ·  Rosso TX  ·  Arancione pacchetti  |  © OpenStreetMap contributors")
        ttk.Label(footer, textvariable=self.footer_legend, foreground="#526176",
                  font=("Segoe UI", 9)).pack(anchor="w")
        self.status_label = ttk.Label(footer, textvariable=self.status,
                                      font=("Segoe UI", 9), foreground="#526176",
                                      wraplength=1000, justify="left")
        self.status_label.pack(anchor="w")
        self.map = map_widget(root)
        self.map.pack(fill="both", expand=True, padx=12, pady=(0, 5))
        root.bind("<Configure>", self.resize_info, add="+")
        root.update_idletasks()
        root.minsize(max(1100, toolbar.winfo_reqwidth()), 680)
        self.set_state("idle", "Seleziona la porta COM del ricevitore")
        if len(usb_ports) > 1:
            self.status.set("Più dispositivi USB presenti · seleziona la COM del ricevitore RX")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.poll)

    def resize_info(self, event):
        if event.widget is self.root:
            width = max(300, event.width - 64)
            self.status_label.configure(wraplength=width)
            self.route_summary.configure(wraplength=width)

    def set_view(self, reviewing, title=""):
        self.live_summary.pack_forget()
        self.route_summary.pack_forget()
        if reviewing:
            self.view_title.set(title)
            self.route_summary.pack(fill="x", pady=4)
            self.footer_legend.set("Blu inizio  ·  Rosso fine  |  © OpenStreetMap contributors")
        else:
            self.view_title.set("Ricezione in tempo reale")
            self.route_info.set("")
            self.live_summary.pack(fill="x")
            self.footer_legend.set(
                "Blu RX  ·  Rosso TX  ·  Arancione pacchetti  |  © OpenStreetMap contributors")

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

    def toggle_connection(self):
        if self.port is None:
            self.connect()
        else:
            self.disconnect()

    def disconnect(self, status="RX disconnesso"):
        port, self.port = self.port, None
        if port is not None:
            try:
                port.close()
            except OSError:
                pass  # Windows can report another error after USB removal.
        self.connection_button.configure(text="Connetti")
        self.cancel_transfer()
        self.sync_on_stop = False
        self.pending = b""
        self.sync_line = True
        self.set_rec(None)
        self.battery_values = {"RX": None, "TX": None}
        self.refresh_batteries()
        self.memory.pending = []
        self.memory.verified = []
        if self.memory.window is not None and self.memory.window.winfo_exists():
            self.memory.info.set(status)
        if self.state != "idle":
            if not self.stop():
                return
            status += " · sessione PC salvata"
        self.status.set(status)

    def connect(self):
        device = self.ports.get().strip()
        if self.port is not None:
            if self.port.port == device:
                self.show_live()
                return
            if self.state != "idle" or self.transfer:
                messagebox.showinfo("Ricevitore RX", "Termina la sessione o il download prima di cambiare COM.")
                return
            self.disconnect()
        if not device:
            messagebox.showinfo("Ricevitore RX", "Seleziona la porta COM del ricevitore RX.")
            return
        try:
            self.port = self.serial.Serial(device, 115200,
                                           timeout=0, write_timeout=1)
            if hasattr(self.port, "set_buffer_size"):
                self.port.set_buffer_size(rx_size=1048576)
            self.port.dtr = True
            self.pending = b""
            self.sync_line = True
            self.battery_values = {"RX": None, "TX": None}
            self.battery_timeout = {"RX": 10.0, "TX": 9.0}
            self.refresh_batteries()
            self.port.write(b"STATUS\n")
            self.connection_button.configure(text="Disconnetti")
            self.show_live()
            self.status.set("RX collegato · ricezione live")
        except (OSError, ValueError) as error:
            self.disconnect()
            messagebox.showerror("Collegamento RX", str(error))

    def set_rec(self, recording):
        self.device_recording = recording
        text = "● REC sul Pico" if recording else "REC · fermo"
        if recording is None:
            text = "REC · sconosciuto"
        self.rec_label.configure(text=text, fg="#dc2626" if recording else "#475569")

    def update_battery(self, name, value):
        try:
            volts = float(value)
            if not math.isfinite(volts) or not 2.5 <= volts <= 4.35:
                raise ValueError
            self.battery_values[name] = (volts, time.monotonic())
        except (TypeError, ValueError):
            self.battery_values[name] = None
        self.refresh_batteries()

    def refresh_batteries(self):
        values = []
        now = time.monotonic()
        for name, reading in self.battery_values.items():
            text = "n/d"
            if reading is not None:
                volts, stamp = reading
                text = f"{volts:.2f} V".replace(".", ",")
                if self.port is None or now - stamp > self.battery_timeout[name]:
                    text += " (dato precedente)"
            values.append(f"Batteria {name}: {text}")
        text = "   ·   ".join(values)
        if self.battery_text.get() != text:
            self.battery_text.set(text)

    def cancel_transfer(self):
        if self.transfer_file is not None:
            self.transfer_file.close()
            self.transfer_file = None
        self.transfer = None
        self.download_queue = []

    def list_recordings(self):
        if self.transfer:
            return
        if self.port is None:
            return
        if self.device_recording:
            self.sync_on_stop = True
            self.status.set("REC attivo sul Pico · download automatico al termine della registrazione")
            return
        self.sync_on_stop = False
        try:
            self.device_files = []
            self.port.write(b"LIST\n")
            self.transfer = "list"
            self.transfer_deadline = time.monotonic() + 15
            self.status.set("Lettura elenco registrazioni dal Pico…")
        except OSError as error:
            self.cancel_transfer()
            messagebox.showerror("Pico", str(error))

    def download_recordings(self):
        if self.transfer:
            return
        if self.port is None or self.port.port != self.ports.get().strip():
            self.connect()
            if self.port is None or self.port.port != self.ports.get().strip():
                return
            self.root.after(300, self.list_recordings)
        else:
            self.list_recordings()

    def download_next_recording(self):
        if self.transfer != "queued":
            return
        if not self.download_queue:
            self.transfer = None
            self.status.set(
                f"Registrazioni aggiornate · {self.download_count} nuove · "
                f"{self.download_skipped} già presenti")
            self.root.after(0, self.open_recording)
            return
        if self.device_recording:
            self.sync_on_stop = True
            self.cancel_transfer()
            self.status.set("REC attivo · download rinviato al termine della registrazione")
            return
        name, self.expected_bytes = self.download_queue.pop(0)
        self.download_name = name
        self.download_attempt = 1
        self.download_crc = None
        self.transfer = "download-check"
        self.transfer_deadline = time.monotonic() + 15
        try:
            self.port.write(f"CHECK {name}\n".encode("ascii"))
            self.status.set(f"Verifica registrazione {name}…")
        except OSError as error:
            self.cancel_transfer()
            messagebox.showerror("Pico", str(error))

    def begin_download(self):
        try:
            RECORDINGS_DIR.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            self.download_path = RECORDINGS_DIR / f"{stamp}-{self.download_name.lstrip('/')}"
            self.transfer_file = self.download_path.with_suffix(".part").open("xb")
            self.transfer = "wait"
            self.transfer_deadline = time.monotonic() + 15
            self.port.write(f"GET {self.download_name}\n".encode("ascii"))
            self.status.set(
                f"Download {self.download_count + self.download_skipped + 1}/"
                f"{len(self.device_files)} · {self.download_name}")
        except OSError as error:
            self.cancel_transfer()
            messagebox.showerror("Pico", str(error))

    def retry_download(self):
        if self.transfer != "retry":
            return
        try:
            self.transfer_file = self.download_path.with_suffix(".part").open("wb")
            self.transfer = "wait"
            self.transfer_deadline = time.monotonic() + 15
            self.port.write(f"GET {self.download_name}\n".encode("ascii"))
            self.status.set(
                f"Ripetizione download {self.download_name} · tentativo {self.download_attempt}/3")
        except OSError as error:
            self.cancel_transfer()
            messagebox.showerror("Pico", str(error))

    def device_line(self, line):
        if self.transfer != "csv":
            if line.startswith("# battery_v="):
                self.update_battery("RX", line.split()[1].split("=", 1)[1])
            elif line.startswith("# rx_radio "):
                fields = dict(word.split("=", 1) for word in line.split() if "=" in word)
                try:
                    self.battery_timeout["TX"] = max(9.0, 3 * int(fields["interval_ms"]) / 1000)
                except (KeyError, ValueError):
                    pass
            elif not line.startswith("#"):
                fields = line.split(",")
                if len(fields) == 18 and fields[14] == "radio":
                    try:
                        int(fields[0])
                        int(fields[1])
                    except ValueError:
                        pass
                    else:
                        self.update_battery("TX", fields[16])
                        self.update_battery("RX", fields[17])
        if line.startswith(("# tx_seq=", "# tx_error=")):
            if self.transfer:
                self.cancel_transfer()
                messagebox.showerror(
                    "Porta del trasmettitore",
                    f"{self.port.port} è il TX. Seleziona la COM del ricevitore RX.")
            self.status.set(f"{self.port.port} è il trasmettitore TX · collega il ricevitore RX")
            return True
        if line.startswith("# log_started") or line == "# recording=1":
            self.set_rec(True)
        elif line == "# recording=0":
            self.set_rec(False)
        elif line == "# log_stopped":
            self.set_rec(False)
            if self.sync_on_stop:
                self.root.after(100, self.list_recordings)
        elif line in ("# log_write_error", "# log_open_error"):
            self.set_rec(False)
            self.status.set("Errore di registrazione sul device")
        if not self.transfer:
            return False
        if self.memory.handle_line(line):
            return True
        if self.transfer == "download-check":
            match = re.fullmatch(r"# CHECK (/session\d{4}\.csv) (\d+) ([0-9a-fA-F]{8})", line)
            if match and match[1] == self.download_name:
                self.expected_bytes = int(match[2])
                self.download_crc = int(match[3], 16)
                if local_recording(RECORDINGS_DIR, self.download_name,
                                   self.expected_bytes, self.download_crc):
                    self.download_skipped += 1
                    self.transfer = "queued"
                    self.root.after(0, self.download_next_recording)
                else:
                    self.begin_download()
                return True
            if line.startswith("# commands:"):
                self.begin_download()
                return True
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
                self.download_queue = sorted(self.device_files)
                self.download_count = 0
                self.download_skipped = 0
                self.transfer = "queued"
                self.transfer_deadline = time.monotonic() + 15
                self.root.after(0, self.download_next_recording)
            return False
        if line == "# BEGIN CSV" and self.transfer == "wait":
            self.transfer_deadline = time.monotonic() + 15
            self.transfer = "csv"
            return True
        if self.transfer == "csv":
            if line == "# END CSV":
                size = self.transfer_file.tell()
                self.transfer_file.close()
                self.transfer_file = None
                downloaded_crc = zlib.crc32(
                    self.download_path.with_suffix(".part").read_bytes()) & 0xFFFFFFFF
                checksum_ok = self.download_crc is None or downloaded_crc == self.download_crc
                if size != self.expected_bytes or not checksum_ok:
                    if self.download_attempt < 3:
                        self.download_attempt += 1
                        self.transfer = "retry"
                        self.transfer_deadline = time.monotonic() + 15
                        self.root.after(100, self.retry_download)
                        return True
                    self.cancel_transfer()
                    messagebox.showerror(
                        "Pico", f"Download non valido dopo 3 tentativi: {size} byte ricevuti "
                        f"su {self.expected_bytes}. Il file .part è conservato.")
                    return True
                if local_recording(RECORDINGS_DIR, self.download_name, size, downloaded_crc):
                    self.download_path.with_suffix(".part").unlink()
                    self.download_skipped += 1
                else:
                    self.download_path.with_suffix(".part").replace(self.download_path)
                    self.download_count += 1
                self.transfer = "queued"
                self.transfer_deadline = time.monotonic() + 15
                self.root.after(0, self.download_next_recording)
            else:
                self.transfer_deadline = time.monotonic() + 15
                self.transfer_file.write((line + "\r\n").encode("ascii"))
            return True
        return False

    def open_recording(self):
        if not RECORDINGS_DIR.exists():
            messagebox.showinfo("Registrazioni", "Nessuna registrazione salvata sul PC.")
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
            if not any(segments):
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
                self.disconnect()
                messagebox.showerror("START", str(error))
                return
            self.segments, self.samples = [[]], []
            self.reviewing = False
            self.set_view(False)
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
            route = read_signal_route(Path(gpx))
        except (OSError, ValueError, ET.ParseError) as error:
            messagebox.showerror("Apri sessione", str(error))
            return
        if not route["points"]:
            messagebox.showinfo("Apri sessione", "Nessuna posizione GPS disponibile.")
            return
        self.reviewing = True
        self.map.delete_all_marker()
        self.map.delete_all_path()
        self.markers.clear()
        self.path = None
        for a, b, quality, label in route["edges"]:
            color = ("#64748b" if quality is None else "#16a34a" if quality >= 6
                     else "#eab308" if quality >= 2 else "#dc2626")
            self.map.set_path([a, b], color=color, width=5,
                              command=lambda _, detail=label: self.status.set(detail))
        points = route["points"]
        self.map.set_dot("RX", points[0], command=lambda _: self.status.set("Inizio percorso"))
        self.map.set_dot("TX", points[-1], command=lambda _: self.status.set("Fine percorso"))
        self.map.fit_bounding_box(
            (max(p[0] for p in points), min(p[1] for p in points)),
            (min(p[0] for p in points), max(p[1] for p in points)))
        self.received.set(route["name"])
        self.set_view(True, route["name"])
        self.route_info.set(route["summary"])
        self.sequence.set("—")
        self.draw_signal()
        self.status.set(f"{Path(gpx).name} · clicca sul tracciato per i dettagli · LIVE per tornare alla ricezione")

    def show_live(self):
        if not self.reviewing:
            return
        self.reviewing = False
        self.set_view(False)
        self.map.delete_all_marker()
        self.map.delete_all_path()
        self.markers.clear()
        self.path = None
        self.centered = False
        self.followed_rx = None
        for segment in self.segments:
            if len(segment) >= 2:
                path = self.map.set_path([fix[0] for fix in segment])
                if segment is self.segments[-1]:
                    self.path = path
        if self.rx is not None:
            self.marker("RX", self.rx[0])
        self.received.set("In attesa di pacchetti LoRa")
        self.sequence.set("—")
        self.draw_signal()
        self.status.set("Mappa live")

    def close(self):
        if self.stop():
            self.disconnect()
            self.root.destroy()

    def poll(self):
        try:
            if self.port is not None:
                data = self.port.read(min(1048576, max(8192, self.port.in_waiting)))
                if data:
                    active = self.state == "running"
                    if active:
                        self.log.write(data)
                        self.log.flush()
                    lines = (self.pending + data).split(b"\n")
                    self.pending = lines.pop()
                    for line in lines:
                        decoded = line.decode("ascii", errors="replace").rstrip("\r")
                        consumed = self.device_line(decoded)
                        if not consumed and (active or self.state == "idle") and self.sync_line:
                            self.process(decoded)
                        self.sync_line = True
                    if self.pending and self.state == "paused":
                        self.sync_line = False
            if self.transfer and time.monotonic() > self.transfer_deadline:
                if self.transfer.startswith("memory-"):
                    self.memory.fail("Il Pico non risponde alla gestione memoria. "
                                     "Verifica il collegamento e il firmware RX aggiornato.")
                    return
                operation = "elenco" if self.transfer == "list" else "registrazione"
                self.cancel_transfer()
                messagebox.showerror(
                    "Pico", f"Nessuna risposta completa per {operation} da {self.port.port}. "
                    "Controlla di aver selezionato il ricevitore RX e che REC sia fermo.")
        except OSError as error:
            if isinstance(error, self.serial.SerialException):
                self.disconnect("Collegamento RX interrotto · ricollega il dispositivo e premi Connetti")
            else:
                self.disconnect("Errore di lettura o salvataggio")
                messagebox.showerror("Lettura RX", str(error))
        finally:
            self.refresh_batteries()
            self.root.after(1 if self.transfer else 50, self.poll)

    def marker(self, name, position):
        if self.reviewing:
            return
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
                if self.reviewing:
                    return
                if self.path is not None:
                    self.path.add_position(*position)
                    self.path.draw()
                elif len(segment) == 2:
                    self.path = self.map.set_path([fix[0] for fix in segment])
            return

        fields = line.split(",")
        if len(fields) not in (9, 12, 14, 16, 18):
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
        if len(fields) < 18:
            self.update_battery("TX", None)
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
        wind_text = "n/d"
        if len(fields) >= 14:
            try:
                wind_speed = float(fields[12])
                if math.isfinite(wind_speed) and wind_speed >= 0:
                    wind_text = f"{wind_speed:.2f} m/s"
            except ValueError:
                pass
        if not self.reviewing:
            self.sequence.set(f"#{sequence}")
            self.draw_signal(quality)
            self.received.set(f"Distanza RX–TX: {range_text}   ·   Vento TX: {wind_text}\n"
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
        if not self.reviewing:
            self.map.set_dot("packet", position, command=lambda _: self.status.set(label))


if __name__ == "__main__":
    import serial
    from serial.tools import list_ports
    from tracker_map import TrackerMap

    window = tk.Tk()
    Client(window, serial, list_ports, TrackerMap)
    window.mainloop()
