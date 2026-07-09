from .base import http_get


def fetch(cfg: dict) -> list:
    """Return list of Working Nomads API response payloads (one per configured URL)."""
    return [http_get(url).json() for url in cfg["sources"]["workingnomads"]["urls"]]
