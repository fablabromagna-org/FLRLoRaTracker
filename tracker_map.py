import io
import os
from pathlib import Path

import requests_cache
from PIL import Image, ImageTk
from tkintermapview import TkinterMapView


class TrackerMap(TkinterMapView):
    def __init__(self, master):
        cache_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TrackerLoRa"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.tile_session = requests_cache.CachedSession(
            str(cache_dir / "map-tiles"), cache_control=True, expire_after=604800,
            stale_if_error=True)
        self.tile_session.headers["User-Agent"] = "TrackerLoRa-Desktop/1.0"
        super().__init__(master)
        self.set_tile_server("https://tile.openstreetmap.org/{z}/{x}/{y}.png")

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
