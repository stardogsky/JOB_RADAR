from src.normalize import normalize_wwr


def test_company_title_split_and_region(wwr_fixture, cfg):
    jobs = normalize_wwr(wwr_fixture, cfg)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.company == "Example Corp"
    assert j.title == "Automation Engineer"
    assert j.location_raw == "Anywhere in the World"
    assert j.remote_confidence == "yes"
    assert j.date_posted == "2026-07-02"
    assert j.url.startswith("https://weworkremotely.com/")


def test_broken_xml_returns_empty(cfg):
    assert normalize_wwr("<rss><channel><item>", cfg) == []
