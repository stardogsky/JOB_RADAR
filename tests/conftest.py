import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def cfg():
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        c = yaml.safe_load(fh)
    c["root"] = str(ROOT)
    return c


@pytest.fixture(scope="session")
def remoteok_fixture():
    with open(ROOT / "fixtures" / "remoteok_sample.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def remotive_fixture():
    with open(ROOT / "fixtures" / "remotive_schema.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def wwr_fixture():
    return (ROOT / "fixtures" / "wwr_item_sample.xml").read_text(encoding="utf-8")
