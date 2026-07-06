from dataclasses import dataclass, field


@dataclass
class Job:
    source: str
    source_id: str | None
    title: str
    company: str | None
    url: str
    location_raw: str | None
    remote_confidence: str  # yes | probably | no
    salary_raw: str | None
    salary_known: bool
    salary_min_usd_month: float | None
    salary_max_usd_month: float | None
    description: str
    tags: list = field(default_factory=list)
    date_posted: str | None = None
    fetched_at: str = ""
    content_hash: str = ""
    score: int | None = None
    category: str | None = None
    reasons: list = field(default_factory=list)
    risks: list = field(default_factory=list)
