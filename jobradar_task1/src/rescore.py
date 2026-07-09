"""Recompute scores for the ENTIRE jobs table.

Run after updating the resume (profile/resume_en.md) or scoring rules in
config.yaml. Reloads every stored job, re-derives hard filters, recomputes
embedding similarity against the current resume, re-runs score_job, and writes
score/category/reasons/risks back. Idempotent; does not collect or notify.

From repo root:
    python -m src.rescore            # apply
    python -m src.rescore --dry-run  # preview, no writes
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

from .config import load_config
from .embeddings import Similarity
from .filters import apply_hard_filters
from .models import Job
from .scoring import score_job

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rescore")


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        source=row["source"],
        source_id=row["source_id"],
        title=row["title"],
        company=row["company"],
        url=row["url"],
        location_raw=row["location_raw"],
        remote_confidence=row["remote_confidence"],
        salary_raw=row["salary_raw"],
        salary_known=bool(row["salary_known"]),
        salary_min_usd_month=row["salary_min_usd_month"],
        salary_max_usd_month=row["salary_max_usd_month"],
        description=row["description"] or "",
        tags=json.loads(row["tags"] or "[]"),
        date_posted=row["date_posted"],
        fetched_at=row["fetched_at"] or "",
        content_hash=row["content_hash"] or "",
    )


def rescore(dry_run: bool = False) -> int:
    cfg = load_config()
    root = Path(cfg["root"])
    db_path = root / "data" / "jobs.sqlite"
    if not db_path.exists():
        log.error("no database at %s", db_path)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    log.info("loaded %d jobs", len(rows))
    if not rows:
        conn.close()
        return 0

    # (id, job, old_score, old_category) after re-deriving hard filters.
    items = []
    for row in rows:
        job = _row_to_job(row)
        job.category = None  # force full re-derivation
        job.score = None
        job.reasons = []
        job.risks = []
        apply_hard_filters(job, cfg)
        items.append((row["id"], job, row["score"], row["category"]))

    to_score = [(rid, j) for rid, j, _, _ in items if j.category != "skip"]
    log.info("scoring %d (skip after hard filter: %d)",
             len(to_score), len(items) - len(to_score))

    sim = Similarity(str(root / "profile" / "resume_en.md"))
    texts = [f"{j.title} {j.description[:4000]}" for _, j in to_score]
    cosines = sim.cosine_batch(texts) if texts else []
    for (_, job), cos in zip(to_score, cosines):
        score_job(job, cos, cfg)
    for _, job, _, _ in items:
        if job.score is None:
            job.score = 0

    changed = 0
    for rid, job, old_score, old_cat in items:
        if job.score != old_score or job.category != old_cat:
            changed += 1
        if not dry_run:
            conn.execute(
                "UPDATE jobs SET score=?, category=?, reasons=?, risks=? WHERE id=?",
                (job.score, job.category,
                 json.dumps(job.reasons, ensure_ascii=False),
                 json.dumps(job.risks, ensure_ascii=False), rid))
    if dry_run:
        log.info("[dry-run] %d rows, %d score/category changes (no writes)",
                 len(items), changed)
    else:
        conn.commit()
        log.info("updated %d rows, %d score/category changes", len(items), changed)
    conn.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Recompute all job scores.")
    ap.add_argument("--dry-run", action="store_true",
                    help="preview changes without writing to the DB")
    args = ap.parse_args()
    sys.exit(rescore(dry_run=args.dry_run))
