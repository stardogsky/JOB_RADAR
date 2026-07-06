from src.filters import apply_hard_filters
from src.models import Job
from src.scoring import categorize, score_job


def make(**kw):
    base = dict(source="x", source_id=None, title="AI Automation Specialist",
                company="Acme", url="https://a", location_raw="Worldwide",
                remote_confidence="yes", salary_raw="$2000-3500/month",
                salary_known=True, salary_min_usd_month=2000.0,
                salary_max_usd_month=3500.0,
                description="Build automation workflows with Zapier, Make.com, n8n, "
                            "OpenAI API, webhooks and CRM integrations.")
    base.update(kw)
    return Job(**base)


def test_ideal_job_apply_first(cfg):
    j = score_job(make(), cosine=0.6, cfg=cfg)
    assert j.score >= 80
    assert j.category == "apply_first"
    assert any("title" in r for r in j.reasons)


def test_senior_backend_scores_low(cfg):
    j = make(title="Senior Staff Software Engineer",
             description="7+ years production experience, kubernetes, "
                         "machine learning engineer background required.")
    j = score_job(j, cosine=0.2, cfg=cfg)
    assert j.score < 50
    assert any("seniority" in r for r in j.risks)
    assert any("negative keyword" in r for r in j.risks)


def test_skip_stays_skip(cfg):
    j = apply_hard_filters(make(remote_confidence="no"), cfg)
    j = score_job(j, cosine=0.9, cfg=cfg)
    assert j.category == "skip" and j.score == 0


def test_unknown_salary_adds_risk(cfg):
    j = make(salary_known=False, salary_min_usd_month=None, salary_max_usd_month=None)
    j = score_job(j, cosine=0.5, cfg=cfg)
    assert "salary unknown" in j.risks


def test_score_clamped(cfg):
    j = score_job(make(), cosine=1.0, cfg=cfg)
    assert 0 <= j.score <= 100


def test_categorize_boundaries():
    assert categorize(80) == "apply_first"
    assert categorize(79) == "good"
    assert categorize(65) == "good"
    assert categorize(64) == "maybe"
    assert categorize(50) == "maybe"
    assert categorize(49) == "weak"
    assert categorize(35) == "weak"
    assert categorize(34) == "skip"
