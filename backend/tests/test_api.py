"""API contract tests (require built artifacts)."""
import pytest

from tatpar.config import ARTIFACTS_DIR

pytestmark = pytest.mark.skipif(not (ARTIFACTS_DIR / "bench" / "summary.json").exists(), reason="artifacts not built")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from tatpar.api.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path", ["/api/health", "/api/meta", "/api/overview", "/api/fleet", "/api/forecast", "/api/plan",
                                  "/api/sustainment", "/api/levers", "/api/waterfall", "/api/requirement/demo",
                                  "/api/snags/recent", "/api/snags/stats", "/api/data/sources", "/api/models", "/api/audit"])
def test_get_endpoints(client, path):
    r = client.get(path)
    assert r.status_code == 200, r.text[:300]


def test_aircraft_detail(client):
    r = client.get("/api/aircraft/HF-101")
    assert r.status_code == 200
    d = r.json()
    assert d["engines"] and 0 <= d["engines"][0]["rul_cycles"]["lo"] <= d["engines"][0]["rul_cycles"]["med"] <= d["engines"][0]["rul_cycles"]["hi"]
    assert client.get("/api/aircraft/XX-999").status_code == 404


def test_snag_analysis_hinglish(client):
    r = client.post("/api/snags/analyse", json={"text": "HYD PRESSURE LH SYSTEM MEIN FLUCTUATION, TAXI KE DAURAN", "tail": "HF-101", "lru": "HYD_PUMP"})
    d = r.json()
    assert d["ata"][0]["ata"] == 29
    assert 0 <= d["nff"]["p_nff"] <= 1


def test_copilot_routes(client):
    for q, tool in [("How many aircraft will Sqn A have in 2 weeks?", "forecast"), ("status of HF-114", "aircraft"),
                    ("which spares should we move", "transfers"), ("why is readiness low", "waterfall")]:
        assert client.post("/api/copilot", json={"question": q}).json()["tool"] == tool


def test_audit_chain(client, tmp_path, monkeypatch):
    from tatpar.trust import audit

    monkeypatch.setattr(audit, "LOG", tmp_path / "log.jsonl")
    for i in range(3):
        audit.append("test", "Analyst", f"entry {i}")
    assert audit.verify()["ok"]
    lines = audit.LOG.read_text().splitlines()
    lines[1] = lines[1].replace("entry 1", "entry X")
    audit.LOG.write_text("\n".join(lines) + "\n")
    assert audit.verify() == {"ok": False, "entries": 3, "broken_at": 2}
