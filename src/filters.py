"""Hard filters. Do not delete jobs; assign category='skip' with a reason."""
from .models import Job


def apply_hard_filters(job: Job, cfg: dict) -> Job:
    text = f"{job.title} {job.description}".lower()
    loc = (job.location_raw or "").lower()

    if job.remote_confidence == "no":
        job.category = "skip"
        job.reasons = ["skip: not remote"]
        return job

    if job.salary_known and job.salary_max_usd_month is not None \
            and job.salary_max_usd_month < cfg["salary_min_usd_month"]:
        job.category = "skip"
        job.reasons = [f"skip: salary below ${cfg['salary_min_usd_month']}/mo"]
        return job

    for pattern in cfg["us_only_patterns"]:
        if pattern in text or pattern in loc:
            job.category = "skip"
            job.reasons = [f"skip: US-only ({pattern})"]
            return job

    title_low = job.title.lower()
    for word in cfg["irrelevant_blacklist"]:
        if word in title_low:
            job.category = "skip"
            job.reasons = [f"skip: irrelevant role ({word})"]
            return job

    return job  # category stays None -> goes to scoring
