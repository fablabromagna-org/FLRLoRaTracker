import io
from PIL import Image, ImageDraw, ImageTk
from tkintermapview import TkinterMapView

from tracker_tiles import tile_session


class TrackerMap(TkinterMapView):
    def __init__(self, master):
        self.tile_session = tile_session()
        self.rx_marker = None
        super().__init__(master)
        self.set_tile_server("https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.dot_icons = {
            "RX": self.dot_icon(16, "#2563eb"),
            "TX": self.dot_icon(10, "#dc2626"),
            "packet": self.dot_icon(7, "#ea580c"),
        }

    def dot_icon(self, size, color):
        image = Image.new("RGBA", (size, size))
        ImageDraw.Draw(image).ellipse((0, 0, size - 1, size - 1),
                                     fill=color, outline="white", width=2 if size > 10 else 1)
        return ImageTk.PhotoImage(image)

    def set_dot(self, name, position, command=None):
        marker = self.set_marker(*position, icon=self.dot_icons[name], command=command)
        if name == "RX":
            self.rx_marker = marker
            self.manage_z_order()
        return marker

    def manage_z_order(self):
        super().manage_z_order()
        if self.rx_marker is not None and self.rx_marker.canvas_icon is not None:
            self.canvas.tag_raise(self.rx_marker.canvas_icon)

    def pre_cache(self):
        # Fetch only the tiles requested for display.
        pass

    def request_image(self, zoom, x, y, db_cursor=None):
        if not self.running or not (0 <= y < 2 ** zoom):
            return self.empty_tile_image
        url = f"https://tile.openstreetmap.org/{zoom}/{x % (2 ** zoom)}/{y}.png"
        try:
            response = self.tile_session.get(url, timeout=5)
            response.raise_for_status()
            with Image.open(io.BytesIO(response.content)) as image:
                tile = ImageTk.PhotoImage(image) if self.running else self.empty_tile_image
        except (OSError, RuntimeError, ValueError):
            return self.empty_tile_image
        self.tile_image_cache[f"{zoom}{x}{y}"] = tile
        return tile
