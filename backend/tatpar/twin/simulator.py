"""Day-stepped simulation of the sustainment system.

One ``Simulator`` advances a ``FleetState`` day by day under a ``Policy``:

    arrivals -> job completions -> spares allocation (lateral, cannibalisation)
    -> scheduled checks (bays, depot slots, bundling) -> flying (policy dispatch)
    -> life consumption -> failures / No-Fault-Found snags -> removals -> status

Life consumption is vectorised over all installed positions, so a 64-aircraft, 60-day
Monte-Carlo run takes a fraction of a second.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from math import ceil, exp, log, sqrt

import numpy as np

from ..config import HISTORY_START
from ..domain.catalog import AIRCRAFT_TYPES, DEPOT_SLOTS, LRU_TYPES, MISSIONS, SQUADRONS, TRANSIT_DAYS
from ..domain.environment import base_features
from .policies import BASELINE, Policy, demand_profile
from .state import (
    CHECKS, COV_KEYS, DEPOT, ED, ENGINE_IDX, LRU_IDS, MC, NMCM_S, NMCM_U, NMCS, SP_IDS, SQN_IDS,
    TYPE_IDS, WAIT, FleetState,
)

START = date.fromisoformat(HISTORY_START)
MISSION_NAMES = list(MISSIONS)
MISSION_G = np.array([MISSIONS[m] for m in MISSION_NAMES])
FEATS = ("dust", "heat", "hum", "alt", "salt")

# Static per-type arrays
_L = [LRU_TYPES[k] for k in LRU_IDS]
SENS = np.array([[l.sens[f] for f in FEATS] for l in _L])          # [lru, 5]
G_SENS = np.array([l.sens["g"] for l in _L])
NFF_RATE = np.array([(l.nff_frac / (1 - l.nff_frac)) / l.mean_life_fh for l in _L])
TAT = np.array([l.tat_days for l in _L])
JOB_DAYS = np.array([2 if l.is_engine else 1 for l in _L])


def day_to_date(d: int) -> date:
    return START + timedelta(days=int(d))


def _feat_table() -> np.ndarray:
    """[month 0..11, stock point, 5 features] using monthly CAMS dust."""
    out = np.zeros((12, len(SP_IDS), len(FEATS)))
    for m in range(12):
        for i, sp in enumerate(SP_IDS):
            if sp == "ED":
                continue
            f = base_features(sp, m + 1)
            out[m, i] = [f[k] for k in FEATS]
    return out


FEAT = _feat_table()
ENV_MULT = np.exp(np.einsum("msf,lf->msl", FEAT, SENS))            # [month, sp, lru]
HUM_NFF = np.exp(0.4 * FEAT[..., 2])                                  # [month, sp]


@dataclass
class Scenario:
    """External conditions for a run: flying-task surges and readiness requirements, plus the
    sensitivity knobs used to test whether results survive different assumptions about the world."""
    surges: list[tuple[int, int, int, float]] = field(default_factory=list)   # (sqn, start_day, end_day, factor)
    requirements: list[tuple[int, int, int, int]] = field(default_factory=list)  # (sqn, start, end, min_mc)
    life_mult: float = 1.0      # true LRU lives × this (0.77 ≈ 30 % more failures)
    tat_mult: float = 1.0       # repair turnaround at BRD / HAL × this
    task_mult: float = 1.0      # flying task (sorties demanded) × this
    stock_mult: float = 1.0     # spares on hand × this (≈ inventory budget)
    extra_bays: int = 0         # additional phase-check bays per squadron
    risk_mult: float = 1.0      # prognostic risk the policies see × this (model bias)

    def factor(self, sqn: int, day: int) -> float:
        f = self.task_mult
        for s, a, b, k in self.surges:
            if s == sqn and a <= day <= b:
                f *= k
        return f


class Simulator:
    def __init__(self, state: FleetState, policy: Policy = BASELINE, scenario: Scenario | None = None,
                 seed: int = 0, record: bool = False):
        self.s = state
        self.p = policy
        self.sc = scenario or Scenario()
        self.rng = np.random.default_rng(seed)
        self.record = record
        self.rec: dict[str, list] = {k: [] for k in (
            "sorties", "snags", "removals", "checks", "supply", "cann", "status", "repairs")}
        self.status_hist: list[np.ndarray] = []
        self.sortie_short: list[np.ndarray] = []
        self._retested: set[int] = set()
        self._swap_pending: set[int] = set()
        self.counters = {"cann": 0, "nff_removals": 0, "nff_avoided": 0, "removals": 0,
                         "preventive": 0, "lateral": 0, "unsched_events": 0}
        sq = list(SQUADRONS.values())
        self.sq_bays = np.array([x.bays for x in sq]) + self.sc.extra_bays
        self.sq_wd = np.array([x.sorties_weekday for x in sq])
        self.sq_sat = np.array([x.sorties_saturday for x in sq])
        self.sq_mix = [np.array([x.mission_mix.get(m, 0) for m in MISSION_NAMES]) for x in sq]
        self.types = [AIRCRAFT_TYPES[TYPE_IDS[t]] for t in range(len(TYPE_IDS))]
        self._risk_cache: tuple[int, np.ndarray] | None = None

    # ================================================================== main loop
    def run(self, days: int) -> "Simulator":
        for _ in range(days):
            self.step()
        return self

    def step(self) -> None:
        s = self.s
        d = s.day
        today = day_to_date(d)
        month = today.month - 1
        self._arrivals(d)
        self._complete_jobs(d)
        self._ed_fulfil(d)
        self._allocate(d)
        if self.p.proactive_spares and today.weekday() == 0:
            self._proactive_spares(d)
        self._start_checks(d)
        hours, gmean = self._fly(d, today)
        self._consume(d, month, hours, gmean)
        st = s.status()
        self.status_hist.append(st)
        if self.record:
            for t in np.flatnonzero(st != MC):
                self.rec["status"].append((d, t, int(st[t])))
        s.day += 1

    # ================================================================== logistics
    def _arrivals(self, d: int) -> None:
        s = self.s
        keep = []
        for (arr, sp, ser, pos) in s.shipments:
            if arr > d:
                keep.append((arr, sp, ser, pos))
                continue
            if pos >= 0 and s.pos_serial[pos] < 0 and self._open_bo(pos) is not None:
                self._install(pos, ser, d, source="shipment")
            elif pos >= 0 and pos in self._swap_pending:
                self._swap_engine(pos, ser, d)
            else:
                s.stock.setdefault((sp, int(s.ser_type[ser])), []).append(ser)
        s.shipments = keep

        keep = []
        for (ret, ser, condemned) in s.pipeline:
            if ret > d:
                keep.append((ret, ser, condemned))
                continue
            li = int(s.ser_type[ser])
            if condemned:
                lead = LRU_TYPES[LRU_IDS[li]].lead_days * self.rng.uniform(0.8, 1.3)
                s.procurement.append((d + int(lead), li))
            else:
                s.stock.setdefault((ED, li), []).append(ser)
        s.pipeline = keep

        keep = []
        for (arr, li) in s.procurement:
            if arr > d:
                keep.append((arr, li))
            else:
                s.stock.setdefault((ED, li), []).append(s.new_serial(li, self.rng))
        s.procurement = keep

    def _ed_fulfil(self, d: int) -> None:
        s = self.s
        if not s.ed_queue:
            return
        # AOG (reserved) requests first, then stock replenishment; FIFO within each class
        s.ed_queue.sort(key=lambda r: (r[3] < 0, r[0]))
        keep = []
        for req in s.ed_queue:
            since, sp, li, pos = req
            if pos >= 0 and (s.pos_serial[pos] >= 0 or self._open_bo(pos) is None) and pos not in self._swap_pending:
                continue  # demand already satisfied another way
            lst = s.stock.get((ED, li), [])
            if lst:
                ser = lst.pop(0)
                s.shipments.append((d + TRANSIT_DAYS, sp, ser, pos))
                if self.record:
                    self.rec["supply"].append((d, LRU_IDS[li], "ED", SP_IDS[sp], "issue_aog" if pos >= 0 else "replenish"))
            else:
                keep.append(req)
        s.ed_queue = keep

    def _open_bo(self, pos: int):
        for b in self.s.backorders:
            if b["pos"] == pos:
                return b
        return None

    def _inbound(self, pos: int) -> bool:
        return any(p == pos for (_, _, _, p) in self.s.shipments)

    def _install(self, pos: int, ser: int, d: int, source: str) -> None:
        s = self.s
        t = int(s.pos_tail[pos])
        s.pos_serial[pos] = ser
        s.missing[t] -= 1
        bo = self._open_bo(pos)
        if bo is not None:
            s.backorders.remove(bo)
        if s.missing[t] == 0:
            s.nmcs_since[t] = -1
        li = int(s.pos_type[pos])
        if not s.check_kind[t]:
            self._crew_job(t, d, int(JOB_DAYS[li]))

    def _crew_job(self, t: int, d: int, dur: int) -> None:
        s = self.s
        crews = s.crew_free[int(s.tail_sqn[t])]
        k = int(np.argmin(crews))
        start = max(d + 1, crews[k])
        end = start + dur
        crews[k] = end
        s.unsched_end[t] = max(s.unsched_end[t], end)

    def _take_from_base(self, sp: int, li: int):
        lst = self.s.stock.get((sp, li), [])
        return lst.pop(0) if lst else None

    def _allocate(self, d: int) -> None:
        """Fill open backorders: base stock -> ED request -> lateral -> cannibalisation."""
        s = self.s
        for bo in sorted(list(s.backorders), key=lambda b: b["since"]):
            if bo not in s.backorders:
                continue
            pos, li = bo["pos"], bo["li"]
            t = int(s.pos_tail[pos])
            sp = int(s.tail_sp[t])
            ser = self._take_from_base(sp, li)
            if ser is not None:
                self._install(pos, ser, d, "base_stock")
                s.ed_queue.append((d, sp, li, -1))     # replenish base stock
                if self.record:
                    self.rec["supply"].append((d, LRU_IDS[li], SP_IDS[sp], s.tail_ids[t], "issue"))
                continue
            if not bo["requested"]:
                s.ed_queue.append((d, sp, li, pos))
                bo["requested"] = True
            wait = d - bo["since"]
            ed_has = bool(s.stock.get((ED, li)))
            if not ed_has and not self._inbound(pos) and wait >= self.p.lateral_after_days:
                donor_sp = self._lateral_source(sp, li)
                if donor_sp is not None:
                    ser = s.stock[(donor_sp, li)].pop(0)
                    s.shipments.append((d + TRANSIT_DAYS, sp, ser, pos))
                    self.counters["lateral"] += 1
                    if self.record:
                        self.rec["supply"].append((d, LRU_IDS[li], SP_IDS[donor_sp], SP_IDS[sp], "lateral"))
                    continue
            if (self.p.cann != "none" and wait >= self.p.cann_after_days and not self._inbound(pos)
                    and not bo["cann"] and s.missing[t] == 1 and not s.check_kind[t]):
                self._try_cann(bo, d)

    def _lateral_source(self, sp: int, li: int):
        s = self.s
        best, best_q = None, 0
        for (k_sp, k_li), lst in s.stock.items():
            if k_li != li or k_sp in (sp, ED) or not lst:
                continue
            q = len(lst)
            if self.p.proactive_spares:
                q -= self._expected_demand(k_sp, li, 14)  # keep what the donor base itself needs
            if q > best_q:
                best, best_q = k_sp, q
        return best

    def _try_cann(self, bo: dict, d: int) -> None:
        s = self.s
        pos, li = bo["pos"], bo["li"]
        t = int(s.pos_tail[pos])
        sq = s.tail_sqn[t]
        st = s.status()
        cands = []
        for p2 in np.flatnonzero((s.pos_type == li) & (s.pos_serial >= 0)):
            t2 = int(s.pos_tail[p2])
            if t2 == t or s.tail_sqn[t2] != sq or s.check_kind[t2] == "overhaul":
                continue
            st2 = st[t2]
            if self.p.cann == "consolidated":
                if st2 == NMCS:
                    cands.append((-(d - s.nmcs_since[t2]), p2))          # longest-down donor first
                elif st2 == NMCM_S and s.check_end[t2] - d >= 4:
                    cands.append((0, p2))
            else:  # ad-hoc
                if st2 in (NMCS, NMCM_S, WAIT):
                    cands.append((self.rng.random(), p2))
                elif st2 == MC and self.rng.random() < self.p.adhoc_rob_mc_prob / 10:
                    cands.append((1 + self.rng.random(), p2))
        if not cands:
            return
        cands.sort()
        p2 = cands[0][1]
        t2 = int(s.pos_tail[p2])
        ser = int(s.pos_serial[p2])
        s.pos_serial[p2] = -1
        s.missing[t2] += 1
        if s.nmcs_since[t2] < 0:
            s.nmcs_since[t2] = d
        s.backorders.append({"pos": int(p2), "li": li, "since": d, "requested": False, "cann": True})
        self.counters["cann"] += 1
        if self.record:
            self.rec["cann"].append((d, s.tail_ids[t2], s.tail_ids[t], LRU_IDS[li], int(ser)))
        self._install(pos, ser, d, "cann")
        if not s.check_kind[t2]:
            self._crew_job(t2, d, 1)   # removal labour on the donor

    # ================================================================== prognostic levers
    def _risk(self, d: int, horizon_days: int) -> np.ndarray:
        if self.p.risk_fn is None:
            return np.zeros(len(self.s.pos_tail))
        key = (d, horizon_days)
        if self._risk_cache is None or self._risk_cache[0] != key:
            self._risk_cache = (key, self.p.risk_fn(self.s, horizon_days))
        return self._risk_cache[1]

    def _expected_demand(self, sp: int, li: int, horizon: int) -> float:
        r = self._risk(self.s.day, horizon)
        mask = (self.s.pos_type == li) & (self.s.tail_sp[self.s.pos_tail] == sp)
        return float(r[mask].sum())

    def _proactive_spares(self, d: int) -> None:
        s = self.s
        r = self._risk(d, 14)
        for sp_name in dict.fromkeys(SQUADRONS[q].base for q in SQN_IDS):  # ordered: set order varies by process
            sp = SP_IDS.index(sp_name)
            at_base = s.tail_sp[s.pos_tail] == sp
            for li in range(len(LRU_IDS)):
                if li == ENGINE_IDX:
                    continue
                mask = at_base & (s.pos_type == li)
                if not mask.any():
                    continue
                exp_dem = float(r[mask].sum())
                target = int(ceil(exp_dem + 1.0 * sqrt(exp_dem))) if exp_dem > 0.15 else 0
                have = len(s.stock.get((sp, li), [])) + sum(
                    1 for (_, sp2, ser, p) in s.shipments if sp2 == sp and p < 0 and s.ser_type[ser] == li)
                pending = sum(1 for (_, sp2, l2, p) in s.ed_queue if sp2 == sp and l2 == li and p < 0)
                for _ in range(max(0, target - have - pending)):
                    s.ed_queue.append((d, sp, li, -1))

    def _bundle(self, t: int, d: int, horizon_days: int) -> None:
        s = self.s
        r = self._risk(d, horizon_days)
        sp = int(s.tail_sp[t])
        for pos in s.positions_of(t):
            if s.pos_serial[pos] < 0:
                continue
            li = int(s.pos_type[pos])
            # engines: swap when failure before the next phase is likely; LRUs only when near-certain
            thr = self.p.bundle_threshold if li == ENGINE_IDX else max(0.8, self.p.bundle_threshold)
            if r[pos] < thr:
                continue
            if li == ENGINE_IDX:
                # only from surplus depot engines (keep one for AOG) and never queued ahead of AOG demands
                ed_eng = s.stock.get((ED, li), [])
                if pos not in self._swap_pending and len(ed_eng) >= 2:
                    self._swap_pending.add(int(pos))
                    s.shipments.append((d + TRANSIT_DAYS, sp, ed_eng.pop(0), int(pos)))
                continue
            ser = self._take_from_base(sp, li)
            if ser is None:
                continue
            old = int(s.pos_serial[pos])
            s.pos_serial[pos] = ser
            self._send_to_repair(old, d, "PREVENTIVE")
            s.ed_queue.append((d, sp, li, -1))
            self.counters["preventive"] += 1

    def _swap_engine(self, pos: int, ser: int, d: int) -> None:
        s = self.s
        self._swap_pending.discard(pos)
        old = int(s.pos_serial[pos])
        s.pos_serial[pos] = ser
        if old >= 0:
            self._send_to_repair(old, d, "PREVENTIVE")
        t = int(s.pos_tail[pos])
        if not s.check_kind[t]:
            self._crew_job(t, d, 2)
        self.counters["preventive"] += 1

    # ================================================================== maintenance
    def _complete_jobs(self, d: int) -> None:
        s = self.s
        for t in range(s.n_tails):
            ck = s.check_kind[t]
            if ck and s.check_end[t] <= d:
                if self.record:
                    self.rec["checks"].append((s.tail_ids[t], ck, int(s.check_end[t] - self.types[s.tail_type[t]].check(ck).duration_days), int(s.check_end[t])))
                s.hrs_since[ck][t] = 0.0
                if ck == "overhaul":
                    s.hrs_since["phase"][t] = 0.0
                    s.hrs_since["minor"][t] = 0.0
                elif ck == "phase":
                    s.hrs_since["minor"][t] = 0.0
                s.check_kind[t] = ""

    def _residual(self, t: int) -> float:
        ty = self.types[self.s.tail_type[t]]
        return min(ty.check(c).interval_fh - self.s.hrs_since[c][t] for c in CHECKS)

    def _start_checks(self, d: int) -> None:
        s = self.s
        p = self.p
        in_phase = np.zeros(len(SQN_IDS), int)
        in_depot = 0
        for t in range(s.n_tails):
            if s.check_kind[t] == "phase":
                in_phase[s.tail_sqn[t]] += 1
            elif s.check_kind[t] == "overhaul":
                in_depot += 1
        planned = set()
        if p.plan:
            planned = {(tl, c) for (tl, c, day) in p.plan.get("checks", []) if day == d}
        order = sorted(range(s.n_tails), key=lambda t: self._residual(t))
        for t in order:
            s.due_wait[t] = False
            if s.check_kind[t] or s.unsched_end[t] > d:
                continue
            if s.missing[t] > 0 and not p.overlap_checks_with_nmcs:
                continue
            ty = self.types[s.tail_type[t]]
            todo = None
            for c in ("overhaul", "phase", "minor"):
                ck = ty.check(c)
                if s.hrs_since[c][t] + ty.sortie_hours > ck.interval_fh or (s.tail_ids[t], c) in planned:
                    todo = ck
                    break
            if todo is None and p.early_phase:
                ck = ty.check("phase")
                left = ck.interval_fh - s.hrs_since["phase"][t]
                if left < 0.12 * ck.interval_fh and in_phase[s.tail_sqn[t]] < self.sq_bays[s.tail_sqn[t]] - 0:
                    # a bay is free and this tail is close: take the slot now instead of queueing later
                    todo = ck if self._bay_idle_soon(s.tail_sqn[t], d, in_phase) else None
            if todo is None:
                continue
            sq = s.tail_sqn[t]
            if todo.id == "phase" and in_phase[sq] >= self.sq_bays[sq]:
                s.due_wait[t] = True
                continue
            if todo.id == "overhaul" and in_depot >= DEPOT_SLOTS:
                s.due_wait[t] = True
                continue
            s.check_kind[t] = todo.id
            s.check_end[t] = d + todo.duration_days
            if todo.id == "phase":
                in_phase[sq] += 1
                if p.bundling:
                    self._bundle(t, d, horizon_days=int(todo.interval_fh / 1.3))
            elif todo.id == "overhaul":
                in_depot += 1

    def _bay_idle_soon(self, sq: int, d: int, in_phase: np.ndarray) -> bool:
        """True if no other tail of the squadron will need a phase bay in the next check duration."""
        s = self.s
        ty_ok = 0
        for t in np.flatnonzero(s.tail_sqn == sq):
            if s.check_kind[t]:
                continue
            ty = self.types[s.tail_type[t]]
            left = ty.check("phase").interval_fh - s.hrs_since["phase"][t]
            if left < ty.sortie_hours * 2:
                ty_ok += 1
        return in_phase[sq] + ty_ok < self.sq_bays[sq]

    # ================================================================== flying
    def _fly(self, d: int, today: date):
        s = self.s
        p = self.p
        hours = np.zeros(s.n_tails)
        gsum = np.zeros(s.n_tails)
        st = s.status()
        short = np.zeros(len(SQN_IDS))
        plan_h = p.plan.get("hours", {}) if p.plan else {}
        plan_day = d - p.plan.get("start_day", 0) if p.plan else 0
        for sq in range(len(SQN_IDS)):
            n_req = demand_profile(int(self.sq_wd[sq]), int(self.sq_sat[sq]), today.weekday())
            n_req = int(round(n_req * self.sc.factor(sq, d)))
            if n_req == 0:
                continue
            tails = np.flatnonzero(s.tail_sqn == sq)
            ty = self.types[s.tail_type[tails[0]]]
            sh = ty.sortie_hours
            cand = [t for t in tails if st[t] == MC and self._residual(t) >= sh]
            if p.dispatch == "flow":
                key = self._flow_priority(tails)
                cand.sort(key=lambda t: -key[t])
            elif p.dispatch == "plan" and plan_h:
                key = self._flow_priority(tails)
                cand.sort(key=lambda t: (-self._plan_hours(plan_h, t, plan_day), -key[t]))
            else:
                # current practice: fly the aircraft with the most hours left before its phase check
                iv = ty.check("phase").interval_fh
                cand.sort(key=lambda t: -(iv - s.hrs_since["phase"][t]))
            remaining = n_req
            for rnd in range(ty.max_sorties_per_day):
                for t in cand:
                    if remaining == 0:
                        break
                    if self._residual(t) - hours[t] < sh:
                        continue
                    if p.dispatch == "plan" and plan_h and rnd > 0 and self._plan_hours(plan_h, t, plan_day) <= hours[t]:
                        continue
                    m = self.rng.choice(len(MISSION_NAMES), p=self.sq_mix[sq])
                    hours[t] += sh
                    gsum[t] += sh * MISSION_G[m]
                    remaining -= 1
            short[sq] = remaining
        flown = hours > 0
        s.hrs_total += hours
        for c in CHECKS:
            s.hrs_since[c] += hours
        gmean = np.where(flown, gsum / np.maximum(hours, 1e-9), 1.0)
        self.sortie_short.append(short)
        if self.record:
            for t in np.flatnonzero(flown):
                self.rec["sorties"].append((d, int(t), float(hours[t]), float(gmean[t])))
        return hours, gmean

    def _plan_hours(self, plan_h: dict, t: int, k: int) -> float:
        arr = plan_h.get(self.s.tail_ids[t])
        if arr is None or k < 0 or k >= len(arr):
            return 0.0
        return float(arr[k])

    def _flow_priority(self, tails: np.ndarray) -> dict[int, float]:
        """Surplus of residual phase hours over an evenly staggered ladder (fly the surplus first)."""
        s = self.s
        ty = self.types[s.tail_type[tails[0]]]
        iv = ty.check("phase").interval_fh
        res = np.array([iv - s.hrs_since["phase"][t] for t in tails])
        order = np.argsort(res)
        n = len(tails)
        target = iv * (np.arange(n) + 0.5) / n
        out = {}
        for rank, idx in enumerate(order):
            out[int(tails[idx])] = res[idx] - target[rank]
        return out

    # ================================================================== failures
    def _consume(self, d: int, month: int, hours: np.ndarray, gmean: np.ndarray) -> None:
        s = self.s
        installed = s.pos_serial >= 0
        pt = s.pos_tail
        h = hours[pt]
        active = installed & (h > 0)
        if not active.any():
            return
        idx = np.flatnonzero(active)
        ser = s.pos_serial[idx]
        sp = s.tail_sp[pt[idx]]
        li = s.pos_type[idx]
        g = gmean[pt[idx]]
        hh = h[idx]
        mult = ENV_MULT[month, sp, li] * np.exp(G_SENS[li] * (g - 1.0))
        s.ser_age[ser] += hh * mult
        s.ser_hrs[ser] += hh
        s.ser_cov[ser, :5] += hh[:, None] * FEAT[month, sp]
        s.ser_cov[ser, 5] += hh * g
        failed = idx[s.ser_age[ser] >= s.ser_L[ser]]
        # No-Fault-Found process (intermittents, troubleshooting by substitution)
        s.pos_nff_budget[idx] -= hh * NFF_RATE[li] * HUM_NFF[month, sp]
        nff = idx[s.pos_nff_budget[idx] <= 0]
        for p in nff:
            s.pos_nff_budget[p] = self.rng.exponential(1.0)
        events: dict[int, list[tuple[int, str]]] = {}
        for p in failed:
            events.setdefault(int(pt[p]), []).append((int(p), "failure"))
        failed_set = set(int(x) for x in failed)
        for p in nff:
            if int(p) not in failed_set:
                events.setdefault(int(pt[p]), []).append((int(p), "nff"))
        for t, evs in events.items():
            self._snag(t, evs, d, month)

    def _snag(self, t: int, evs: list[tuple[int, str]], d: int, month: int) -> None:
        s = self.s
        p = self.p
        any_removal = False
        for pos, kind in evs:
            if s.pos_serial[pos] < 0:
                continue   # part was cannibalised earlier the same evening; its snag moves with it
            li = int(s.pos_type[pos])
            is_nff = kind == "nff"
            intermittent = self.rng.random() < (0.6 if is_nff else 0.12)
            bite_reset = self.rng.random() < (0.45 if is_nff else 0.08)
            if self.record:
                self.rec["snags"].append((d, s.tail_ids[t], LRU_IDS[li], int(pos), kind, bool(intermittent),
                                          bool(bite_reset), int(s.pos_serial[pos])))
            self.counters["unsched_events"] += 1
            if p.nff_screen and pos not in self._retested:
                flagged = self.rng.random() < (p.nff_tpr if is_nff else p.nff_fpr)
                if flagged:
                    self._retested.add(pos)
                    if is_nff:
                        self.counters["nff_avoided"] += 1
                    if not s.check_kind[t]:
                        self._crew_job(t, d, 1)       # ground re-test instead of removal
                    continue
            self._retested.discard(pos)
            ser = int(s.pos_serial[pos])
            s.pos_serial[pos] = -1
            s.missing[t] += 1
            if s.nmcs_since[t] < 0:
                s.nmcs_since[t] = d
            finding = "NFF" if is_nff else "CONFIRMED"
            self._send_to_repair(ser, d, finding, tail=t)
            self.counters["removals"] += 1
            if is_nff:
                self.counters["nff_removals"] += 1
            s.backorders.append({"pos": int(pos), "li": li, "since": d, "requested": False, "cann": False})
            any_removal = True
        if any_removal:
            self._allocate(d)

    def _send_to_repair(self, ser: int, d: int, finding: str, tail: int | None = None) -> None:
        s = self.s
        li = int(s.ser_type[ser])
        if self.record:
            self.rec["removals"].append({
                "day": d, "tail": s.tail_ids[tail] if tail is not None else "", "lru": LRU_IDS[li],
                "serial": int(ser), "finding": finding, "hours": float(s.ser_hrs[ser]),
                "life_start": int(s.ser_life_start[ser]), "repairs": int(s.ser_repairs[ser]),
                "entry": float(s.ser_entry[ser]),
                **{f"cov_{k}": float(s.ser_cov[ser, i]) for i, k in enumerate(COV_KEYS)},
                "rogue_truth": bool(s.ser_rogue[ser]), "engine_unit": int(s.ser_unit[ser]),
                "age_eff": float(s.ser_age[ser]),
            })
        tat = TAT[li] * self.sc.tat_mult
        if finding == "NFF":
            tat *= 0.4
        if li in s.expedite:
            tat *= 0.6
        ret = d + max(3, int(self.rng.lognormal(log(tat) - 0.06, 0.35)))
        condemned = finding == "CONFIRMED" and self.rng.random() < 0.04
        if finding != "NFF":
            s.ser_repairs[ser] += 1
            s.renew(ser)
            s.ser_life_start[ser] = ret
        s.pipeline.append((ret, ser, condemned))
        if self.record:
            self.rec["repairs"].append((int(ser), LRU_IDS[li], d, ret, finding, condemned))

    # ================================================================== metrics
    def status_array(self) -> np.ndarray:
        return np.array(self.status_hist) if self.status_hist else np.zeros((0, self.s.n_tails), np.int8)
