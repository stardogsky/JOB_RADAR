from src.normalize import normalize_remotive


def test_basic_mapping(remotive_fixture, cfg):
    jobs = normalize_remotive(remotive_fixture, cfg)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "AI Automation Specialist"
    assert j.company == "Example Inc"
    assert j.remote_confidence == "yes"
    assert j.location_raw == "Worldwide"
    assert j.salary_known is True
    assert j.salary_min_usd_month == 2000
    assert j.salary_max_usd_month == 3500
    assert j.date_posted == "2026-07-01"
    assert "<p>" not in j.description
