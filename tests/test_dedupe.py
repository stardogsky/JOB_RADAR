from src.dedupe import content_hash
from src.models import Job


def make(title="AI Automation Specialist", company="Acme", desc="build workflows"):
    return Job(source="x", source_id=None, title=title, company=company,
               url="https://a", location_raw=None, remote_confidence="yes",
               salary_raw=None, salary_known=False, salary_min_usd_month=None,
               salary_max_usd_month=None, description=desc)


def test_same_content_same_hash_despite_url_and_case():
    a, b = make(), make()
    b.url = "https://b?utm=tracking"
    b.title = "AI AUTOMATION Specialist"
    b.description = "Build   workflows"
    assert content_hash(a) == content_hash(b)


def test_different_company_different_hash():
    assert content_hash(make(company="Acme")) != content_hash(make(company="Bcme"))
