"""Offline end-to-end smoke: runs the real main.run() with collectors fed from
fixtures and embeddings disabled. No network needed.
Run: python scripts/smoke_local.py"""
import json
import os
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["JOB_RADAR_NO_EMBED"] = "1"

from src import main  # noqa: E402

remotive_data = json.loads((ROOT / "fixtures" / "remotive_schema.json").read_text(encoding="utf-8"))
remoteok_data = json.loads((ROOT / "fixtures" / "remoteok_sample.json").read_text(encoding="utf-8"))
wwr_xml = (ROOT / "fixtures" / "wwr_item_sample.xml").read_text(encoding="utf-8")

with mock.patch.object(main.remotive, "fetch", return_value=[remotive_data]), \
     mock.patch.object(main.remoteok, "fetch", return_value=remoteok_data), \
     mock.patch.object(main.wwr, "fetch", return_value=[wwr_xml]):
    code = main.run()

print(f"\nsmoke exit code: {code}")
sys.exit(code)
