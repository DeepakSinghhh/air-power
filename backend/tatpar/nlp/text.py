"""Logbook text normalisation: abbreviations, Hinglish phrases, serial-number scrubbing."""
from __future__ import annotations

import re

from ..data.maintnet import load_abbreviations

ABBREV = {
    "hyd": "hydraulic", "pr": "pressure", "press": "pressure", "lt": "light", "lts": "lights", "sys": "system",
    "u/s": "unserviceable", "gnd": "ground", "flt": "flight", "eng": "engine", "engs": "engines", "chk": "check",
    "r/r": "removed and replaced", "r&r": "removed and replaced", "a/c": "aircraft", "inop": "inoperative",
    "ops": "operational", "satis": "satisfactory", "ind": "indication", "temp": "temperature", "acc": "accumulator",
    "gen": "generator", "tx": "transmit", "rx": "receive", "fcs": "flight control system",
    "flcs": "flight control system", "fcc": "flight control computer", "ecs": "environmental control system",
    "cpc": "cabin pressure controller", "adc": "air data computer", "ins": "inertial navigation system",
    "mfd": "multi function display", "rad": "radar", "radalt": "radar altimeter", "gts": "gas turbine starter",
    "egt": "exhaust gas temperature", "vib": "vibration", "evm": "engine vibration monitor", "fcu": "fuel control unit",
    "tru": "transformer rectifier unit", "nws": "nose wheel steering", "lh": "left", "rh": "right",
    "fwd": "forward", "aft": "aft", "qty": "quantity", "fqis": "fuel quantity indication system",
    "bit": "built in test", "bite": "built in test", "txr": "transmitter", "fl": "flight level",
    "ias": "indicated airspeed", "alt": "altitude", "eicas": "engine indication", "sn": "serial",
}
HINGLISH = {
    "ke dauran": "during", "mein": "in", "par": "on", "se awaaz aa rahi hai": "is noisy", "awaaz": "noise",
    "jal rahi hai": "is on", "kharab": "faulty", "nahi": "not", "chal raha": "working", "band": "off",
    "baar baar": "repeatedly", "kabhi kabhi": "intermittent", "theek": "ok",
}
_SERIAL = re.compile(r"\b[a-z]{2,4}-\d{3,6}\b|\bs/n\s*\S+|\b\d{4,}\b", re.I)
_TOKEN = re.compile(r"[a-z0-9/&]+")


def normalise(text: str) -> str:
    t = str(text).lower()
    t = _SERIAL.sub(" ", t)
    for hi, en in HINGLISH.items():
        t = t.replace(hi, en)
    abbr = {**load_abbreviations(), **ABBREV}
    out = []
    for tok in _TOKEN.findall(t):
        out.append(abbr.get(tok, tok))
    return " ".join(out)
