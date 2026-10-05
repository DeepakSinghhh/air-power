"""Data contracts for the four maintenance data sources named in PS 26249, plus flying records.

Each contract says what a unit's export must contain: field, type, unit, allowed range or values,
whether it is required, and which fields identify a record. ``validate`` checks an uploaded CSV
against its contract and the fleet register (known tails, serials, stock points), row by row, and
returns the accepted rows with a reason for every rejected one. Nothing is stored here; see
``tatpar.ingest.apply`` for what an accepted import changes.

The layouts are prototype formats aligned to S5000F / OSA-CBM concepts. A unit deployment would
map its actual e-MMS, IMMOLS and HUMS-ground-station exports onto them (a column mapping, not code).
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..domain.catalog import AIRCRAFT_TYPES, LRU_TYPES, MISSIONS, STOCK_POINTS
from ..prognostics.engine_rul import USE_SENSORS

MAX_ROWS = 20_000


@dataclass(frozen=True)
class Field:
    name: str
    type: str                      # str | int | float | date | enum
    unit: str = ""
    required: bool = True
    lo: float | None = None
    hi: float | None = None
    values: tuple = ()             # allowed values for enum
    ref: str = ""                  # register the value must exist in: tail | lru | stock_point | serial
    doc: str = ""


@dataclass(frozen=True)
class Contract:
    source: str
    title: str
    system: str                    # the unit system that would produce the export
    entity: str                    # common-data-model entity
    s5000f: str
    osa_cbm: str
    fields: tuple[Field, ...]
    key: tuple[str, ...] = ()      # fields that identify a record (duplicates rejected)
    applies: str = ""              # what an import changes in TATPAR
    validate_only: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def columns(self) -> list[str]:
        return [f.name for f in self.fields]


# C-MAPSS sensor channels (Saxena et al. 2008): unit, plausible range (training range ±15 %)
_SENSOR = {
    "T2": ("°R", "Total temperature at fan inlet", 445.0, 518.7), "T24": ("°R", "Total temperature at LPC outlet", 535.5, 645.1),
    "T30": ("°R", "Total temperature at HPC outlet", 1242.7, 1616.9), "T50": ("°R", "Total temperature at LPT outlet", 1023.8, 1441.5),
    "P2": ("psia", "Pressure at fan inlet", 3.9, 14.6), "P15": ("psia", "Total pressure in bypass duct", 5.7, 21.6),
    "P30": ("psia", "Total pressure at HPC outlet", 136.2, 570.8), "Nf": ("rpm", "Physical fan speed", 1914.7, 2388.6),
    "Nc": ("rpm", "Physical core speed", 7984.5, 9244.6), "epr": ("—", "Engine pressure ratio (P50/P2)", 0.93, 1.32),
    "Ps30": ("psia", "Static pressure at HPC outlet", 36.0, 48.5), "phi": ("pps/psi", "Ratio of fuel flow to Ps30", 128.3, 537.5),
    "NRf": ("rpm", "Corrected fan speed", 2027.6, 2390.5), "NRc": ("rpm", "Corrected core speed", 7845.8, 8293.7),
    "BPR": ("—", "Bypass ratio", 8.16, 11.07), "farB": ("—", "Burner fuel-air ratio", 0.02, 0.03),
    "htBleed": ("—", "Bleed enthalpy", 302, 400), "Nf_dmd": ("rpm", "Demanded fan speed", 1915, 2388),
    "PCNfR_dmd": ("%", "Demanded corrected fan speed", 84.9, 100.0), "W31": ("lbm/s", "HPT coolant bleed", 10.2, 39.9),
    "W32": ("lbm/s", "LPT coolant bleed", 6.0, 24.0),
}


def _sensor(name: str) -> Field:
    unit, doc, lo, hi = _SENSOR[name]
    pad = 0.15 * (hi - lo)
    return Field(name, "float", unit, name in USE_SENSORS, round(lo - pad, 3), round(hi + pad, 3),
                 doc=doc + ("" if name in USE_SENSORS else " (optional: not used by the RUL model)"))


MAX_ENGINES = max(t.engines for t in AIRCRAFT_TYPES.values())

CONTRACTS: dict[str, Contract] = {c.source: c for c in [
    Contract(
        "hums", "HUMS / ACMS engine download", "Ground station export of the engine health-monitoring recorder, one row per engine cycle",
        "EngineHealthSnapshot", "Health monitoring data", "DA → DM",
        (Field("tail", "str", ref="tail", doc="Aircraft tail number, e.g. HF-107"),
         Field("engine", "int", "", True, 1, MAX_ENGINES, doc="Engine position on the aircraft (1 = left / single)"),
         Field("cycle", "int", "cycles", True, 1, 2000, doc="Engine cycle number since the module was fitted"),
         Field("date", "date", required=False, doc="Flight date of the cycle"),
         Field("setting1", "float", "kft", True, -1, 45, doc="Altitude"),
         Field("setting2", "float", "Mach", True, -0.05, 0.9, doc="Mach number"),
         Field("setting3", "float", "deg", True, 50, 105, doc="Throttle resolver angle"),
         *[_sensor(s) for s in _SENSOR]),
        key=("tail", "engine", "cycle"),
        applies="Appended to the engine's health history; the RUL model re-predicts with a calibrated 90 % interval and "
                "module attribution. The new interval replaces the stored one everywhere: alerts, risk, Monte-Carlo "
                "forecasts, engine protection in the flight plan and the planner.",
        notes=("Layout follows NASA C-MAPSS (3 operating settings, 21 sensors). A real fleet's HUMS channels map onto it; "
               "the model must be retrained on that fleet's own history before its numbers are trusted.",
               "At least 5 cycles per engine; 30 or more gives the full rolling-window features.")),
    Contract(
        "snags", "Technical log (Form-700 / e-MMS)", "e-MMS or Form-700 export of defect entries",
        "Snag", "Failure / malfunction report", "SD",
        (Field("date", "date", doc="Date the defect was raised"),
         Field("tail", "str", ref="tail"),
         Field("text", "str", doc="Defect text as written; Hinglish and abbreviations are fine"),
         Field("lru", "str", required=False, ref="lru", doc="LRU code if known (see /api/meta), e.g. HYD_PUMP"),
         Field("reported_by", "str", required=False, doc="Who raised it")),
        applies="Filed in the aircraft's technical log, auto-coded to an ATA chapter with similar past cases, and checked "
                "for repeat defects on the same tail and system."),
    Contract(
        "stock", "Stock levels (IMMOLS)", "IMMOLS stock-on-hand report per stock point",
        "StockLevel", "Material supply (S2000M)", "—",
        (Field("stock_point", "enum", values=tuple(STOCK_POINTS), ref="stock_point", doc="Base store or ED (equipment depot)"),
         Field("lru", "str", ref="lru", doc="LRU code"),
         Field("qty", "int", "units", True, 0, 500, doc="Serviceable units on hand"),
         Field("as_of", "date", required=False)),
        key=("stock_point", "lru"),
        applies="Sets the serviceable stock at that stock point; forecasts, sparing, transfers and the planner use it."),
    Contract(
        "repairs", "Repair-order status (BRD / HAL)", "Repair agency status report for units under repair",
        "RepairOrder", "Repair / overhaul event", "—",
        (Field("serial", "int", ref="serial", doc="Serial number of the unit under repair (S/N)"),
         Field("lru", "str", ref="lru", doc="LRU code; must match the serial"),
         Field("agency", "enum", values=("BRD", "HAL")),
         Field("status", "enum", values=("IN_WORK", "AWAITING_PARTS", "BER"),
               doc="BER = beyond economic repair (condemned)"),
         Field("expected_return", "date", doc="Agency's promised return date"),
         Field("finding", "enum", required=False, values=("CONFIRMED", "NFF"), doc="Shop finding, if known")),
        key=("serial",),
        applies="Updates the unit's return date (or condemns it) in the repair pipeline; spares availability, "
                "forecasts and the depot-expedite advice follow."),
    Contract(
        "sorties", "Flying records", "Squadron flying log",
        "Sortie", "Operation / usage", "DA",
        (Field("date", "date"), Field("tail", "str", ref="tail"),
         Field("hours", "float", "FH", True, 0.1, 8),
         Field("mission", "enum", required=False, values=tuple(MISSIONS))),
        applies="Validated against the contract; usage feeds the survival models at the next retrain (make train).",
        validate_only=True),
]}


@dataclass
class Register:
    """What the fleet knows about: used to check references in an upload."""
    tails: set
    engines_per_tail: dict
    lrus: set
    stock_points: set
    serial_type: dict              # serial -> lru id (every serial the twin knows)
    serial_where: dict = field(default_factory=dict)   # serial -> where it is now (installed / stock / repair)

    @classmethod
    def from_state(cls, st) -> "Register":
        from ..twin.state import LRU_IDS, SP_IDS, TYPE_IDS
        where = {}
        for p in range(len(st.pos_serial)):
            s = int(st.pos_serial[p])
            if s >= 0:
                where[s] = f"installed on {st.tail_ids[int(st.pos_tail[p])]}"
        for (sp, _), sers in st.stock.items():
            for s in sers:
                where[int(s)] = f"in stock at {SP_IDS[sp]}"
        for (_, s, _) in st.pipeline:
            where[int(s)] = "at repair"
        return cls(tails=set(st.tail_ids),
                   engines_per_tail={t: AIRCRAFT_TYPES[TYPE_IDS[int(st.tail_type[i])]].engines for i, t in enumerate(st.tail_ids)},
                   lrus=set(LRU_TYPES), stock_points=set(STOCK_POINTS),
                   serial_type={s: LRU_IDS[int(st.ser_type[s])] for s in range(st.n_ser)}, serial_where=where)


def read_csv(raw: bytes) -> tuple[pd.DataFrame | None, str | None]:
    try:
        df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, skipinitialspace=True)
    except Exception as e:  # noqa: BLE001
        return None, f"Could not read the file as CSV: {e}"
    return df, None


def _coerce(f: Field, s: pd.Series) -> tuple[pd.Series, pd.Series, str]:
    """Typed values, a mask of bad cells, and the reason text."""
    raw = s.astype(str).str.strip()
    empty = raw.eq("") | raw.str.lower().isin(["nan", "none", "null"])
    if f.type in ("int", "float"):
        v = pd.to_numeric(raw.where(~empty), errors="coerce")
        bad = v.isna() & ~empty
        why = "not a number"
        if f.type == "int":
            frac = v.notna() & (v != v.round())
            bad |= frac
            why = "not a whole number"
        if f.lo is not None or f.hi is not None:
            out = v.notna() & ((v < (f.lo if f.lo is not None else -np.inf)) | (v > (f.hi if f.hi is not None else np.inf)))
            bad |= out
            why += f" or outside {f.lo:g}–{f.hi:g} {f.unit}".rstrip()
        return v, bad, why
    if f.type == "date":
        v = pd.to_datetime(raw.where(~empty), errors="coerce", dayfirst=False, format="mixed")
        return v, v.isna() & ~empty, "not a date (use YYYY-MM-DD)"
    if f.type == "enum":
        up = raw.str.upper()
        allowed = {str(a).upper(): a for a in f.values}
        v = up.map(allowed)
        return v, v.isna() & ~empty, f"must be one of {', '.join(map(str, f.values))}"
    return raw.where(~empty), pd.Series(False, index=s.index), ""


def validate(source: str, df: pd.DataFrame, reg: Register, max_row_errors: int = 50) -> tuple[dict, pd.DataFrame]:
    """Check ``df`` against the contract. Returns (report, accepted rows with typed values)."""
    c = CONTRACTS[source]
    canon = {f.name.lower(): f.name for f in c.fields}
    df = df.rename(columns={col: canon.get(col.strip().lower(), col.strip()) for col in df.columns})
    rep = {"source": source, "title": c.title, "rows": int(len(df)), "accepted": 0, "rejected": 0,
           "errors": [], "row_errors": [], "warnings": [], "validate_only": c.validate_only}
    missing = [f.name for f in c.fields if f.required and f.name not in df.columns]
    if missing:
        rep["errors"].append(f"Missing required column(s): {', '.join(missing)}")
    extra = [col for col in df.columns if col not in canon.values()]
    if extra:
        rep["warnings"].append(f"Ignored column(s) not in the contract: {', '.join(extra[:8])}")
    if len(df) == 0:
        rep["errors"].append("The file has no data rows")
    if len(df) > MAX_ROWS:
        rep["errors"].append(f"Too many rows ({len(df):,}); split the export into files of at most {MAX_ROWS:,}")
    if rep["errors"]:
        rep["ok"] = False
        return rep, df.iloc[0:0]

    bad = pd.Series(False, index=df.index)
    reasons: dict[int, list[str]] = {}

    def flag(mask: pd.Series, text: str):
        nonlocal bad
        for i in df.index[mask.fillna(False).to_numpy()]:
            reasons.setdefault(i, []).append(text)
        bad = bad | mask.fillna(False)

    out = pd.DataFrame(index=df.index)
    present = 0
    for f in c.fields:
        if f.name not in df.columns:
            out[f.name] = None
            continue
        v, b, why = _coerce(f, df[f.name])
        flag(b, f"{f.name}: '{{}}' {why}")
        if f.required:
            flag(v.isna() & ~b, f"{f.name}: required value missing")
        present += int(v.notna().sum())
        out[f.name] = v
    # turn the placeholder into the actual cell value
    for i, rs in reasons.items():
        reasons[i] = [r.replace("'{}'", repr(str(df.at[i, r.split(':')[0]]))) if "'{}'" in r else r for r in rs]

    if "tail" in out:
        flag(out["tail"].notna() & ~out["tail"].isin(reg.tails), "tail: not in the fleet register")
    if "lru" in out:
        flag(out["lru"].notna() & ~out["lru"].isin(reg.lrus), "lru: unknown LRU code (see /api/meta)")
    if source == "hums":
        n_eng = out["tail"].map(reg.engines_per_tail)
        flag(out["engine"].notna() & n_eng.notna() & (out["engine"] > n_eng), "engine: the aircraft type has fewer engines")
    if source == "repairs":
        known = out["serial"].map(lambda s: reg.serial_type.get(int(s)) if pd.notna(s) else None)
        flag(out["serial"].notna() & known.isna(), "serial: no such serial number")
        flag(known.notna() & out["lru"].notna() & (known != out["lru"]), "lru: does not match the serial's part type")
        for i in out.index[known.notna().to_numpy()]:
            w = reg.serial_where.get(int(out.at[i, "serial"]), "not tracked")
            if w != "at repair":
                flag(pd.Series(out.index == i, index=out.index), f"serial: not at a repair agency ({w})")
    if c.key and all(k in out for k in c.key):
        dup = out.duplicated(list(c.key), keep="last") & out[list(c.key)].notna().all(axis=1)
        flag(dup, f"duplicate of a later row with the same {' + '.join(c.key)}")

    accepted = out[~bad].copy()
    rep["accepted"], rep["rejected"] = int(len(accepted)), int(bad.sum())
    rep["row_errors"] = [{"line": int(i) + 2, "reasons": rs} for i, rs in list(reasons.items())[:max_row_errors]]
    if len(reasons) > max_row_errors:
        rep["warnings"].append(f"{len(reasons) - max_row_errors} more rejected rows not listed")
    rep["completeness"] = round(present / max(1, len(df) * len(c.fields)), 4)
    if source == "hums" and len(accepted):
        per = accepted.groupby(["tail", "engine"]).size()
        short = [f"{t} engine {int(e)}" for (t, e), n in per.items() if n < 5]
        if short:
            rep["warnings"].append(f"Fewer than 5 cycles for {', '.join(short)}: those engines will not be updated")
        rep["engines"] = [{"tail": t, "engine": int(e), "cycles": int(n)} for (t, e), n in per.items()]
    rep["ok"] = rep["accepted"] > 0
    if not rep["ok"] and not rep["errors"]:
        rep["errors"].append("No row passed validation")
    return rep, accepted


def markdown() -> str:
    """docs/05-data-contracts.md — generated from the contracts above (a test keeps it in sync)."""
    lines = ["# 05 · Data contracts (generated from `backend/tatpar/ingest/contracts.py`)", "",
             "How a unit feeds its own data into TATPAR. Each source is a CSV export; `POST /api/ingest/{source}` "
             "validates it row by row against the contract below and the fleet register, then applies the accepted rows. "
             "`POST /api/ingest/{source}/validate` checks a file without storing anything. Templates and samples: "
             "`GET /api/ingest/template/{source}` (add `?sample=true`), or `data/samples/`.", "",
             "Every import is recorded with its file hash, row counts and the signed-in user, and written to the "
             "hash-chained decision ledger. `python -m tatpar.ingest reset` removes all imported data.", ""]
    for c in CONTRACTS.values():
        lines += [f"## `{c.source}` — {c.title}", "",
                  f"*Produced by:* {c.system}. *Entity:* {c.entity} (S5000F: {c.s5000f}; OSA-CBM: {c.osa_cbm}).", "",
                  f"*What an import changes:* {c.applies}", ""]
        if c.key:
            lines += [f"*Record key:* {' + '.join(c.key)} (a later duplicate replaces an earlier one).", ""]
        lines += ["| Field | Type | Unit | Required | Allowed | Meaning |", "|---|---|---|---|---|---|"]
        for f in c.fields:
            allowed = (", ".join(map(str, f.values)) if f.values else
                       f"{f.lo:g} – {f.hi:g}" if f.lo is not None else
                       {"tail": "a tail in the fleet register", "lru": "an LRU code", "serial": "a known serial",
                        "stock_point": "a stock point"}.get(f.ref, ""))
            lines.append(f"| `{f.name}` | {f.type} | {f.unit} | {'yes' if f.required else 'no'} | {allowed} | {f.doc} |")
        lines += [""] + [f"> {n}" for n in c.notes] + ([""] if c.notes else [])
    return "\n".join(lines).rstrip() + "\n"
