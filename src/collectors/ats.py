"""Generic ATS collector (task 1B).

Reads cfg["sources"]["ats"]["companies"] = list of {ats, slug, name}. For each
company it hits the public, no-auth job-board endpoint of its ATS and returns a
list of {ats, slug, name, payload} dicts (one per company). Each company is
isolated: a dead slug is logged and skipped, never aborting the rest.

Supported ATS (all public, keyless):
  greenhouse | lever | ashby | recruitee | smartrecruiters | breezy
"""
import logging

from .base import http_get

log = logging.getLogger("collectors")

# 'SLUG' is replaced with the company board token at fetch time.
ATS_URL = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/SLUG/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/SLUG?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/SLUG?includeCompensation=true",
    "recruitee": "https://SLUG.recruitee.com/api/offers/",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/SLUG/postings?limit=100",
    "breezy": "https://SLUG.breezy.hr/json",
}


def fetch(cfg: dict) -> list[dict]:
    companies = cfg.get("sources", {}).get("ats", {}).get("companies", []) or []
    out = []
    for entry in companies:
        ats = str(entry.get("ats") or "").strip().lower()
        slug = str(entry.get("slug") or "").strip()
        if ats not in ATS_URL or not slug:
            log.warning("ats: bad entry %r (unknown ats or empty slug)", entry)
            continue
        url = ATS_URL[ats].replace("SLUG", slug)
        try:
            payload = http_get(url).json()
        except Exception as exc:  # noqa: BLE001 - isolate per-company failures
            log.warning("ats %s/%s failed: %s", ats, slug, str(exc)[:120])
            continue
        out.append({"ats": ats, "slug": slug,
                    "name": entry.get("name") or slug, "payload": payload})
    return out
