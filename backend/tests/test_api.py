"""API contract tests (require built artifacts)."""
import pytest

from tatpar.config import ARTIFACTS_DIR

pytestmark = pytest.mark.skipif(not (ARTIFACTS_DIR / "bench" / "summary.json").exists(), reason="artifacts not built")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from tatpar.api.main import app

    with TestClient(app) as c:
        tok = c.post("/api/auth/login", json={"id": "stncdr", "pin": "2601"}).json()["token"]
        c.headers.update({"Authorization": f"Bearer {tok}"})
        yield c


def _login(client, uid, pin):
    r = client.post("/api/auth/login", json={"id": uid, "pin": pin}, headers={"Authorization": ""})
    return r


def test_auth_required_and_roles(client, tmp_path, monkeypatch):
    from tatpar.trust import audit

    monkeypatch.setattr(audit, "LOG", tmp_path / "log.jsonl")
    assert client.get("/api/fleet", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/fleet", headers={"Authorization": "Bearer forged.token"}).status_code == 401
    assert _login(client, "sengo", "0000").status_code == 401
    sengo = {"Authorization": f"Bearer {_login(client, 'sengo', '2602').json()['token']}"}
    plan = {"kind": "readiness_plan", "summary": "test", "persona": "STN CDR"}
    assert client.post("/api/approve", json=plan, headers=sengo).status_code == 403          # only STN CDR
    assert client.post("/api/approve", json={**plan, "kind": "daily_signal"}, headers=sengo).status_code == 200
    e = client.post("/api/approve", json=plan).json()                                          # fixture = STN CDR
    assert e["persona"] == "STN CDR" and e["user"] == "stncdr" and e["sig"]
    auditor = {"Authorization": f"Bearer {_login(client, 'auditor', '2605').json()['token']}"}
    assert client.post("/api/approve", json={**plan, "kind": "daily_signal"}, headers=auditor).status_code == 403
    assert client.get("/api/audit", headers=auditor).json()["verify"]["ok"]


@pytest.mark.parametrize("path", ["/api/health", "/api/auth/roster", "/api/auth/me", "/api/meta", "/api/overview", "/api/fleet", "/api/forecast", "/api/plan",
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


def test_audit_signature_catches_rebuilt_chain(tmp_path, monkeypatch):
    """Re-hashing the whole chain after an edit still fails: the forger lacks the signing key."""
    import hashlib
    import json

    from tatpar.trust import audit

    monkeypatch.setattr(audit, "LOG", tmp_path / "log.jsonl")
    for i in range(3):
        audit.append("test", "STN CDR", f"entry {i}")
    es = audit.read()
    es[1]["summary"] = "entry X"
    prev = audit.GENESIS
    for e in es:
        e["prev"] = prev
        e["hash"] = hashlib.sha256((prev + audit._canon(e)).encode()).hexdigest()
        prev = e["hash"]
    audit.LOG.write_text("".join(json.dumps(e) + "\n" for e in es))
    v = audit.verify()
    assert not v["ok"] and v["reason"] == "signature"


def test_orders_close_the_loop(client, tmp_path, monkeypatch):
    from tatpar.trust import audit, records

    monkeypatch.setattr(audit, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(records, "ORDERS", tmp_path / "orders.jsonl")
    items = [{"type": "phase", "tail": "HF-104", "phase_start": "D+10"},
             {"type": "transfer", "name": "Hydraulic pump", "from": "ED", "to": "jodhpur", "qty": 2}]
    e = client.post("/api/approve", json={"kind": "readiness_plan", "summary": "t", "payload": {"orders": items}}).json()
    assert [o["owner"] for o in e["orders"]] == ["SENGO", "LOG OFFR"]
    oid = e["orders"][1]["id"]
    sengo = {"Authorization": f"Bearer {_login(client, 'sengo', '2602').json()['token']}"}
    assert client.post(f"/api/orders/{oid}", json={"status": "ACTIONED"}, headers=sengo).status_code == 403  # not the owner
    logo = {"Authorization": f"Bearer {_login(client, 'logoffr', '2603').json()['token']}"}
    o = client.post(f"/api/orders/{oid}", json={"status": "ACTIONED", "note": "shipped"}, headers=logo).json()
    assert o["status"] == "ACTIONED" and o["history"][0]["by"] == "LOG OFFR"
    assert client.get("/api/orders").json()["outstanding"] == 1
    assert audit.read()[-1]["kind"] == "order_update" and audit.verify()["ok"]


def test_file_and_import_snags(client, tmp_path, monkeypatch):
    from tatpar.trust import records

    monkeypatch.setattr(records, "FILED", tmp_path / "filed.jsonl")
    r = client.post("/api/snags/file", json={"tail": "HF-101", "text": "hyd pr fluctuating on lh sys during taxi", "lru": "HYD_PUMP"}).json()
    assert r["entry"]["snag_id"] == "TL-0001" and r["entry"]["ata"] == 29 and r["entry"]["filed_by"] == "STN CDR"
    assert client.get("/api/snags/recent").json()[0]["snag_id"] == "TL-0001"
    assert client.get("/api/aircraft/HF-101").json()["snags"][0]["snag_id"] == "TL-0001"
    csv = b"date,tail,text\n2026-10-01,HF-202,RADAR TX FAIL IN A2A MODE\n2026-10-01,ZZ-999,UNKNOWN TAIL\n"
    rep = client.post("/api/snags/import", files={"file": ("x.csv", csv, "text/csv")}).json()
    assert rep["ok"] and rep["filed"] == 1 and rep["warnings"]
    auditor = {"Authorization": f"Bearer {_login(client, 'auditor', '2605').json()['token']}"}
    assert client.post("/api/snags/file", json={"tail": "HF-101", "text": "x"}, headers=auditor).status_code == 403


def test_unknown_squadron_is_a_validation_error(client):
    assert client.post("/api/requirement", json={"sqn": "SQN-Z"}).status_code == 422
    assert client.post("/api/plan/run", json={"sqn": "SQN-Z", "start": 1, "end": 2, "min_capable": 3}).status_code == 422
