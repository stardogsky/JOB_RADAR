"""End-to-end on fixtures: normalize -> dedupe -> filter -> score -> db, no network."""
import json

from src.db import DB
from src.dedupe import content_hash
from src.filters import apply_hard_filters
from src.normalize import normalize_remoteok, normalize_remotive, normalize_wwr
from src.scoring import score_job


def test_full_pipeline_on_fixtures(tmp_path, cfg, remoteok_fixture, remotive_fixture, wwr_fixture):
    jobs = (normalize_remoteok(remoteok_fixture, cfg)
            + normalize_remotive(remotive_fixture, cfg)
            + normalize_wwr(wwr_fixture, cfg))
    assert len(jobs) == 5

    db = DB(str(tmp_path / "jobs.sqlite"))
    seen = db.existing_hashes()
    fresh = []
    for j in jobs:
        j.content_hash = content_hash(j)
        if j.content_hash not in seen:
            seen.add(j.content_hash)
            fresh.append(j)

    for j in fresh:
        apply_hard_filters(j, cfg)
    for j in fresh:
        if j.category != "skip":
            score_job(j, cosine=0.45, cfg=cfg)
        else:
            j.score = 0

    inserted = sum(db.insert_job(j) for j in fresh)
    assert inserted == len(fresh)

    # idempotency: second insert of the same jobs adds nothing
    assert sum(db.insert_job(j) for j in fresh) == 0

    # Home Depot onsite retail must be skip; Remotive example must be top
    rows = {r[0]: r[1] for r in db.conn.execute("SELECT title, category FROM jobs")}
    assert rows["Special Services Associate AIRDRIE"] == "skip"
    assert rows["AI Automation Specialist"] in ("apply_first", "good")

    db.record_run("2026-07-04T06:00:00", len(jobs), inserted, {})
    db.retention(cfg)
    db.close()
