"""Job Radar orchestration. One run: collect -> normalize -> dedupe -> filter ->
score -> store -> export -> notify. Exit 0 = ok/degraded, exit 1 = fatal."""
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .collectors import (
    arbeitnow, himalayas, jobicy, jobscollider, jobspresso,
    remoteok, remotive, wwr,
)
from .config import load_config
from .db import DB
from .dedupe import content_hash
from .embeddings import Similarity
from .export import export_csv
from .filters import apply_hard_filters
from .normalize import (
    normalize_arbeitnow, normalize_himalayas, normalize_jobicy,
    normalize_jobscollider, normalize_jobspresso,
    normalize_remoteok, normalize_remotive, normalize_wwr,
)
from .notify import build_digest, send_telegram
from .scoring import score_job

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("main")

LOCK_MAX_AGE_SEC = 3600

# Source registry. mode:
#   "each"   -> fetch(cfg) returns an iterable of payloads; normalize(payload, cfg) per payload
#   "single" -> fetch(cfg) returns one payload; normalize(payload, cfg) once
# Each source is isolated: one failing source never aborts the others.
SOURCES = [
    ("remotive", remotive.fetch, normalize_remotive, "each"),
    ("remoteok", remoteok.fetch, normalize_remoteok, "single"),
    ("wwr", wwr.fetch, normalize_wwr, "each"),
    ("himalayas", himalayas.fetch, normalize_himalayas, "each"),
    ("jobicy", jobicy.fetch, normalize_jobicy, "each"),
    ("arbeitnow", arbeitnow.fetch, normalize_arbeitnow, "each"),
    ("jobscollider", jobscollider.fetch, normalize_jobscollider, "each"),
    ("jobspresso", jobspresso.fetch, normalize_jobspresso, "each"),
]


def acquire_lock(root: Path) -> Path | None:
    lock = root / "data" / ".run.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age < LOCK_MAX_AGE_SEC:
            log.error("another run in progress (lock age %.0fs), aborting", age)
            return None
        log.warning("stale lock (%.0fs), overwriting", age)
    lock.write_text(datetime.now(timezone.utc).isoformat())
    return lock


def collect_all(cfg: dict) -> tuple[list, dict]:
    jobs, errors = [], {}
    for name, fetch_fn, normalize_fn, mode in SOURCES:
        src_cfg = cfg["sources"].get(name, {})
        if not src_cfg.get("enabled"):
            continue
        try:
            payloads = fetch_fn(cfg)
            if mode == "single":
                jobs.extend(normalize_fn(payloads, cfg))
            else:
                for payload in payloads:
                    jobs.extend(normalize_fn(payload, cfg))
        except Exception as exc:  # noqa: BLE001 - isolate source failures
            log.error("%s failed: %s", name, exc)
            errors[name] = str(exc)[:120]
    return jobs, errors


def run() -> int:
    cfg = load_config()
    root = Path(cfg["root"])
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    lock = acquire_lock(root)
    if lock is None:
        return 1
    try:
        db = DB(str(root / "data" / "jobs.sqlite"))

        if db.size_mb() > cfg["guards"]["max_db_mb"]:
            log.error("DB size guard tripped: %.1f MB", db.size_mb())
            send_telegram(f"Job Radar ALERT: DB size {db.size_mb():.0f} MB > guard. Run aborted.", cfg)
            return 1

        jobs, errors = collect_all(cfg)
        enabled_count = sum(1 for n, *_ in SOURCES if cfg["sources"].get(n, {}).get("enabled"))
        if jobs == [] and len(errors) >= max(3, enabled_count):
            log.error("all sources failed")
            send_telegram("Job Radar ALERT: all sources failed: " + str(errors), cfg)
            return 1
        log.info("fetched %d jobs, source errors: %s", len(jobs), errors or "none")

        seen = db.existing_hashes()
        fresh = []
        for job in jobs:
            job.content_hash = content_hash(job)
            if job.content_hash not in seen:
                seen.add(job.content_hash)
                fresh.append(job)
        log.info("new after dedupe: %d", len(fresh))

        guard_tripped = len(fresh) > cfg["guards"]["max_new_per_run"]

        for job in fresh:
            apply_hard_filters(job, cfg)

        to_score = [j for j in fresh if j.category != "skip"]
        sim = Similarity(str(root / "profile" / "resume_en.md"))
        cosines = sim.cosine_batch(
            [f"{j.title} {j.description[:4000]}" for j in to_score])
        for job, cos in zip(to_score, cosines):
            score_job(job, cos, cfg)
        for job in fresh:
            if job.score is None:
                job.score = 0

        inserted = sum(db.insert_job(j) for j in fresh)
        log.info("inserted %d rows", inserted)

        if guard_tripped:
            send_telegram(f"Job Radar ALERT: {len(fresh)} new jobs in one run "
                          f"(guard {cfg['guards']['max_new_per_run']}). Possible parser bug. "
                          f"Rows inserted, run stopped.", cfg)
            db.record_run(started_at, len(jobs), inserted, {**errors, "guard": "max_new_per_run"})
            return 1

        db.retention(cfg)
        run_count = db.record_run(started_at, len(jobs), inserted, errors)
        db.maybe_vacuum(run_count, cfg["guards"]["vacuum_every_runs"])

        dig = cfg["digest"]
        rows = db.top_today(dig["top_n"], dig["min_score"])
        fallback_used = False
        if not rows:
            rows = db.top_today(5, dig["fallback_min_score"])
            fallback_used = bool(rows)
        stats = {
            "date": datetime.now(timezone.utc).strftime("%d.%m.%Y"),
            "fetched": len(jobs), "inserted": inserted,
            "apply_first": sum(1 for j in fresh if j.category == "apply_first"),
            "good": sum(1 for j in fresh if j.category == "good"),
        }
        text = build_digest(rows, stats, errors, cfg)
        if fallback_used:
            text += "\n(показаны maybe-варианты: выше порога сегодня пусто)"
        export_csv(rows, str(root / "data" / "digest_latest.csv"))
        send_telegram(text, cfg)
        db.close()
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(run())
