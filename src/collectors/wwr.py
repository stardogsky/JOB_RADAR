from .base import http_get


def fetch(cfg: dict) -> list[str]:
    """Return list of RSS XML texts, one per feed."""
    return [http_get(url, accept="application/rss+xml").text
            for url in cfg["sources"]["wwr"]["feeds"]]
