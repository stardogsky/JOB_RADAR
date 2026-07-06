from .base import http_get


def fetch(cfg: dict) -> list[dict]:
    """Return list of Remotive API response dicts (one per configured URL)."""
    payloads = []
    for url in cfg["sources"]["remotive"]["urls"]:
        payloads.append(http_get(url).json())
    return payloads
