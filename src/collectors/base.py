import logging
import time

import requests

log = logging.getLogger("collectors")

USER_AGENT = "job-radar/1.0 (personal job search; contact in repo)"
TIMEOUT = (10, 30)
RETRIES = 2
BACKOFFS = (5, 15)


def http_get(url: str, accept: str = "application/json") -> requests.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    last_exc: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
            if resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last_exc = exc
            if attempt < RETRIES:
                wait = BACKOFFS[min(attempt, len(BACKOFFS) - 1)]
                log.warning("GET %s failed (%s), retry in %ss", url, exc, wait)
                time.sleep(wait)
    raise RuntimeError(f"GET {url} failed after {RETRIES + 1} attempts: {last_exc}")
