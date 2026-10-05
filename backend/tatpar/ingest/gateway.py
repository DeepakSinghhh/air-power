"""Simulated edge HUMS gateway: replays an engine's post-flight downloads into a running TATPAR.

An aircraft's health-monitoring recorder is downloaded after each flight; at a forward base an edge
gateway forwards the download to the station's TATPAR server. This script plays that role over the
same authenticated HTTP API a real gateway would use (MQTT/Kafka transport is the production path).
It replays a run-to-failure NASA C-MAPSS engine the models never trained on, a few cycles per
"flight", and prints the calibrated interval TATPAR returns next to the hidden true remaining life.

    python -m tatpar.ingest.gateway                      # demo engine, 5 cycles per flight, every 3 s
    python -m tatpar.ingest.gateway --tail HF-107 --engine 1 --per-flight 10 --every 2
"""
from __future__ import annotations

import argparse
import io
import json
import time
import urllib.request
import uuid

import pandas as pd

from ..config import FH_PER_CYCLE
from .samples import DEMO_CUT, demo_unit, hums_rows


def _request(url: str, data: bytes | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"text": body.decode()}


def login(base: str, uid: str, pin: str) -> str:
    return _request(f"{base}/api/auth/login", json.dumps({"id": uid, "pin": pin}).encode(),
                    {"Content-Type": "application/json"})["token"]


def upload(base: str, token: str, df: pd.DataFrame, name: str, replace: bool = False) -> dict:
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: text/csv\r\n\r\n").encode() + df.to_csv(index=False).encode() + f"\r\n--{boundary}--\r\n".encode()
    return _request(f"{base}/api/ingest/hums{'?replace=true' if replace else ''}", body,
                    {"Content-Type": f"multipart/form-data; boundary={boundary}", "Authorization": f"Bearer {token}"})


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="sengo")
    ap.add_argument("--pin", default="2602")
    ap.add_argument("--tail")
    ap.add_argument("--engine", type=int, default=1)
    ap.add_argument("--per-flight", type=int, default=5, help="engine cycles in each post-flight download")
    ap.add_argument("--every", type=float, default=3.0, help="seconds between downloads")
    ap.add_argument("--stop-before-end", type=int, default=3, help="stop this many cycles before the engine's end of life")
    a = ap.parse_args(argv)

    token = login(a.url, a.user, a.pin)
    if not a.tail:   # the server's HUMS sample names the demo engine
        req = urllib.request.Request(f"{a.url}/api/ingest/template/hums?sample=true", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            first = pd.read_csv(io.BytesIO(r.read()), nrows=1).iloc[0]
        a.tail, a.engine = str(first["tail"]), int(first["engine"])
    uid, traj = demo_unit()
    life = int(traj["cycle"].max())
    today = pd.Timestamp.today().date()
    print(f"HUMS gateway → {a.url} as {a.user}: {a.tail} engine {a.engine} replaying {uid} ({life} cycles, unseen by the models)")
    k = life - DEMO_CUT
    first = True
    while True:
        lo_c = 1 if first else k - a.per_flight + 1
        rows = hums_rows(a.tail, a.engine, traj[(traj["cycle"] >= lo_c) & (traj["cycle"] <= k)], today)
        res = upload(a.url, token, rows, f"hums_{a.tail}_E{a.engine}_c{k}.csv", replace=first)
        eng = (res.get("result") or {}).get("engines") or []
        if not eng:
            print("  rejected:", res.get("report", {}).get("errors") or res.get("report", {}).get("row_errors") or res)
            return
        e = eng[0]["after_fh"]
        truth = (life - k) * FH_PER_CYCLE
        print(f"  cycle {k:>3}: RUL {e['med']:5.0f} FH (90 % {e['lo']:4.0f}–{e['hi']:4.0f})"
              f"{'  ALERT' if eng[0]['alert'] else '       '}   hidden truth {truth:4.0f} FH")
        first = False
        if k >= life - a.stop_before_end:
            return
        k = min(life - a.stop_before_end, k + a.per_flight)
        time.sleep(a.every)


if __name__ == "__main__":
    main()
