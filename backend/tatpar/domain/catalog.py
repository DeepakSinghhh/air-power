"""Notional fleet catalogue: bases, squadrons, aircraft types, checks and LRUs.

Every number here is NOTIONAL. Bases use public coordinates; squadron codes, tail
numbers and reliability parameters are invented for demonstration and are not IAF data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import gamma


@dataclass(frozen=True)
class Base:
    id: str
    name: str
    lat: float
    lon: float
    elevation_m: float
    tmax_annual_c: float     # climatological mean daily max temperature (approx. IMD normals)
    rh_annual_pct: float     # climatological mean relative humidity (approx. IMD normals)
    coastal: float           # 0..1 salt-air exposure
    climate: str


BASES: dict[str, Base] = {
    b.id: b
    for b in [
        Base("jodhpur", "Jodhpur", 26.25, 73.05, 217, 33.5, 45, 0.0, "Hot desert, dust storms"),
        Base("pune", "Pune", 18.58, 73.92, 592, 31.0, 58, 0.0, "Semi-arid plateau"),
        Base("tezpur", "Tezpur", 26.71, 92.78, 79, 29.5, 80, 0.0, "Humid sub-tropical, heavy monsoon"),
        Base("thanjavur", "Thanjavur", 10.72, 79.10, 77, 33.0, 72, 0.6, "Hot humid coastal"),
        Base("leh", "Leh", 34.14, 77.55, 3256, 13.0, 35, 0.0, "High-altitude cold desert"),
    ]
}


@dataclass(frozen=True)
class CheckType:
    id: str
    interval_fh: float
    duration_days: int
    needs_bay: bool
    at_depot: bool = False


@dataclass(frozen=True)
class AircraftType:
    id: str
    label: str
    engines: int
    sortie_hours: float
    max_sorties_per_day: int
    checks: tuple[CheckType, ...]

    def check(self, cid: str) -> CheckType:
        return next(c for c in self.checks if c.id == cid)


AIRCRAFT_TYPES: dict[str, AircraftType] = {
    "HF": AircraftType(
        "HF", "Heavy fighter (Su-30MKI-class, notional)", 2, 1.5, 2,
        (
            CheckType("minor", 50, 1, False),
            CheckType("phase", 200, 10, True),
            CheckType("overhaul", 1000, 45, False, at_depot=True),
        ),
    ),
    "LF": AircraftType(
        "LF", "Light fighter (Tejas-class, notional)", 1, 1.0, 2,
        (
            CheckType("minor", 50, 1, False),
            CheckType("phase", 150, 8, True),
            CheckType("overhaul", 800, 40, False, at_depot=True),
        ),
    ),
}


@dataclass(frozen=True)
class Squadron:
    id: str
    name: str
    base: str
    type: str
    n_aircraft: int
    bays: int
    crews: int                      # concurrent unscheduled jobs
    sorties_weekday: int
    sorties_saturday: int
    mission_mix: dict[str, float] = field(default_factory=dict)


MISSIONS = {  # mission -> g-severity factor (1.0 = training baseline)
    "training": 1.0,
    "air_combat": 1.5,
    "strike": 1.25,
    "recce_nav": 0.85,
}

SQUADRONS: dict[str, Squadron] = {
    s.id: s
    for s in [
        Squadron("SQN-A", "Sqn A (HF) — Jodhpur", "jodhpur", "HF", 16, 1, 4, 10, 4,
                 {"training": 0.45, "air_combat": 0.25, "strike": 0.2, "recce_nav": 0.1}),
        Squadron("SQN-B", "Sqn B (HF) — Pune", "pune", "HF", 16, 1, 4, 10, 4,
                 {"training": 0.55, "air_combat": 0.2, "strike": 0.15, "recce_nav": 0.1}),
        Squadron("SQN-C", "Sqn C (HF) — Tezpur", "tezpur", "HF", 16, 1, 4, 10, 4,
                 {"training": 0.5, "air_combat": 0.2, "strike": 0.2, "recce_nav": 0.1}),
        Squadron("SQN-D", "Sqn D (LF) — Thanjavur", "thanjavur", "LF", 16, 1, 4, 12, 5,
                 {"training": 0.5, "air_combat": 0.3, "strike": 0.1, "recce_nav": 0.1}),
    ]
}

STOCK_POINTS = [s.base for s in SQUADRONS.values()] + ["ED"]  # base stores + central Equipment Depot
AGENCIES = {"BRD": "Base Repair Depot (notional)", "HAL": "OEM / HAL division (notional)"}
TRANSIT_DAYS = 3          # ED -> base, base -> base (air courier)
DEPOT_SLOTS = 8           # concurrent aircraft overhauls at the BRD


@dataclass(frozen=True)
class LRUType:
    id: str
    name: str
    ata: int
    system: str
    qpa: dict[str, int]                 # per aircraft type
    beta: float                         # Weibull shape
    eta_fh: float                       # Weibull scale at reference severity (flight hours)
    sens: dict[str, float]              # AFT time-acceleration coefficients
    nff_frac: float                     # share of removals that are No-Fault-Found
    agency: str
    tat_days: float                     # mean repair turnaround
    cost_lakh: float
    lead_days: int                      # new procurement lead time
    source: str                         # indigenous | import
    rogue_prone: bool = False
    is_engine: bool = False

    @property
    def mean_life_fh(self) -> float:
        return self.eta_fh * gamma(1 + 1 / self.beta)


def _s(dust=0.0, heat=0.0, hum=0.0, alt=0.0, salt=0.0, g=0.0) -> dict[str, float]:
    return {"dust": dust, "heat": heat, "hum": hum, "alt": alt, "salt": salt, "g": g}


ATA_CHAPTERS = {
    21: "Air conditioning", 23: "Communications", 24: "Electrical power", 25: "Equipment / escape",
    27: "Flight controls", 28: "Fuel", 29: "Hydraulic power", 31: "Indicating / recording",
    32: "Landing gear", 34: "Navigation & radar", 36: "Pneumatic", 49: "Gas turbine starter",
    72: "Engine", 73: "Engine fuel & control", 77: "Engine indicating", 79: "Engine oil",
}

LRU_TYPES: dict[str, LRUType] = {
    l.id: l
    for l in [
        LRUType("ECS_TURB", "ECS cooling turbine", 21, "Air conditioning", {"HF": 1, "LF": 1}, 1.6, 900,
                _s(dust=.35, heat=.25, hum=.05, salt=.05, g=.05), .15, "BRD", 30, 18, 180, "import"),
        LRUType("CPC", "Cabin pressure controller", 21, "Air conditioning", {"HF": 1, "LF": 1}, 1.3, 1800,
                _s(dust=.05, heat=.10, hum=.15, alt=.20, salt=.05), .35, "BRD", 25, 6, 120, "indigenous"),
        LRUType("VUHF", "V/UHF radio", 23, "Communications", {"HF": 2, "LF": 1}, 1.0, 3800,
                _s(heat=.10, hum=.25, salt=.10), .50, "BRD", 15, 3, 60, "indigenous"),
        LRUType("GEN", "AC generator (IDG)", 24, "Electrical power", {"HF": 2, "LF": 1}, 1.5, 1400,
                _s(dust=.15, heat=.25, hum=.05, alt=.05, salt=.05, g=.10), .20, "HAL", 45, 25, 240, "import"),
        LRUType("TRU", "Transformer rectifier unit", 24, "Electrical power", {"HF": 2, "LF": 1}, 1.2, 2200,
                _s(dust=.05, heat=.20, hum=.25, salt=.15), .40, "BRD", 20, 4, 90, "indigenous", rogue_prone=True),
        LRUType("SEAT_SEQ", "Ejection seat sequencer", 25, "Equipment / escape", {"HF": 2, "LF": 1}, 1.4, 4000,
                _s(dust=.05, heat=.10, hum=.20, alt=.05, salt=.15, g=.05), .20, "BRD", 30, 6, 180, "import"),
        LRUType("FCC", "Flight control computer", 27, "Flight controls", {"HF": 2, "LF": 2}, 1.1, 3000,
                _s(heat=.15, hum=.20, alt=.05, salt=.10, g=.05), .55, "HAL", 60, 60, 300, "import", rogue_prone=True),
        LRUType("ACT", "Control surface actuator", 27, "Flight controls", {"HF": 4, "LF": 3}, 1.8, 2000,
                _s(dust=.10, heat=.05, hum=.05, alt=.05, salt=.10, g=.35), .10, "HAL", 50, 30, 270, "import"),
        LRUType("FBP", "Fuel boost pump", 28, "Fuel", {"HF": 2, "LF": 1}, 1.5, 1600,
                _s(dust=.10, heat=.20, hum=.05, alt=.05, g=.05), .15, "BRD", 25, 5, 120, "indigenous"),
        LRUType("FQP", "Fuel quantity probe", 28, "Fuel", {"HF": 4, "LF": 3}, 1.0, 4000,
                _s(heat=.05, hum=.30, salt=.20), .45, "BRD", 15, 1.5, 60, "indigenous"),
        LRUType("HYD_PUMP", "Engine-driven hydraulic pump", 29, "Hydraulic power", {"HF": 2, "LF": 1}, 1.7, 1300,
                _s(dust=.20, heat=.20, alt=.05, g=.20), .10, "BRD", 35, 12, 200, "import"),
        LRUType("HYD_ACC", "Hydraulic accumulator", 29, "Hydraulic power", {"HF": 2, "LF": 1}, 1.4, 2500,
                _s(dust=.05, heat=.15, hum=.05, alt=.15, salt=.05, g=.10), .15, "BRD", 20, 3, 90, "indigenous"),
        LRUType("MFD", "Multi-function display", 31, "Indicating / recording", {"HF": 3, "LF": 2}, 1.1, 3500,
                _s(dust=.05, heat=.20, hum=.15, salt=.05, g=.05), .40, "BRD", 30, 10, 150, "indigenous", rogue_prone=True),
        LRUType("BRAKE", "Main wheel brake unit", 32, "Landing gear", {"HF": 2, "LF": 2}, 2.2, 600,
                _s(dust=.25, heat=.25, alt=.10, salt=.05, g=.05), .05, "BRD", 15, 4, 90, "indigenous"),
        LRUType("NWS", "Nose-wheel steering actuator", 32, "Landing gear", {"HF": 1, "LF": 1}, 1.5, 1800,
                _s(dust=.15, heat=.05, hum=.10, alt=.05, salt=.15), .20, "BRD", 25, 5, 120, "indigenous"),
        LRUType("INS", "INS/GPS unit", 34, "Navigation & radar", {"HF": 1, "LF": 1}, 1.1, 2600,
                _s(heat=.15, hum=.15, alt=.10, salt=.05, g=.15), .50, "HAL", 60, 45, 300, "import", rogue_prone=True),
        LRUType("ADC", "Air data computer", 34, "Navigation & radar", {"HF": 2, "LF": 1}, 1.2, 3200,
                _s(dust=.10, heat=.10, hum=.15, alt=.15, salt=.10), .45, "HAL", 45, 15, 240, "import", rogue_prone=True),
        LRUType("RADAR", "Fire-control radar transmitter", 34, "Navigation & radar", {"HF": 1, "LF": 1}, 1.3, 1100,
                _s(dust=.05, heat=.35, hum=.20, alt=.05, salt=.10, g=.15), .35, "HAL", 75, 120, 360, "import", rogue_prone=True),
        LRUType("RALT", "Radar altimeter", 34, "Navigation & radar", {"HF": 1, "LF": 1}, 1.1, 3500,
                _s(heat=.10, hum=.20, salt=.10), .45, "BRD", 20, 3, 90, "indigenous"),
        LRUType("BAV", "Bleed-air shut-off valve", 36, "Pneumatic", {"HF": 2, "LF": 1}, 1.6, 1500,
                _s(dust=.30, heat=.20, hum=.05, alt=.05, salt=.10), .15, "BRD", 25, 4, 120, "indigenous"),
        LRUType("GTS", "Gas turbine starter", 49, "Gas turbine starter", {"HF": 1, "LF": 1}, 1.5, 1000,
                _s(dust=.30, heat=.20, alt=.25), .15, "HAL", 45, 20, 240, "import"),
        LRUType("FCU", "Engine fuel control unit", 73, "Engine fuel & control", {"HF": 2, "LF": 1}, 1.3, 2400,
                _s(dust=.10, heat=.20, hum=.10, alt=.15, salt=.05, g=.05), .30, "HAL", 60, 35, 300, "import", rogue_prone=True),
        LRUType("EVM", "Engine vibration monitor", 77, "Engine indicating", {"HF": 2, "LF": 1}, 1.0, 4000,
                _s(heat=.10, hum=.15, salt=.05, g=.05), .50, "BRD", 15, 2, 60, "indigenous"),
        LRUType("OPT", "Oil pressure transmitter", 79, "Engine oil", {"HF": 2, "LF": 1}, 1.2, 3000,
                _s(dust=.05, heat=.15, hum=.10, salt=.05), .40, "BRD", 15, 1, 45, "indigenous"),
        # Engines: life comes from mapped NASA C-MAPSS run-to-failure trajectories, not a Weibull draw.
        LRUType("ENGINE", "Turbofan engine module", 72, "Engine", {"HF": 2, "LF": 1}, 3.0, 650,
                _s(dust=.25, heat=.15, alt=.10, g=.10), .03, "HAL", 75, 900, 540, "import", is_engine=True),
    ]
}


def tail_numbers() -> list[tuple[str, str]]:
    """Return (tail, squadron_id) for the whole notional fleet."""
    out = []
    for k, sq in enumerate(SQUADRONS.values(), start=1):
        for i in range(1, sq.n_aircraft + 1):
            out.append((f"{sq.type}-{k}{i:02d}", sq.id))
    return out
