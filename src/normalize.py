"""Source payloads -> unified Job objects."""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .models import Job
from .salary import parse_salary_numbers, parse_salary_text
from .textclean import clean_description, normalize_spaces

log = logging.getLogger("normalize")



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _has_remote_marker(text: str, cfg: dict) -> bool:
    low = text.lower()
    return any(marker in low for marker in cfg["remote_positive_markers"])


# ---------------- Remotive ----------------

def normalize_remotive(data: dict, cfg: dict) -> list[Job]:
    jobs = []
    for item in data.get("jobs", []):
        title = normalize_spaces(str(item.get("title") or ""))
        url = item.get("url") or ""
        if not title or not url:
            log.warning("remotive: skipped item without title/url id=%s", item.get("id"))
            continue
        description = clean_description(item.get("description") or "")
        salary_raw = (item.get("salary") or "").strip() or None
        known, lo, hi = parse_salary_text(salary_raw, cfg)
        jobs.append(Job(
            source="remotive",
            source_id=str(item.get("id") or "") or None,
            title=title,
            company=normalize_spaces(str(item.get("company_name") or "")) or None,
            url=url,
            location_raw=(item.get("candidate_required_location") or "").strip() or None,
            remote_confidence="yes",
            salary_raw=salary_raw,
            salary_known=known,
            salary_min_usd_month=lo,
            salary_max_usd_month=hi,
            description=description,
            tags=[str(t) for t in (item.get("tags") or [])],
            date_posted=(item.get("publication_date") or "")[:10] or None,
            fetched_at=_now_iso(),
        ))
    return jobs


# ---------------- RemoteOK ----------------

def _remoteok_salary(item: dict, description: str, cfg: dict):
    smin = item.get("salary_min") or 0
    smax = item.get("salary_max") or 0
    if not smin and not smax:
        return None, False, None, None
    # Currency sanity check: find the numeric value inside the description and
    # inspect 200 chars around it for a non-USD currency code (spec 2.2).
    probe = str(int(smin or smax))
    idx = description.replace(",", "").find(probe)
    if idx >= 0:
        window = description.replace(",", "")[max(0, idx - 200): idx + 200]
        known, lo, hi = parse_salary_text(window, cfg)
        if not known:
            return window[max(0, idx - 30): idx + 60].strip(), False, None, None
    known, lo, hi = parse_salary_numbers(float(smin), float(smax), cfg)
    return f"{smin}-{smax} (yearly fields)", known, lo, hi


def _remoteok_remote_confidence(location: str, title: str, description: str, cfg: dict) -> str:
    """City-like location (contains a comma, e.g. 'Airdrie, ' or 'Lisboa, Portugal')
    with no remote markers anywhere -> 'no'. Everything else -> 'probably'."""
    loc = (location or "").strip()
    if loc and "," in loc and not _has_remote_marker(loc, cfg):
        if not _has_remote_marker(title + " " + description, cfg):
            return "no"
    return "probably"


def normalize_remoteok(items: list, cfg: dict) -> list[Job]:
    jobs = []
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            continue  # legal-notice header and any malformed rows
        title = normalize_spaces(str(item.get("position") or ""))
        url = item.get("url") or item.get("apply_url") or ""
        if not title or not url:
            log.warning("remoteok: skipped item without title/url id=%s", item.get("id"))
            continue
        description = clean_description(item.get("description") or "")
        salary_raw, known, lo, hi = _remoteok_salary(item, description, cfg)
        jobs.append(Job(
            source="remoteok",
            source_id=str(item.get("id")),
            title=title,
            company=normalize_spaces(str(item.get("company") or "")) or None,
            url=url,
            location_raw=(item.get("location") or "").strip() or None,
            remote_confidence=_remoteok_remote_confidence(
                item.get("location") or "", title, description, cfg),
            salary_raw=salary_raw,
            salary_known=known,
            salary_min_usd_month=lo,
            salary_max_usd_month=hi,
            description=description,
            tags=[str(t) for t in (item.get("tags") or [])],
            date_posted=(item.get("date") or "")[:10] or None,
            fetched_at=_now_iso(),
        ))
    return jobs


# ---------------- We Work Remotely (RSS) ----------------

HEADQUARTERS_RE = re.compile(r"Headquarters:\s*([^\n]+)", re.IGNORECASE)


def normalize_wwr(xml_text: str, cfg: dict) -> list[Job]:
    jobs = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.error("wwr: RSS parse error: %s", exc)
        return jobs
    for item in root.iter("item"):
        raw_title = normalize_spaces(item.findtext("title") or "")
        link = (item.findtext("link") or item.findtext("guid") or "").strip()
        if not raw_title or not link:
            continue
        if ": " in raw_title:
            company, _, title = raw_title.partition(": ")
        else:
            company, title = None, raw_title
        description = clean_description(item.findtext("description") or "")
        region = (item.findtext("region") or "").strip()
        location = region or None
        if not location:
            hq = HEADQUARTERS_RE.search(description)
            location = hq.group(1).strip() if hq else None
        salary_raw = None
        sal_match = re.search(r"(salary[^.\n]{0,120}|\$\s?\d[\d,]*(?:\s*-\s*\$?\d[\d,]*)?[^.\n]{0,40})",
                              description, re.IGNORECASE)
        if sal_match and "$" in sal_match.group(0):
            salary_raw = normalize_spaces(sal_match.group(0))
        known, lo, hi = parse_salary_text(salary_raw, cfg)
        date_posted = None
        pub = item.findtext("pubDate")
        if pub:
            try:
                date_posted = parsedate_to_datetime(pub).date().isoformat()
            except (TypeError, ValueError):
                pass
        jobs.append(Job(
            source="wwr",
            source_id=(item.findtext("guid") or link).strip(),
            title=normalize_spaces(title),
            company=normalize_spaces(company) if company else None,
            url=link,
            location_raw=location,
            remote_confidence="yes",
            salary_raw=salary_raw,
            salary_known=known,
            salary_min_usd_month=lo,
            salary_max_usd_month=hi,
            description=description,
            tags=[],
            date_posted=date_posted,
            fetched_at=_now_iso(),
        ))
    return jobs
