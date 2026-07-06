import json
import logging

import requests

log = logging.getLogger("notify")

API = "https://api.telegram.org/bot{token}/sendMessage"
CHUNK = 3800


def _fmt_salary(row) -> str:
    if not row["salary_known"]:
        return "salary n/a"
    lo, hi = row["salary_min_usd_month"], row["salary_max_usd_month"]
    if hi and hi != lo:
        return f"${lo:.0f}-{hi:.0f}/mo"
    return f"${lo:.0f}+/mo" if hi is None else f"${lo:.0f}/mo"


def build_digest(rows, stats: dict, errors: dict, cfg: dict) -> str:
    lines = [f"<b>Job Radar - {stats['date']}</b>",
             f"Собрано: {stats['fetched']} | новых: {stats['inserted']} | "
             f"apply_first: {stats['apply_first']} | good: {stats['good']}", ""]
    if not rows:
        lines.append("Сегодня нет вакансий выше порога.")
    for i, r in enumerate(rows, 1):
        reasons = "; ".join(json.loads(r["reasons"] or "[]")[:3])
        risks = "; ".join(json.loads(r["risks"] or "[]")[:2])
        lines.append(f"{i}. [{r['score']}] <b>{r['title']}</b> - {r['company'] or '?'} ({r['source']})")
        lines.append(f"   {_fmt_salary(r)} | {r['location_raw'] or 'location n/a'}")
        if reasons:
            lines.append(f"   + {reasons}")
        if risks:
            lines.append(f"   - {risks}")
        lines.append(f"   {r['url']}")
        lines.append("")
    if errors:
        lines.append("Source errors: " + "; ".join(f"{k}: {v}" for k, v in errors.items()))
    return "\n".join(lines)


def send_telegram(text: str, cfg: dict) -> bool:
    token, chat_id = cfg["telegram_bot_token"], cfg["telegram_chat_id"]
    if not token or not chat_id:
        log.warning("telegram credentials missing, digest printed to stdout only")
        print(text)
        return False
    ok = True
    for i in range(0, len(text), CHUNK):
        try:
            resp = requests.post(API.format(token=token), json={
                "chat_id": chat_id, "text": text[i:i + CHUNK],
                "parse_mode": "HTML", "disable_web_page_preview": True,
            }, timeout=(10, 30))
            if resp.status_code != 200:
                log.error("telegram error %s: %s", resp.status_code, resp.text[:200])
                ok = False
        except requests.RequestException as exc:
            log.error("telegram send failed: %s", exc)
            ok = False
    return ok
