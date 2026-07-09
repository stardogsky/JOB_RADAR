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


# ---------------- Jobicy (API v2) ----------------

def _annual_salary(smin, smax, currency: str, cfg: dict):
    """Shared yearly-salary handling for API sources that expose numeric
    annual min/max + currency. USD -> numeric path; other -> text path (which
    applies currency_rates_to_usd from config). Returns (raw, known, lo, hi)."""
    cur = (currency or "USD").upper()
    try:
        smin_f = float(smin) if smin not in (None, "", 0, "0") else 0.0
        smax_f = float(smax) if smax not in (None, "", 0, "0") else 0.0
    except (TypeError, ValueError):
        return None, False, None, None
    if not smin_f and not smax_f:
        return None, False, None, None
    if cur == "USD":
        raw = f"{smin}-{smax} USD/year"
        known, lo, hi = parse_salary_numbers(smin_f or smax_f, smax_f or smin_f, cfg)
        return raw, known, lo, hi
    raw = f"{smin}-{smax} {cur} per year"
    known, lo, hi = parse_salary_text(raw, cfg)
    return raw, known, lo, hi


def normalize_jobicy(data: dict, cfg: dict) -> list[Job]:
    jobs = []
    for item in data.get("jobs", []):
        title = normalize_spaces(str(item.get("jobTitle") or ""))
        url = item.get("url") or ""
        if not title or not url:
            log.warning("jobicy: skipped item without title/url id=%s", item.get("id"))
            continue
        description = clean_description(item.get("jobDescription") or item.get("jobExcerpt") or "")
        geo = normalize_spaces(str(item.get("jobGeo") or ""))
        remote_confidence = "yes" if _has_remote_marker(geo or "anywhere", cfg) else "probably"
        salary_raw, known, lo, hi = _annual_salary(
            item.get("annualSalaryMin"), item.get("annualSalaryMax"),
            item.get("salaryCurrency"), cfg)
        tags = [str(t) for t in (item.get("jobIndustry") or [])]
        tags += [str(t) for t in (item.get("jobType") or [])]
        jobs.append(Job(
            source="jobicy",
            source_id=str(item.get("id") or "") or None,
            title=title,
            company=normalize_spaces(str(item.get("companyName") or "")) or None,
            url=url,
            location_raw=geo or None,
            remote_confidence=remote_confidence,
            salary_raw=salary_raw,
            salary_known=known,
            salary_min_usd_month=lo,
            salary_max_usd_month=hi,
            description=description,
            tags=tags,
            date_posted=(str(item.get("pubDate") or ""))[:10] or None,
            fetched_at=_now_iso(),
        ))
    return jobs


# ---------------- Arbeitnow (API) ----------------

def normalize_arbeitnow(data: dict, cfg: dict) -> list[Job]:
    jobs = []
    for item in data.get("data", []):
        title = normalize_spaces(str(item.get("title") or ""))
        url = item.get("url") or ""
        if not title or not url:
            log.warning("arbeitnow: skipped item without title/url slug=%s", item.get("slug"))
            continue
        description = clean_description(item.get("description") or "")
        location = normalize_spaces(str(item.get("location") or ""))
        is_remote = bool(item.get("remote"))
        if not is_remote:
            remote_confidence = "no"
        elif not location or _has_remote_marker(location, cfg):
            remote_confidence = "yes"
        else:
            remote_confidence = "probably"
        known, lo, hi = parse_salary_text(None, cfg)  # Arbeitnow API exposes no salary
        date_posted = None
        created = item.get("created_at")
        if created:
            try:
                date_posted = datetime.fromtimestamp(int(created), tz=timezone.utc).date().isoformat()
            except (TypeError, ValueError, OSError):
                date_posted = str(created)[:10]
        tags = [str(t) for t in (item.get("tags") or [])]
        tags += [str(t) for t in (item.get("job_types") or [])]
        jobs.append(Job(
            source="arbeitnow",
            source_id=str(item.get("slug") or "") or None,
            title=title,
            company=normalize_spaces(str(item.get("company_name") or "")) or None,
            url=url,
            location_raw=location or None,
            remote_confidence=remote_confidence,
            salary_raw=None,
            salary_known=known,
            salary_min_usd_month=lo,
            salary_max_usd_month=hi,
            description=description,
            tags=tags,
            date_posted=date_posted,
            fetched_at=_now_iso(),
        ))
    return jobs


# ---------------- Himalayas (API) ----------------

def normalize_himalayas(data: dict, cfg: dict) -> list[Job]:
    jobs = []
    for item in data.get("jobs", []):
        title = normalize_spaces(str(item.get("title") or ""))
        url = item.get("applicationLink") or item.get("guid") or ""
        if not title or not url:
            log.warning("himalayas: skipped item without title/url guid=%s", item.get("guid"))
            continue
        description = clean_description(item.get("description") or item.get("excerpt") or "")
        restrictions = item.get("locationRestrictions") or []
        if isinstance(restrictions, str):
            restrictions = [restrictions]
        location = ", ".join(str(r) for r in restrictions) or None
        if not restrictions or _has_remote_marker(location or "worldwide", cfg):
            remote_confidence = "yes"
        else:
            remote_confidence = "probably"
        salary_raw, known, lo, hi = _annual_salary(
            item.get("minSalary") or item.get("salaryMin"),
            item.get("maxSalary") or item.get("salaryMax"),
            item.get("salaryCurrency"), cfg)
        date_posted = None
        pub = item.get("pubDate")
        if pub:
            try:
                date_posted = datetime.fromtimestamp(int(pub), tz=timezone.utc).date().isoformat()
            except (TypeError, ValueError, OSError):
                date_posted = str(pub)[:10]
        tags = [str(t) for t in (item.get("categories") or [])]
        tags += [str(s) for s in (item.get("seniority") or [])]
        jobs.append(Job(
            source="himalayas",
            source_id=str(item.get("guid") or url),
            title=title,
            company=normalize_spaces(str(item.get("companyName") or "")) or None,
            url=url,
            location_raw=location,
            remote_confidence=remote_confidence,
            salary_raw=salary_raw,
            salary_known=known,
            salary_min_usd_month=lo,
            salary_max_usd_month=hi,
            description=description,
            tags=tags,
            date_posted=date_posted,
            fetched_at=_now_iso(),
        ))
    return jobs


# ---------------- Generic remote-only RSS (JobsCollider, Jobspresso) ----------------

def _normalize_rss(xml_text: str, source: str, cfg: dict) -> list[Job]:
    jobs = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.error("%s: RSS parse error: %s", source, exc)
        return jobs
    for item in root.iter("item"):
        title = normalize_spaces(item.findtext("title") or "")
        link = (item.findtext("link") or item.findtext("guid") or "").strip()
        if not title or not link:
            continue
        description = clean_description(item.findtext("description") or "")
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
        tags = [c.text.strip() for c in item.findall("category") if c is not None and c.text]
        jobs.append(Job(
            source=source,
            source_id=(item.findtext("guid") or link).strip(),
            title=title,
            company=None,
            url=link,
            location_raw=None,
            remote_confidence="yes",  # remote-only boards
            salary_raw=salary_raw,
            salary_known=known,
            salary_min_usd_month=lo,
            salary_max_usd_month=hi,
            description=description,
            tags=tags,
            date_posted=date_posted,
            fetched_at=_now_iso(),
        ))
    return jobs


def normalize_jobscollider(xml_text: str, cfg: dict) -> list[Job]:
    return _normalize_rss(xml_text, "jobscollider", cfg)


def normalize_jobspresso(xml_text: str, cfg: dict) -> list[Job]:
    return _normalize_rss(xml_text, "jobspresso", cfg)


# ---------------- Landing.jobs (API) ----------------

def normalize_landingjobs(payload, cfg: dict) -> list[Job]:
    items = payload.get("jobs", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = normalize_spaces(str(item.get("title") or item.get("role") or ""))
        url = item.get("url") or item.get("landing_page") or item.get("apply_url") or ""
        if not title or not url:
            continue
        description = clean_description(item.get("description") or item.get("summary") or "")
        loc = normalize_spaces(str(item.get("location") or item.get("city") or ""))
        remote_flag = item.get("remote")
        if remote_flag is True or _has_remote_marker(loc or "", cfg):
            conf = "yes"
        elif remote_flag is False and loc:
            conf = "no"
        else:
            conf = "probably"
        salary_raw = item.get("salary") or item.get("salary_range")
        salary_raw = normalize_spaces(str(salary_raw)) if salary_raw else None
        known, lo, hi = parse_salary_text(salary_raw, cfg)
        tags = [str(t) for t in (item.get("tags") or item.get("skills") or [])]
        jobs.append(Job(
            source="landingjobs",
            source_id=str(item.get("id") or "") or None,
            title=title,
            company=normalize_spaces(str(item.get("company_name") or item.get("company") or "")) or None,
            url=url,
            location_raw=loc or None,
            remote_confidence=conf,
            salary_raw=salary_raw,
            salary_known=known,
            salary_min_usd_month=lo,
            salary_max_usd_month=hi,
            description=description,
            tags=tags,
            date_posted=(str(item.get("published_at") or item.get("created_at") or ""))[:10] or None,
            fetched_at=_now_iso(),
        ))
    return jobs


# ---------------- Working Nomads (API) ----------------

def normalize_workingnomads(payload, cfg: dict) -> list[Job]:
    items = payload.get("jobs", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = normalize_spaces(str(item.get("title") or ""))
        url = item.get("url") or ""
        if not title or not url:
            continue
        description = clean_description(item.get("description") or "")
        loc = normalize_spaces(str(item.get("location") or ""))
        conf = "yes" if (not loc or _has_remote_marker(loc, cfg)) else "probably"
        raw_tags = item.get("tags") or item.get("category_name") or []
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        jobs.append(Job(
            source="workingnomads",
            source_id=str(item.get("id") or url),
            title=title,
            company=normalize_spaces(str(item.get("company_name") or "")) or None,
            url=url,
            location_raw=loc or None,
            remote_confidence=conf,
            salary_raw=None,
            salary_known=parse_salary_text(None, cfg)[0],
            salary_min_usd_month=None,
            salary_max_usd_month=None,
            description=description,
            tags=[str(t) for t in raw_tags],
            date_posted=(str(item.get("pub_date") or ""))[:10] or None,
            fetched_at=_now_iso(),
        ))
    return jobs


# ---------------- Freelancer (RSS, disabled by default) ----------------

def normalize_freelancer(xml_text: str, cfg: dict) -> list[Job]:
    return _normalize_rss(xml_text, "freelancer", cfg)


# ---------------- ATS company boards (Greenhouse/Lever/Ashby/...) ----------------

def _ats_remote(loc: str, remote_flag, text: str, cfg: dict) -> str:
    """Remote confidence for company ATS boards. Explicit API remote flag wins;
    otherwise fall back to markers in location/description. A city-like location
    with no remote marker anywhere -> 'no' (hard-filtered as not-remote)."""
    if remote_flag is True:
        return "yes"
    if _has_remote_marker(f"{loc} {text}", cfg):
        return "yes"
    if remote_flag is False:
        return "no"
    if loc and not _has_remote_marker(loc, cfg):
        return "no"
    return "probably"


def _str(v) -> str:
    return normalize_spaces(str(v)) if v is not None else ""


def _norm_greenhouse(payload: dict, company: str, cfg: dict) -> list[Job]:
    jobs = []
    for item in (payload.get("jobs") or []):
        title = _str(item.get("title"))
        url = item.get("absolute_url") or ""
        if not title or not url:
            continue
        description = clean_description(item.get("content") or "")
        loc = _str((item.get("location") or {}).get("name"))
        tags = [d.get("name") for d in (item.get("departments") or []) if isinstance(d, dict) and d.get("name")]
        jobs.append(Job(
            source="greenhouse", source_id=str(item.get("id") or "") or None,
            title=title, company=company or _str(item.get("company_name")) or None, url=url,
            location_raw=loc or None,
            remote_confidence=_ats_remote(loc, None, f"{title} {description}", cfg),
            salary_raw=None, salary_known=parse_salary_text(None, cfg)[0],
            salary_min_usd_month=None, salary_max_usd_month=None,
            description=description, tags=[str(t) for t in tags],
            date_posted=(str(item.get("updated_at") or ""))[:10] or None,
            fetched_at=_now_iso()))
    return jobs


def _norm_lever(payload, company: str, cfg: dict) -> list[Job]:
    items = payload if isinstance(payload, list) else (payload.get("data") or [])
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _str(item.get("text"))
        url = item.get("hostedUrl") or item.get("applyUrl") or ""
        if not title or not url:
            continue
        description = clean_description(item.get("descriptionPlain") or item.get("description") or "")
        cats = item.get("categories") or {}
        loc = _str(cats.get("location"))
        wtype = str(item.get("workplaceType") or "").lower()
        flag = True if wtype == "remote" else (False if wtype in ("on-site", "onsite") else None)
        sr = item.get("salaryRange") or {}
        if sr.get("min") or sr.get("max"):
            salary_raw, known, lo, hi = _annual_salary(sr.get("min"), sr.get("max"), sr.get("currency"), cfg)
        else:
            salary_raw, (known, lo, hi) = None, parse_salary_text(None, cfg)
        tags = [str(v) for v in (cats.get("team"), cats.get("department"), cats.get("commitment")) if v]
        date_posted = None
        created = item.get("createdAt")
        if created:
            try:
                date_posted = datetime.fromtimestamp(int(created) / 1000, tz=timezone.utc).date().isoformat()
            except (TypeError, ValueError, OSError):
                pass
        jobs.append(Job(
            source="lever", source_id=str(item.get("id") or "") or None,
            title=title, company=company or None, url=url, location_raw=loc or None,
            remote_confidence=_ats_remote(loc, flag, f"{title} {description}", cfg),
            salary_raw=salary_raw, salary_known=known,
            salary_min_usd_month=lo, salary_max_usd_month=hi,
            description=description, tags=tags, date_posted=date_posted, fetched_at=_now_iso()))
    return jobs


def _norm_ashby(payload: dict, company: str, cfg: dict) -> list[Job]:
    jobs = []
    for item in (payload.get("jobs") or []):
        title = _str(item.get("title"))
        url = item.get("jobUrl") or item.get("applyUrl") or ""
        if not title or not url:
            continue
        description = clean_description(item.get("descriptionPlain") or item.get("descriptionHtml") or "")
        loc = _str(item.get("location"))
        flag = item.get("isRemote")
        salary_raw = item.get("compensationTierSummary")
        salary_raw = _str(salary_raw) or None
        known, lo, hi = parse_salary_text(salary_raw, cfg)
        tags = [str(v) for v in (item.get("department"), item.get("team"), item.get("employmentType")) if v]
        jobs.append(Job(
            source="ashby", source_id=str(item.get("id") or "") or None,
            title=title, company=company or None, url=url, location_raw=loc or None,
            remote_confidence=_ats_remote(loc, flag, f"{title} {description}", cfg),
            salary_raw=salary_raw, salary_known=known,
            salary_min_usd_month=lo, salary_max_usd_month=hi,
            description=description, tags=tags,
            date_posted=(str(item.get("publishedAt") or ""))[:10] or None,
            fetched_at=_now_iso()))
    return jobs


def _norm_recruitee(payload: dict, company: str, cfg: dict) -> list[Job]:
    jobs = []
    for item in (payload.get("offers") or []):
        title = _str(item.get("title"))
        url = item.get("careers_url") or item.get("careers_apply_url") or ""
        if not title or not url:
            continue
        description = clean_description(item.get("description") or "")
        loc = ", ".join(p for p in (_str(item.get("city")), _str(item.get("country"))) if p) or _str(item.get("location"))
        flag = True if (item.get("remote") is True or str(item.get("location") or "").lower() == "remote") else None
        jobs.append(Job(
            source="recruitee", source_id=str(item.get("id") or "") or None,
            title=title, company=company or None, url=url, location_raw=loc or None,
            remote_confidence=_ats_remote(loc, flag, f"{title} {description}", cfg),
            salary_raw=None, salary_known=parse_salary_text(None, cfg)[0],
            salary_min_usd_month=None, salary_max_usd_month=None,
            description=description,
            tags=[str(t) for t in (item.get("tags") or [])],
            date_posted=(str(item.get("published_at") or ""))[:10] or None,
            fetched_at=_now_iso()))
    return jobs


def _norm_smartrecruiters(payload: dict, company: str, cfg: dict) -> list[Job]:
    jobs = []
    for item in (payload.get("content") or []):
        title = _str(item.get("name"))
        loc_obj = item.get("location") or {}
        pid = item.get("id") or ""
        ident = (item.get("company") or {}).get("identifier") or company
        url = item.get("ref") or ("https://jobs.smartrecruiters.com/" + str(ident) + "/" + str(pid))
        if not title or not url:
            continue
        loc = ", ".join(p for p in (_str(loc_obj.get("city")), _str(loc_obj.get("country"))) if p)
        flag = True if loc_obj.get("remote") is True else None
        jobs.append(Job(
            source="smartrecruiters", source_id=str(pid) or None,
            title=title, company=company or None, url=url, location_raw=loc or None,
            remote_confidence=_ats_remote(loc, flag, title, cfg),
            salary_raw=None, salary_known=parse_salary_text(None, cfg)[0],
            salary_min_usd_month=None, salary_max_usd_month=None,
            description="", tags=[],
            date_posted=(str(item.get("releasedDate") or ""))[:10] or None,
            fetched_at=_now_iso()))
    return jobs


def _norm_breezy(payload, company: str, cfg: dict) -> list[Job]:
    items = payload if isinstance(payload, list) else (payload.get("jobs") or [])
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _str(item.get("name"))
        url = item.get("url") or ""
        if not title or not url:
            continue
        description = clean_description(item.get("description") or "")
        loc_obj = item.get("location") or {}
        country = loc_obj.get("country")
        country = country.get("name") if isinstance(country, dict) else country
        loc = ", ".join(p for p in (_str(loc_obj.get("name")), _str(country)) if p)
        flag = True if loc_obj.get("is_remote") is True else None
        jtype = item.get("type")
        jtype = jtype.get("name") if isinstance(jtype, dict) else jtype
        jobs.append(Job(
            source="breezy", source_id=str(item.get("id") or url),
            title=title, company=company or None, url=url, location_raw=loc or None,
            remote_confidence=_ats_remote(loc, flag, f"{title} {description}", cfg),
            salary_raw=None, salary_known=parse_salary_text(None, cfg)[0],
            salary_min_usd_month=None, salary_max_usd_month=None,
            description=description, tags=[str(t) for t in ([jtype] if jtype else [])],
            date_posted=(str(item.get("published_date") or ""))[:10] or None,
            fetched_at=_now_iso()))
    return jobs


_ATS_DISPATCH = {
    "greenhouse": _norm_greenhouse,
    "lever": _norm_lever,
    "ashby": _norm_ashby,
    "recruitee": _norm_recruitee,
    "smartrecruiters": _norm_smartrecruiters,
    "breezy": _norm_breezy,
}


def normalize_ats(entry: dict, cfg: dict) -> list[Job]:
    """entry = {ats, slug, name, payload} produced by collectors.ats.fetch."""
    fn = _ATS_DISPATCH.get(entry.get("ats"))
    if not fn:
        return []
    try:
        return fn(entry.get("payload") or {}, entry.get("name") or entry.get("slug") or "", cfg)
    except Exception as exc:  # noqa: BLE001 - one bad board must not kill the run
        log.error("ats normalize %s/%s failed: %s", entry.get("ats"), entry.get("slug"), str(exc)[:150])
        return []
