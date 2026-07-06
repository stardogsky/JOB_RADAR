from src.normalize import normalize_remoteok


def test_legal_notice_skipped(remoteok_fixture, cfg):
    jobs = normalize_remoteok(remoteok_fixture, cfg)
    assert len(jobs) == 3  # 4 items, first is legal notice


def test_home_depot_not_remote(remoteok_fixture, cfg):
    jobs = normalize_remoteok(remoteok_fixture, cfg)
    hd = next(j for j in jobs if "Home Depot" in (j.company or ""))
    assert hd.remote_confidence == "no"
    assert hd.title == "Special Services Associate AIRDRIE"
    assert hd.salary_known is False


def test_mojibake_fixed_and_antispam_stripped(remoteok_fixture, cfg):
    jobs = normalize_remoteok(remoteok_fixture, cfg)
    hd = next(j for j in jobs if "Home Depot" in (j.company or ""))
    assert "you\u2019re" in hd.description.lower() or "you're" in hd.description.lower()
    assert "please mention the word" not in hd.description.lower()
    assert "â€" not in hd.description


def test_pln_salary_marked_unknown(remoteok_fixture, cfg):
    jobs = normalize_remoteok(remoteok_fixture, cfg)
    tellent = next(j for j in jobs if j.company == "Tellent")
    assert tellent.salary_known is False
    assert tellent.salary_min_usd_month is None


def test_empty_location_probably(remoteok_fixture, cfg):
    jobs = normalize_remoteok(remoteok_fixture, cfg)
    tellent = next(j for j in jobs if j.company == "Tellent")
    assert tellent.remote_confidence == "probably"
