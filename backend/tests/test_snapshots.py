"""Every GET endpoint compared to the JSON saved in tests/snapshots/ (taken before the backend refactor).

Regenerate after an intended change:  python backend/tests/test_snapshots.py
"""

from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

import pytest
from conftest import BRAM, HAS_DATA
from fastapi.testclient import TestClient

SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"

URLS: list[str] = [
    "/openapi.json",
    "/api/health",
    "/api/meta",
    "/api/processes",
    "/api/processes/leave",
    "/api/processes/offboarding",
    "/api/processes/onboarding",
    "/api/processes/recruiting",  # 404
    "/api/cases",
    "/api/cases?process=leave",
    "/api/cases?status=cancelled",
    "/api/cases?flagged=true",
    "/api/cases?flagged=false",
    "/api/cases?q=bram",
    "/api/cases?process=onboarding&status=complete&q=FARADAY",
    f"/api/cases/{BRAM}",
    "/api/cases/leave:bram-montague:2026-03-30_2026-03-30",
    "/api/cases/leave:farah-zielinski:2026-03-18_2026-03-20",
    "/api/cases/onboarding:vida-faraday",
    "/api/cases/onboarding:chiara-ekwueme",
    "/api/cases/onboarding:bram-danforth",
    "/api/cases/nope",  # 404
    "/api/insights",
    "/api/insights?process=onboarding",
    "/api/insights?kind=case_flag",
    "/api/flags",
    "/api/flags?rule=activity_after_last_day",
    "/api/flags?process=leave",
    "/api/people/p_luca-bellweather",
    "/api/people/p_bram-montague",
    "/api/people/p_vida-faraday",
    "/api/people/nope",  # 404
    "/api/events/nope/raw",  # 404
    "/api/feedback",
    "/api/feedback/export",
]
RAW_URLS: list[str] = [  # need the data/ export
    "/api/events/mail:Rl2k4RMKxiWdybd2UWETKyjR@harbourline.example/raw",
    "/api/events/screen:lerato:1279/raw",
    "/api/events/teams_chat:19:6b0d549b-11e2-43d9-a173-6cad8d116ece_2e5f950c-33a7-4eea-a4fd-4e14a0f096da@unq.gbl.spaces:1773118116353/raw",
    "/api/events/calendar:040000008200E00074C5B7101A82E0082C151BD80257B450868D792028BE84A6D36ABC86/raw",
    "/api/events/teams_channel:1773645951734/raw",
]


def snapshot_name(url: str) -> str:
    """File name for a URL: non-alphanumerics become '_', long names are cut and suffixed with a short hash."""
    name = re.sub(r"[^A-Za-z0-9]+", "_", url).strip("_")
    if len(name) > 80:
        name = f"{name[:60]}_{zlib.crc32(url.encode()):08x}"
    return name + ".json"


def capture(client: TestClient, url: str) -> dict:
    """Status, content type and body (JSON when possible) of one GET."""
    r = client.get(url)
    try:
        body = r.json()
    except ValueError:
        body = r.text
    return {"url": url, "status": r.status_code, "content_type": r.headers.get("content-type"), "body": body}


@pytest.mark.parametrize("url", URLS + [pytest.param(u, marks=pytest.mark.skipif(not HAS_DATA, reason="data/ export not present")) for u in RAW_URLS])
def test_matches_snapshot(client: TestClient, url: str) -> None:
    expected = json.loads((SNAPSHOT_DIR / snapshot_name(url)).read_text(encoding="utf-8"))
    assert capture(client, url) == expected


def write_snapshots(client: TestClient) -> None:
    """Overwrite tests/snapshots/ with the current responses."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    for url in URLS + RAW_URLS:
        path = SNAPSHOT_DIR / snapshot_name(url)
        path.write_text(json.dumps(capture(client, url), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import tempfile

    from conftest import make_client

    with make_client(Path(tempfile.mkdtemp())) as c:
        write_snapshots(c)
