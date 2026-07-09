from .base import http_get


def fetch(cfg: dict) -> list[dict]:
    """Return list of Landing.jobs API response payloads (one per configured URL)."""
    return [http_get(url).json() for url in cfg["sources"]["landingjobs"]["urls"]]
