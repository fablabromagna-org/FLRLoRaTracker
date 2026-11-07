"""Serial protocol and dialog for managing the Pico recording filesystem."""
import re
import time
import tkinter as tk
from tkinter import messagebox, ttk
import zlib


def local_recording(folder, name, size, crc):
    for path in folder.glob("*" + name.lstrip("/")):
        if (path.is_file() and path.stat().st_size == size and
                (zlib.crc32(path.read_bytes()) & 0xFFFFFFFF) == crc):
            return path
    return None


class MemoryManager:
    def __init__(self, client, recordings_dir):
        self.client = client
        self.folder = recordings_dir
        self.window = None
        self.files = []
        self.pending = []
        self.verified = []

    def request(self, command, phase):
        self.client.transfer = phase
        self.client.transfer_deadline = time.monotonic() + 30
        self.client.port.write((command + "\n").encode("ascii"))

    def open(self):
        c = self.client
        if c.transfer:
            messagebox.showinfo("Memoria Pico", "Attendi il termine del trasferimento.")
            return
        if c.port is None or c.port.port != c.ports.get().strip():
            c.connect()
            if c.port is None or c.port.port != c.ports.get().strip():
                return
        if c.device_recording:
            messagebox.showinfo("Memoria Pico", "Termina REC sul device prima di gestire la memoria.")
            return
        if self.window is None or not self.window.winfo_exists():
            self.window = tk.Toplevel(c.root)
            self.window.title("Memoria registrazioni Pico")
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            self.window.geometry("660x430")
            self.info = tk.StringVar(value="Lettura memoria…")
            ttk.Label(self.window, textvariable=self.info, padding=12).pack(fill="x")
            self.listbox = tk.Listbox(self.window, selectmode="extended", exportselection=False)
            self.listbox.pack(fill="both", expand=True, padx=12)
            ttk.Label(self.window, text="Seleziona i file da eliminare. È richiesta una copia locale verificata.",
                      padding=12).pack(fill="x")
            actions = ttk.Frame(self.window, padding=12)
            actions.pack(fill="x")
            ttk.Button(actions, text="AGGIORNA", command=self.open).pack(side="left")
            ttk.Button(actions, text="ELIMINA SELEZIONATE",
                       command=self.check_selected).pack(side="right")
        self.window.lift()
        self.files = []
        self.listbox.delete(0, "end")
        self.request("MEM\nLIST", "memory-list")

    def close(self):
        if (self.client.transfer or "").startswith("memory-"):
            messagebox.showinfo("Memoria Pico", "Attendi il termine dell'operazione.",
                                parent=self.window)
            return
        self.window.destroy()

    def check_selected(self):
        if self.client.transfer:
            return
        selected = self.listbox.curselection()
        if not selected:
            return
        self.pending = [self.files[index] for index in selected]
        self.verified = []
        self.check_next()

    def check_next(self):
        if self.pending:
            self.name, self.size = self.pending.pop(0)
            self.info.set("Verifica copia PC di " + self.name)
            self.request("CHECK " + self.name, "memory-check")
            return
        self.client.transfer = None
        if not messagebox.askyesno(
                "Elimina registrazioni dal Pico",
                "Copia locale verificata per tutti i file selezionati.\n\n"
                "Eliminare dal Pico questi file?\n" +
                "\n".join(name for name, _, _ in self.verified), parent=self.window):
            self.info.set("Cancellazione annullata")
            return
        self.pending = self.verified.copy()
        self.delete_next()

    def delete_next(self):
        if not self.pending:
            self.client.transfer = None
            self.open()
            return
        name, size, crc = self.pending.pop(0)
        self.name = name
        self.info.set("Eliminazione di " + name)
        self.request(f"DEL {name} {crc:08x} {size}", "memory-delete")

    def fail(self, text):
        self.client.cancel_transfer()
        self.pending = []
        self.verified = []
        if self.window is not None and self.window.winfo_exists():
            self.info.set(text)
        messagebox.showerror("Memoria Pico", text)

    def handle_line(self, line):
        c = self.client
        if not (c.transfer or "").startswith("memory-"):
            return False
        if line.startswith("# commands:"):
            self.fail("Per gestire la memoria serve il firmware aggiornato sul Pico RX.")
            return True
        if line in ("# file not found", "# delete_error", "# memory_error",
                    "# stop recording first or check storage"):
            self.fail("Operazione interrotta dal Pico. Verifica che REC sia fermo e aggiorna l'elenco.")
            return True
        if c.transfer == "memory-list":
            memory = re.fullmatch(r"# MEM (\d+) (\d+)", line)
            file = re.fullmatch(r"# /?(session\d{4}\.csv) (\d+)", line)
            if memory:
                total, used = map(int, memory.groups())
                self.info.set(f"Totale {total / 1024:.0f} KiB   ·   "
                              f"Occupati {used / 1024:.0f} KiB   ·   "
                              f"Liberi {(total - used) / 1024:.0f} KiB")
            if file:
                self.files.append(("/" + file[1], int(file[2])))
                self.listbox.insert("end", f"{file[1]}     {int(file[2]):,} byte")
            if line == "# END LIST":
                c.transfer = None
            return line.startswith("# ")
        if c.transfer == "memory-check":
            match = re.fullmatch(r"# CHECK (/session\d{4}\.csv) (\d+) ([0-9a-fA-F]{8})", line)
            if not match:
                return False
            name, size, crc = match[1], int(match[2]), int(match[3], 16)
            if name != self.name or size != self.size:
                self.fail("Il file sul Pico è cambiato. Aggiorna l'elenco.")
                return True
            try:
                backed_up = local_recording(self.folder, name, size, crc)
            except OSError as error:
                self.fail(str(error))
                return True
            if not backed_up:
                self.fail(f"Copia locale verificata assente per {name}. "
                          "Scarica prima i file con REGISTRAZIONI.")
                return True
            self.verified.append((name, size, crc))
            self.check_next()
            return True
        if c.transfer == "memory-delete" and line == "# DELETED " + self.name:
            self.delete_next()
            return True
        return False
