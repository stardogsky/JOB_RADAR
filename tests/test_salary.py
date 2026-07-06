import pytest

from src.salary import parse_salary_numbers, parse_salary_text

CASES = [
    ("$20/hr", True, 3200, 3200),
    ("$1500/month", True, 1500, 1500),
    ("€40k/year", True, 3600, 3600),
    ("£35,000 - £45,000 per year", True, 3704, 4763),
    ("$60k - $90k", True, 5000, 7500),
    ("$90,000 USD or more", True, 7500, None),
    ("Competitive salary", False, None, None),
    ("", False, None, None),
    (None, False, None, None),
    ("200000-225000 PLN/year", False, None, None),
    ("$15-20/hour", True, 2400, 3200),
]


@pytest.mark.parametrize("text,known,lo,hi", CASES)
def test_parse_salary_text(text, known, lo, hi, cfg):
    got_known, got_lo, got_hi = parse_salary_text(text, cfg)
    assert got_known is known
    if lo is None:
        assert got_lo is None
    else:
        assert got_lo == pytest.approx(lo, abs=1)
    if hi is None:
        assert got_hi is None
    else:
        assert got_hi == pytest.approx(hi, abs=1)


def test_remoteok_numbers_zero(cfg):
    assert parse_salary_numbers(0, 0, cfg) == (False, None, None)


def test_remoteok_numbers_yearly(cfg):
    known, lo, hi = parse_salary_numbers(60000, 90000, cfg)
    assert known and lo == 5000 and hi == 7500
