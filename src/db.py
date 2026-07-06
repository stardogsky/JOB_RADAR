import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job

log = logging.getLogger("db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  content_hash TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  source_id TEXT,
  title TEXT NOT NULL,
  company TEXT,
  url TEXT NOT NULL,
  location_raw TEXT,
  remote_confidence TEXT NOT NULL,
  salary_raw TEXT,
  salary_known INTEGER NOT NULL DEFAULT 0,
  salary_min_usd_month REAL,
  salary_max_usd_month REAL,
  description TEXT,
  tags TEXT,
  date_posted TEXT,
  fetched_at TEXT NOT NULL,
  score INTEGER,
  category TEXT,
  reasons TEXT,
  risks TEXT,
  status TEXT NOT NULL DEFAULT 'new'
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_fetched ON jobs(fetched_at);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT, finished_at TEXT,
  fetched_total INTEGER, inserted_new INTEGER,
  errors TEXT
);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def size_mb(self) -> float:
        return os.path.getsize(self.path) / 1_048_576 if os.path.exists(self.path) else 0.0

    def existing_hashes(self) -> set[str]:
        rows = self.conn.execute("SELECT content_hash FROM jobs").fetchall()
        return {r[0] for r in rows}

    def insert_job(self, job: Job) -> bool:
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO jobs
               (content_hash, source, source_id, title, company, url, location_raw,
                remote_confidence, salary_raw, salary_known, salary_min_usd_month,
                salary_max_usd_month, description, tags, date_posted, fetched_at,
                score, category, reasons, risks)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job.content_hash, job.source, job.source_id, job.title, job.company,
             job.url, job.location_raw, job.remote_confidence, job.salary_raw,
             int(job.salary_known), job.salary_min_usd_month, job.salary_max_usd_month,
             job.description, json.dumps(job.tags, ensure_ascii=False), job.date_posted,
             job.fetched_at, job.score, job.category,
             json.dumps(job.reasons, ensure_ascii=False),
             json.dumps(job.risks, ensure_ascii=False)))
        return cur.rowcount > 0

    def retention(self, cfg: dict) -> int:
        now = datetime.now(timezone.utc)
        weak_cutoff = (now - timedelta(days=cfg["retention_days"]["weak"])).isoformat()
        all_cutoff = (now - timedelta(days=cfg["retention_days"]["all_new"])).isoformat()
        cur = self.conn.execute(
            "DELETE FROM jobs WHERE category IN ('skip','weak') AND fetched_at < ? AND status='new'",
            (weak_cutoff,))
        deleted = cur.rowcount
        cur = self.conn.execute(
            "DELETE FROM jobs WHERE fetched_at < ? AND status='new'", (all_cutoff,))
        deleted += cur.rowcount
        self.conn.commit()
        if deleted:
            log.info("retention: deleted %d rows", deleted)
        return deleted

    def record_run(self, started_at: str, fetched: int, inserted: int, errors: dict) -> int:
        self.conn.execute(
            "INSERT INTO runs (started_at, finished_at, fetched_total, inserted_new, errors) "
            "VALUES (?,?,?,?,?)",
            (started_at, datetime.now(timezone.utc).isoformat(timespec="seconds"),
             fetched, inserted, json.dumps(errors, ensure_ascii=False)))
        self.conn.commit()
        return self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    def maybe_vacuum(self, run_count: int, every: int) -> None:
        if every and run_count % every == 0:
            log.info("VACUUM")
            self.conn.execute("VACUUM")

    def top_today(self, limit: int, min_score: int) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        today = datetime.now(timezone.utc).date().isoformat()
        rows = self.conn.execute(
            """SELECT * FROM jobs WHERE fetched_at >= ? AND score >= ?
               AND category NOT IN ('skip') ORDER BY score DESC LIMIT ?""",
            (today, min_score, limit)).fetchall()
        self.conn.row_factory = None
        return rows

    def close(self):
        self.conn.commit()
        self.conn.close()
