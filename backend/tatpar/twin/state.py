"""Fleet Twin state: tails, installed positions, serialised items, stock and pipelines.

The state carries the *hidden ground truth* (each serial's life budget ``ser_L``). The
analytics never read it; they learn from the records the twin emits.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from ..config import FH_PER_CYCLE, SEED
from ..data import cmapss
from ..domain.catalog import AIRCRAFT_TYPES, LRU_TYPES, SQUADRONS, STOCK_POINTS, tail_numbers

LRU_IDS = list(LRU_TYPES)
LRU_IDX = {k: i for i, k in enumerate(LRU_IDS)}
ENGINE_IDX = LRU_IDX["ENGINE"]
SQN_IDS = list(SQUADRONS)
SP_IDS = STOCK_POINTS                     # base stores ... + "ED"
SP_IDX = {k: i for i, k in enumerate(SP_IDS)}
ED = SP_IDX["ED"]
TYPE_IDS = list(AIRCRAFT_TYPES)

# Daily status codes
MC, NMCM_S, NMCM_U, NMCS, DEPOT, WAIT = range(6)
STATE_NAMES = ["MC", "NMCM_S", "NMCM_U", "NMCS", "DEPOT", "WAIT"]
STATE_LABELS = {
    "MC": "Mission capable", "NMCM_S": "Scheduled maintenance", "NMCM_U": "Unscheduled maintenance",
    "NMCS": "Awaiting spares", "DEPOT": "Depot overhaul", "WAIT": "Awaiting bay / crew",
}
CHECKS = ("minor", "phase", "overhaul")
COV_KEYS = ("dust", "heat", "hum", "alt", "salt", "g")


def draw_life(lru_idx: int, rng: np.random.Generator, rogue: bool) -> float:
    l = LRU_TYPES[LRU_IDS[lru_idx]]
    life = l.eta_fh * rng.weibull(l.beta)
    return life * (0.2 if rogue else 1.0)


@dataclass
class FleetState:
    day: int
    # ---- tails
    tail_ids: list[str]
    tail_sqn: np.ndarray
    tail_sp: np.ndarray          # stock point index of home base
    tail_type: np.ndarray        # index into TYPE_IDS
    hrs_total: np.ndarray
    hrs_since: dict[str, np.ndarray]           # per check type
    check_kind: list[str]                      # "" or check id in progress
    check_end: np.ndarray
    unsched_end: np.ndarray
    missing: np.ndarray                        # empty positions awaiting a part
    due_wait: np.ndarray                       # waiting for bay/slot (bool)
    nmcs_since: np.ndarray
    # ---- positions
    pos_tail: np.ndarray
    pos_type: np.ndarray
    pos_serial: np.ndarray
    pos_nff_budget: np.ndarray
    # ---- serials (growable arrays)
    n_ser: int
    ser_type: np.ndarray
    ser_L: np.ndarray            # hidden: effective life budget
    ser_age: np.ndarray          # effective life consumed since last repair
    ser_hrs: np.ndarray          # actual flight hours since last repair
    ser_cov: np.ndarray          # [n, 6] exposure-weighted covariate sums (hours * feature)
    ser_rogue: np.ndarray
    ser_repairs: np.ndarray
    ser_life_start: np.ndarray   # day the current life started (-1 = before history)
    ser_unit: np.ndarray         # C-MAPSS fleet-unit index for engines (-1 otherwise)
    ser_lives: np.ndarray        # number of lives drawn (for per-serial seeding)
    # ---- logistics
    stock: dict[tuple[int, int], list[int]]
    shipments: list[tuple[int, int, int, int]]      # (arrive_day, sp, serial, reserved_pos or -1)
    pipeline: list[tuple[int, int, bool]]           # (return_day, serial, condemned)
    procurement: list[tuple[int, int]]              # (arrive_day, lru_idx)
    backorders: list[dict]                          # open part demands per position
    ed_queue: list[tuple[int, int, int]]            # (since_day, sp, lru_idx) replenishment
    crew_free: dict[int, list[int]]                 # sqn -> crew next-free days
    engine_units: list[str]                         # C-MAPSS uids backing fleet engines
    engine_unit_life: np.ndarray                    # cycles
    seed: int = SEED
    expedite: set[int] = field(default_factory=set)  # lru types with expedited repair

    # ------------------------------------------------------------------ helpers
    def copy(self) -> "FleetState":
        return copy.deepcopy(self)

    @property
    def n_tails(self) -> int:
        return len(self.tail_ids)

    def ensure_capacity(self, extra: int = 1) -> None:
        if self.n_ser + extra <= len(self.ser_type):
            return
        new = max(len(self.ser_type) * 2, self.n_ser + extra)
        for name in ("ser_type", "ser_L", "ser_age", "ser_hrs", "ser_rogue", "ser_repairs",
                     "ser_life_start", "ser_unit", "ser_lives"):
            a = getattr(self, name)
            b = np.zeros(new, dtype=a.dtype)
            if name in ("ser_unit", "ser_life_start"):
                b[:] = -1
            b[: len(a)] = a
            setattr(self, name, b)
        c = np.zeros((new, len(COV_KEYS)))
        c[: len(self.ser_cov)] = self.ser_cov
        self.ser_cov = c

    def new_serial(self, lru_idx: int, rng: np.random.Generator) -> int:
        self.ensure_capacity()
        s = self.n_ser
        self.n_ser += 1
        l = LRU_TYPES[LRU_IDS[lru_idx]]
        self.ser_type[s] = lru_idx
        self.ser_rogue[s] = bool(l.rogue_prone and rng.random() < 0.06)
        self.ser_repairs[s] = 0
        self.ser_unit[s] = -1
        self.renew(s, rng)
        return s

    def renew(self, s: int, rng: np.random.Generator | None = None) -> None:
        """Start a fresh life (new or repaired item). Life drawn from a per-serial stream for CRN."""
        k = int(self.ser_lives[s])
        r = np.random.default_rng([self.seed, 7919, s, k])
        lru_idx = int(self.ser_type[s])
        if lru_idx == ENGINE_IDX:
            u = int(r.integers(len(self.engine_units)))
            self.ser_unit[s] = u
            self.ser_L[s] = self.engine_unit_life[u] * FH_PER_CYCLE
        else:
            self.ser_L[s] = draw_life(lru_idx, r, bool(self.ser_rogue[s]))
        self.ser_age[s] = 0.0
        self.ser_hrs[s] = 0.0
        self.ser_cov[s] = 0.0
        self.ser_life_start[s] = self.day
        self.ser_lives[s] = k + 1

    def positions_of(self, t: int) -> np.ndarray:
        return np.flatnonzero(self.pos_tail == t)

    def status(self) -> np.ndarray:
        """Derived daily status code per tail."""
        st = np.full(self.n_tails, MC, dtype=np.int8)
        for t in range(self.n_tails):
            ck = self.check_kind[t]
            if ck == "overhaul":
                st[t] = DEPOT
            elif ck:
                st[t] = NMCM_S
            elif self.missing[t] > 0:
                st[t] = NMCS
            elif self.unsched_end[t] > self.day:
                st[t] = NMCM_U
            elif self.due_wait[t]:
                st[t] = WAIT
        return st


def build_initial_state(seed: int = SEED, day: int = 0) -> FleetState:
    """Create the notional fleet at the start of history (day 0)."""
    rng = np.random.default_rng(seed)
    tails = tail_numbers()
    n = len(tails)
    tail_sqn = np.array([SQN_IDS.index(s) for _, s in tails])
    tail_sp = np.array([SP_IDX[SQUADRONS[s].base] for _, s in tails])
    tail_type = np.array([TYPE_IDS.index(SQUADRONS[s].type) for _, s in tails])

    hrs_since = {}
    for c in CHECKS:
        iv = np.array([AIRCRAFT_TYPES[TYPE_IDS[ty]].check(c).interval_fh for ty in tail_type])
        # Slightly clustered starting phase positions (realistic: tails inducted in batches)
        frac = rng.beta(1.6, 1.6, n) if c == "phase" else rng.random(n)
        hrs_since[c] = frac * iv * 0.95
    hrs_total = 600 + rng.random(n) * 2400

    # positions
    pos_tail, pos_type = [], []
    for t in range(n):
        ty = TYPE_IDS[tail_type[t]]
        for li, lid in enumerate(LRU_IDS):
            for _ in range(LRU_TYPES[lid].qpa[ty]):
                pos_tail.append(t)
                pos_type.append(li)
    pos_tail = np.array(pos_tail)
    pos_type = np.array(pos_type)
    n_pos = len(pos_tail)

    split = cmapss.split_units()
    lives = cmapss.unit_lives()
    engine_units = split["fleet"]
    engine_unit_life = lives.loc[engine_units].to_numpy(dtype=float)

    cap = n_pos * 2
    st = FleetState(
        day=day, tail_ids=[t for t, _ in tails], tail_sqn=tail_sqn, tail_sp=tail_sp, tail_type=tail_type,
        hrs_total=hrs_total, hrs_since=hrs_since, check_kind=[""] * n, check_end=np.zeros(n, int),
        unsched_end=np.zeros(n, int), missing=np.zeros(n, int), due_wait=np.zeros(n, bool),
        nmcs_since=np.full(n, -1),
        pos_tail=pos_tail, pos_type=pos_type, pos_serial=np.full(n_pos, -1),
        pos_nff_budget=rng.exponential(1.0, n_pos),
        n_ser=0, ser_type=np.zeros(cap, int), ser_L=np.zeros(cap), ser_age=np.zeros(cap),
        ser_hrs=np.zeros(cap), ser_cov=np.zeros((cap, len(COV_KEYS))), ser_rogue=np.zeros(cap, bool),
        ser_repairs=np.zeros(cap, int), ser_life_start=np.full(cap, -1), ser_unit=np.full(cap, -1),
        ser_lives=np.zeros(cap, int),
        stock={}, shipments=[], pipeline=[], procurement=[], backorders=[], ed_queue=[],
        crew_free={i: [0] * SQUADRONS[s].crews for i, s in enumerate(SQN_IDS)},
        engine_units=engine_units, engine_unit_life=engine_unit_life, seed=seed,
    )

    # install serials with a random amount of life already consumed
    for p in range(n_pos):
        s = st.new_serial(int(pos_type[p]), rng)
        st.ser_age[s] = rng.random() * 0.9 * st.ser_L[s]
        st.ser_life_start[s] = -1
        st.ser_repairs[s] = int(rng.integers(0, 3))
        st.pos_serial[p] = s

    # baseline (current-practice) stock: total spares per type cover ~90 % of the mean
    # repair-pipeline quantity, split 40 % central depot / 60 % bases by demand
    rates = expected_removal_rates()
    for li, lid in enumerate(LRU_IDS):
        total = baseline_total_spares(li, rates)
        bases = {sp_name: rates[(sp_name, li)] for sp_name in SP_IDS if sp_name != "ED"}
        alloc = split_stock(total, bases, ed_share=1.0 if LRU_TYPES[lid].is_engine else 0.4)
        for sp_name, qty in alloc.items():
            st.stock[(SP_IDX[sp_name], li)] = [st.new_serial(li, rng) for _ in range(qty)]
    return st


FH_PER_TAIL_DAY = {"HF": 0.76, "LF": 0.65}   # long-run average utilisation implied by the flying task


def expected_removal_rates() -> dict[tuple[str, int], float]:
    """Expected removals per day for each (base, LRU type) under the normal flying task."""
    from ..domain.environment import severity_multiplier, base_features
    from math import exp

    out: dict[tuple[str, int], float] = {}
    eng_life = float(cmapss.unit_lives().loc[cmapss.split_units()["fleet"]].mean()) * FH_PER_CYCLE
    for sq in SQUADRONS.values():
        fh = sq.n_aircraft * FH_PER_TAIL_DAY[sq.type]
        hum = base_features(sq.base)["hum"]
        for li, lid in enumerate(LRU_IDS):
            l = LRU_TYPES[lid]
            q = l.qpa[sq.type]
            life = eng_life if l.is_engine else l.mean_life_fh
            fail = q * fh * severity_multiplier(l, sq.base, 1.15) / life
            nff = q * fh * (l.nff_frac / (1 - l.nff_frac)) / l.mean_life_fh * exp(0.4 * hum)
            out[(sq.base, li)] = out.get((sq.base, li), 0.0) + fail + nff
    return out


def pipeline_days(li: int) -> float:
    l = LRU_TYPES[LRU_IDS[li]]
    return l.tat_days + 3 + 0.04 * l.lead_days


def baseline_total_spares(li: int, rates: dict | None = None) -> int:
    rates = rates or expected_removal_rates()
    lam = sum(v for (b, k), v in rates.items() if k == li)
    return max(1, int(round(0.9 * lam * pipeline_days(li))))


def split_stock(total: int, base_rates: dict[str, float], ed_share: float) -> dict[str, int]:
    ed = int(round(total * ed_share))
    rest = total - ed
    out = {"ED": ed}
    tot_rate = sum(base_rates.values()) or 1.0
    shares = {b: rest * r / tot_rate for b, r in base_rates.items()}
    floor = {b: int(v) for b, v in shares.items()}
    left = rest - sum(floor.values())
    for b in sorted(shares, key=lambda b: shares[b] - floor[b], reverse=True)[:left]:
        floor[b] += 1
    out.update(floor)
    return out
