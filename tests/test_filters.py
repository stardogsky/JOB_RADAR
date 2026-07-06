from src.filters import apply_hard_filters
from src.models import Job


def make(**kw):
    base = dict(source="x", source_id=None, title="AI Automation Specialist",
                company="Acme", url="https://a", location_raw="Worldwide",
                remote_confidence="yes", salary_raw=None, salary_known=False,
                salary_min_usd_month=None, salary_max_usd_month=None,
                description="build workflows with zapier and openai")
    base.update(kw)
    return Job(**base)


def test_not_remote_skipped(cfg):
    j = apply_hard_filters(make(remote_confidence="no"), cfg)
    assert j.category == "skip"


def test_low_salary_skipped(cfg):
    j = apply_hard_filters(make(salary_known=True, salary_min_usd_month=800,
                                salary_max_usd_month=1000), cfg)
    assert j.category == "skip"


def test_unknown_salary_not_skipped(cfg):
    j = apply_hard_filters(make(salary_known=False), cfg)
    assert j.category is None


def test_us_only_skipped(cfg):
    j = apply_hard_filters(make(description="Must have US work authorization"), cfg)
    assert j.category == "skip"


def test_irrelevant_title_skipped(cfg):
    j = apply_hard_filters(make(title="Registered Nurse"), cfg)
    assert j.category == "skip"


def test_good_job_passes(cfg):
    j = apply_hard_filters(make(), cfg)
    assert j.category is None
