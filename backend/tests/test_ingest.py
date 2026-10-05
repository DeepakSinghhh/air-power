"""Data fabric: contracts, validation, and what each import changes (require built artifacts)."""
import pytest

from tatpar.config import ARTIFACTS_DIR, REPO_DIR

pytestmark = pytest.mark.skipif(not (ARTIFACTS_DIR / "bench" / "summary.json").exists(), reason="artifacts not built")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A signed-in client whose imports, ledger and tech log live in a temp dir; the live state is reloaded after."""
    from fastapi.testclient import TestClient

    from tatpar.api import context
    from tatpar.api.main import app
    from tatpar.ingest import store
    from tatpar.trust import audit, records

    monkeypatch.setattr(store, "DIR", tmp_path / "ingest")
    monkeypatch.setattr(audit, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(records, "FILED", tmp_path / "filed.jsonl")
    context.reload()
    with TestClient(app) as c:
        def hdr(uid, pin):
            return {"Authorization": f"Bearer {c.post('/api/auth/login', json={'id': uid, 'pin': pin}).json()['token']}"}
        c.headers.update(hdr("stncdr", "2601"))
        yield c, hdr, context.get_ctx()
    context.reload()


def _csv(df) -> bytes:
    return df.to_csv(index=False).encode()


def _post(c, source, df, headers=None, **params):
    return c.post(f"/api/ingest/{source}", files={"file": (f"{source}.csv", _csv(df), "text/csv")},
                  params=params, headers=headers or {})


def test_contracts_doc_is_in_sync():
    from tatpar.ingest.contracts import markdown

    assert (REPO_DIR / "docs" / "05-data-contracts.md").read_text() == markdown(), "run: python -m tatpar.ingest docs"


def test_every_sample_passes_its_contract(env):
    from tatpar.ingest.contracts import CONTRACTS, Register, validate
    from tatpar.ingest.samples import sample

    c, _, ctx = env
    for src in CONTRACTS:
        df = sample(ctx, src)
        rep, acc = validate(src, df.astype(str), Register.from_state(ctx.state))
        assert rep["ok"] and rep["rejected"] == 0 and len(acc) == len(df), (src, rep["row_errors"][:3])
        assert c.get(f"/api/ingest/template/{src}?sample=true").text.splitlines()[0].split(",") == list(df.columns)


def test_bad_rows_are_rejected_with_reasons(env):
    from tatpar.ingest.samples import sample

    c, _, ctx = env
    h = sample(ctx, "hums").head(8).astype(object)
    h.loc[0, "T30"] = "hot"                    # not a number
    h.loc[1, "Ps30"] = 900                     # out of range
    h.loc[2, "tail"] = "HF-999"                # not in the register
    h.loc[3, "cycle"] = h.loc[4, "cycle"]      # duplicate key
    rep = c.post("/api/ingest/hums/validate", files={"file": ("h.csv", _csv(h), "text/csv")}).json()["report"]
    reasons = {e["line"]: " ".join(e["reasons"]) for e in rep["row_errors"]}
    assert rep["accepted"] == 4 and rep["rejected"] == 4
    assert "not a number" in reasons[2] and "outside" in reasons[3] and "fleet register" in reasons[4] and "duplicate" in reasons[5]
    r = sample(ctx, "repairs").head(1).copy()
    st = ctx.state
    r.loc[0, "serial"] = int(st.pos_serial[st.pos_serial >= 0][0])     # an installed unit is not at a repair agency
    rep = c.post("/api/ingest/repairs/validate", files={"file": ("r.csv", _csv(r), "text/csv")}).json()["report"]
    assert not rep["ok"] and "not at a repair agency" in rep["row_errors"][0]["reasons"][-1]
    rep = c.post("/api/ingest/stock/validate", files={"file": ("s.csv", b"stock_point,lru\nED,INS\n", "text/csv")}).json()["report"]
    assert not rep["ok"] and "qty" in rep["errors"][0]


def test_hums_download_updates_every_consumer(env):
    from tatpar.ingest.samples import sample

    c, hdr, ctx = env
    df = sample(ctx, "hums")
    tail = df["tail"].iloc[0]
    before = c.get(f"/api/aircraft/{tail}").json()["engines"][0]
    risk_before = ctx.risk30.copy()
    out = _post(c, "hums", df, hdr("sengo", "2602")).json()
    assert out["applied"] and out["result"]["engines"], out
    e = out["result"]["engines"][0]
    ser = e["serial"]
    lo, med, hi = ctx.belief.engine_quantiles(ctx.state, ser)          # the one hook every consumer reads
    assert round(med * 3, 1) == pytest.approx(e["after_fh"]["med"], abs=0.2)
    assert e["after_fh"]["med"] < before["rul_fh"]["med"]              # the download shows a worn engine
    after = c.get(f"/api/aircraft/{tail}").json()["engines"][0]
    assert after["uploaded"] and after["hums_source"].startswith("DOWNLOAD") and after["cycle"] == e["last_cycle"]
    assert (ctx.risk30 != risk_before).any()                            # risk recomputed from the new interval
    src = {s["key"]: s for s in c.get("/api/data/sources").json()["sources"]}
    assert src["hums"]["last_import"]["sha256"] and src["hums"]["freshness_days"] == 0
    from tatpar.trust import audit
    assert audit.read()[-1]["kind"] == "data_import" and audit.verify()["ok"]
    assert c.get("/api/ingest/stamp").json()["seq"] == 1


def test_logistics_imports_change_the_state(env):
    from tatpar.ingest.samples import sample
    from tatpar.twin.state import LRU_IDS, SP_IDX

    c, hdr, ctx = env
    stock = sample(ctx, "stock")
    assert _post(c, "stock", stock, hdr("logoffr", "2603")).json()["applied"]
    for _, r in stock.iterrows():
        assert len(ctx.state.stock[(SP_IDX[r["stock_point"]], LRU_IDS.index(r["lru"]))]) == r["qty"]
    rep = sample(ctx, "repairs")
    out = _post(c, "repairs", rep, hdr("depotmgr", "2604")).json()
    assert out["applied"] and len(out["result"]["rows"]) == len(rep)
    from tatpar.ingest.apply import date_to_day
    ret = {int(s): d for d, s, _ in ctx.state.pipeline}
    for _, r in rep.iterrows():
        assert ret[int(r["serial"])] == date_to_day(r["expected_return"])


def test_import_permissions_follow_the_source(env):
    from tatpar.ingest.samples import sample

    c, hdr, ctx = env
    assert _post(c, "hums", sample(ctx, "hums"), hdr("auditor", "2605")).status_code == 403
    assert _post(c, "hums", sample(ctx, "hums"), hdr("logoffr", "2603")).status_code == 403
    assert _post(c, "stock", sample(ctx, "stock"), hdr("sengo", "2602")).status_code == 403
    assert _post(c, "sorties", sample(ctx, "sorties")).status_code == 422          # validate-only source
    assert c.post("/api/ingest/reset", headers=hdr("sengo", "2602")).status_code == 403


def test_imports_survive_a_restart_and_reset_clears_them(env):
    from tatpar.api import context
    from tatpar.ingest.samples import sample
    from tatpar.twin.state import LRU_IDS, SP_IDX

    c, hdr, ctx = env
    stock = sample(ctx, "stock").head(1)
    _post(c, "stock", stock)
    out = _post(c, "hums", sample(ctx, "hums")).json()
    ser = out["result"]["engines"][0]["serial"]
    key = (SP_IDX[stock["stock_point"].iloc[0]], LRU_IDS.index(stock["lru"].iloc[0]))
    context.reload()
    ctx2 = context.get_ctx()
    assert len(ctx2.state.stock[key]) == stock["qty"].iloc[0] and ser in ctx2.belief.hums_overrides
    r = c.post("/api/ingest/reset").json()
    assert r["imports_removed"] == 2
    ctx3 = context.get_ctx()
    assert ser not in ctx3.belief.hums_overrides and c.get("/api/ingest/lineage").json() == []
