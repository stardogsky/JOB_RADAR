"""Salary parsing: free text or yearly numbers -> (known, min_usd_month, max_usd_month)."""
import re

NON_USD_UNSUPPORTED = (
    "pln", "inr", "brl", "chf", "sek", "nok", "dkk", "jpy", "cny", "zar",
    "mxn", "ars", "uah", "rub", "czk", "huf", "ron", "try", "cad", "aud",
    "zł", "₹", "¥", "₽",
)

NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(k)?", re.IGNORECASE)


def _detect_currency(text: str) -> str | None:
    """Return 'USD'|'EUR'|'GBP', 'UNSUPPORTED', or None if no currency marker at all."""
    low = text.lower()
    for token in NON_USD_UNSUPPORTED:
        if re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", low):
            return "UNSUPPORTED"
    if "€" in text or re.search(r"\beur\b", low):
        return "EUR"
    if "£" in text or re.search(r"\bgbp\b", low):
        return "GBP"
    if "$" in text or re.search(r"\busd\b", low):
        return "USD"
    return None


def _detect_period(text: str, min_value: float) -> str:
    low = text.lower()
    if re.search(r"(/|per\s*)h(ou)?r|hourly", low):
        return "hour"
    if re.search(r"(/|per\s*)mo(nth)?\b|monthly", low):
        return "month"
    if re.search(r"(/|per\s*)y(ea)?r\b|annual|annum|\bp\.?a\.?\b|yearly", low):
        return "year"
    if min_value < 200:
        return "hour"
    if min_value < 10_000:
        return "month"
    return "year"


def _to_monthly(value: float, period: str, rate: float, hours_per_month: int) -> float:
    value_usd = value * rate
    if period == "hour":
        return value_usd * hours_per_month
    if period == "month":
        return value_usd
    return value_usd / 12.0


def parse_salary_text(text: str | None, cfg: dict) -> tuple[bool, float | None, float | None]:
    if not text or not text.strip():
        return False, None, None
    currency = _detect_currency(text)
    if currency == "UNSUPPORTED":
        return False, None, None

    numbers: list[float] = []
    for m in NUM_RE.finditer(text.replace(",", "")):
        value = float(m.group(1))
        if m.group(2):
            value *= 1000
        numbers.append(value)
    numbers = [n for n in numbers if n >= 5]  # drop noise like "401(k) -> 401" handled below
    if not numbers:
        return False, None, None
    # Ignore obvious non-salary numbers such as 401 (401k plans)
    numbers = [n for n in numbers if n != 401 and n != 401000]
    if not numbers:
        return False, None, None

    rates = cfg["currency_rates_to_usd"]
    rate = rates.get(currency or "USD", 1.0)
    if currency is None:
        # No currency marker at all: too risky to treat text as salary
        return False, None, None

    hours = cfg["hours_per_month"]
    smin = numbers[0]
    smax = numbers[1] if len(numbers) > 1 else numbers[0]
    open_ended = bool(re.search(r"or more|and up|\+\s*$|\bplus\b\s*$", text.lower()))
    period = _detect_period(text, smin)
    min_month = _to_monthly(smin, period, rate, hours)
    max_month = None if (open_ended and len(numbers) == 1) else _to_monthly(smax, period, rate, hours)
    if max_month is not None and max_month < min_month:
        min_month, max_month = max_month, min_month
    return True, round(min_month, 2), (round(max_month, 2) if max_month is not None else None)


def parse_salary_numbers(smin: float, smax: float, cfg: dict) -> tuple[bool, float | None, float | None]:
    """RemoteOK numeric fields: yearly USD, 0 means unknown."""
    if not smin and not smax:
        return False, None, None
    lo = smin or smax
    hi = smax or smin
    return True, round(lo / 12.0, 2), round(hi / 12.0, 2)
