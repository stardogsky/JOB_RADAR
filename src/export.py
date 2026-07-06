import csv
import json
from pathlib import Path


COLUMNS = ["score", "category", "title", "company", "salary_min_usd_month",
           "salary_max_usd_month", "salary_known", "location_raw", "source",
           "date_posted", "url", "reasons", "risks", "status"]


def export_csv(rows, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for r in rows:
            writer.writerow([
                r["score"], r["category"], r["title"], r["company"],
                r["salary_min_usd_month"], r["salary_max_usd_month"],
                bool(r["salary_known"]), r["location_raw"], r["source"],
                r["date_posted"], r["url"],
                "; ".join(json.loads(r["reasons"] or "[]")),
                "; ".join(json.loads(r["risks"] or "[]")),
                r["status"],
            ])
