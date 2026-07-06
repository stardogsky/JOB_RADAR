"""Hybrid scoring: config-driven rules + embedding similarity. Spec 02 section 5."""
from .models import Job


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _title_component(title_low: str, cfg: dict, reasons: list) -> float:
    best, best_phrase = 0.0, None
    for phrase, weight in cfg["positive_titles"].items():
        if phrase in title_low and weight > best:
            best, best_phrase = float(weight), phrase
    if best_phrase and best >= 0.6:
        reasons.append(f"title matches target role ({best_phrase})")
    return best


def _similarity_component(cos: float, reasons: list) -> float:
    norm = _clamp((cos - 0.1) / 0.5, 0.0, 1.0)
    if norm >= 0.6:
        reasons.append("strong profile similarity")
    return norm


def _salary_component(job: Job, reasons: list, risks: list) -> float:
    if not job.salary_known:
        risks.append("salary unknown")
        return 0.4
    lo = job.salary_min_usd_month or 0
    if lo >= 2000:
        reasons.append(f"salary ${lo:.0f}+/mo")
        return 1.0
    if lo >= 1300:
        reasons.append(f"salary above threshold (${lo:.0f}/mo)")
        return 0.7
    # known salary with max >= threshold but min below it
    risks.append("salary range starts below threshold")
    return 0.4


def _remote_component(job: Job, reasons: list, risks: list) -> float:
    if job.remote_confidence == "yes":
        reasons.append("remote")
        return 1.0
    risks.append("remote status not fully confirmed")
    return 0.6


def _seniority_component(title_low: str, cfg: dict, reasons: list, risks: list) -> float:
    for word in cfg["seniority_negative"]:
        if word in title_low:
            risks.append(f"seniority mismatch ({word})")
            return 0.1
    for word in cfg["seniority_positive"]:
        if word in title_low:
            reasons.append(f"seniority fit ({word})")
            return 1.0
    return 0.6


def _keywords_component(text_low: str, cfg: dict, reasons: list) -> float:
    hits = [kw for kw in cfg["positive_keywords"] if kw in text_low]
    if hits:
        reasons.append("keywords: " + ", ".join(hits[:6]))
    return _clamp(len(hits) / 5.0, 0.0, 1.0)


def _penalties(text_low: str, loc_low: str, cfg: dict, risks: list) -> int:
    penalty = 0
    for kw in cfg["negative_keywords"]:
        if kw in text_low:
            penalty += 8
            risks.append(f"negative keyword: {kw}")
    penalty = min(penalty, 25)
    for pattern in cfg["location_risk_patterns"]:
        if pattern in text_low or pattern in loc_low:
            penalty += 10
            risks.append(f"location restriction ({pattern})")
            break
    return penalty


def categorize(score: int) -> str:
    if score >= 80:
        return "apply_first"
    if score >= 65:
        return "good"
    if score >= 50:
        return "maybe"
    if score >= 35:
        return "weak"
    return "skip"


def score_job(job: Job, cosine: float, cfg: dict) -> Job:
    if job.category == "skip":  # hard filter already decided
        job.score = 0
        return job
    reasons: list[str] = []
    risks: list[str] = []
    title_low = job.title.lower()
    text_low = f"{job.title} {job.description}".lower()
    loc_low = (job.location_raw or "").lower()
    w = cfg["weights"]
    raw = (
        w["title"] * _title_component(title_low, cfg, reasons)
        + w["similarity"] * _similarity_component(cosine, reasons)
        + w["salary"] * _salary_component(job, reasons, risks)
        + w["remote"] * _remote_component(job, reasons, risks)
        + w["seniority"] * _seniority_component(title_low, cfg, reasons, risks)
        + w["keywords"] * _keywords_component(text_low, cfg, reasons)
    )
    score = int(_clamp(round(raw * 100 - _penalties(text_low, loc_low, cfg, risks)), 0, 100))
    job.score = score
    job.category = categorize(score)
    job.reasons = reasons
    job.risks = risks
    return job
