import hashlib

from .models import Job
from .textclean import normalize_spaces


def content_hash(job: Job) -> str:
    base = "|".join([
        normalize_spaces((job.company or "").lower()),
        normalize_spaces(job.title.lower()),
        normalize_spaces(job.description[:500].lower()),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
