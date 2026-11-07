import os
from pathlib import Path

import requests_cache


def tile_session():
    cache_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TrackerLoRa"
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = requests_cache.CachedSession(
        str(cache_dir / "map-tiles"), cache_control=True, expire_after=604800,
        stale_if_error=True)
    session.headers["User-Agent"] = "TrackerLoRa-Desktop/1.0"
    return session
