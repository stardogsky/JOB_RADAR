from .base import http_get


def fetch(cfg: dict) -> list:
    return http_get(cfg["sources"]["remoteok"]["url"]).json()
