from .base import http_get


def fetch(cfg: dict) -> list[dict]:
    """Return list of Himalayas API response dicts (one per configured URL)."""
    return [http_get(url).json() for url in cfg["sources"]["himalayas"]["urls"]]
