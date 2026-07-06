"""Snapshot live source responses into fixtures/ for parser development and tests.
Run locally: python scripts/capture_fixtures.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.collectors.base import http_get  # noqa: E402
from src.config import load_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"


def main() -> None:
    cfg = load_config()
    FIX.mkdir(exist_ok=True)

    url = cfg["sources"]["remotive"]["urls"][0] + "&limit=5"
    data = http_get(url).json()
    (FIX / "remotive_live.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"remotive: {len(data.get('jobs', []))} jobs -> fixtures/remotive_live.json")

    items = http_get(cfg["sources"]["remoteok"]["url"]).json()
    (FIX / "remoteok_live.json").write_text(
        json.dumps(items[:11], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"remoteok: {len(items)} items (saved 11) -> fixtures/remoteok_live.json")

    for feed_url in cfg["sources"]["wwr"]["feeds"]:
        name = feed_url.rstrip("/").split("/")[-1].replace(".rss", "")
        text = http_get(feed_url, accept="application/rss+xml").text
        (FIX / f"wwr_live_{name}.xml").write_text(text, encoding="utf-8")
        print(f"wwr: {name} -> fixtures/wwr_live_{name}.xml ({len(text)} chars)")


if __name__ == "__main__":
    main()
