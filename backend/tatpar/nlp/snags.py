"""Snag intelligence: ATA-chapter auto-coding, similar-case retrieval and fix-effectiveness.

* ATA coder — TF-IDF (word + character n-grams) + logistic regression, trained on fleet snags
  (true ATA from the technical record) plus MaintNet real logbook problems weakly labelled by
  keyword rules. Character n-grams make it robust to abbreviations, typos and Hinglish.
* Retrieval — cosine similarity over normalised text of fleet history and MaintNet records,
  returning what was done and (for fleet cases) whether the defect came back within 30 days.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import FeatureUnion, Pipeline

from ..config import ARTIFACTS_DIR
from ..data.maintnet import load_logbook
from ..datagen import history
from ..domain.catalog import ATA_CHAPTERS
from .text import normalise

MODEL_PATH = ARTIFACTS_DIR / "snag_nlp.joblib"

ATA_EXTRA = {22: "Auto flight", 26: "Fire protection", 30: "Ice & rain", 33: "Lights", 35: "Oxygen", 37: "Vacuum",
             52: "Doors / canopy", 56: "Windows", 61: "Propellers", 71: "Power plant", 74: "Ignition", 80: "Starting"}
ATA_NAMES = {**ATA_EXTRA, **ATA_CHAPTERS}

# ordered keyword rules (most specific first) for weak labelling of MaintNet problems
RULES: list[tuple[int, str]] = [
    (73, r"fuel servo|injector|mixture|carb|fuel control"),
    (74, r"\bmag(neto)?s?\b|ignition|spark plug|\bplugs?\b|fouled"),
    (80, r"starter|wont start|won't start|start(ing)? problem"),
    (77, r"tach|\begt\b|\bcht\b|engine gauge|vibration"),
    (79, r"\boil\b|oil press|oil temp"),
    (61, r"\bprop(eller)?\b|spinner"),
    (24, r"alternator|\balt\b|battery|\bbus\b|voltage|\bamps?\b|ammeter|circuit breaker|\bc/?b\b|electrical|generator"),
    (23, r"radio|\bcomm?\b|com ?[12]|intercom|headset|\bmic\b|\bptt\b|squelch|audio panel"),
    (34, r"\bgps\b|\bnav\b|\bvor\b|\bils\b|transponder|altimeter|airspeed|pitot|static|compass|attitude|\bgyro|\bhsi\b|\bdg\b|garmin"),
    (22, r"auto ?pilot"),
    (33, r"\blight|beacon|strobe|bulb|lamp"),
    (32, r"\btire|\btyre|wheel|brake|\bgear\b|strut|nose ?wheel|shimmy|steering"),
    (27, r"aileron|elevator|rudder|\bflaps?\b|\btrim\b|control (yoke|stick|cable)|yoke"),
    (28, r"\bfuel\b|tank|\bsump|fuel cap|fuel gauge|fuel qty"),
    (21, r"heater|cabin heat|defrost|\bvent\b|air cond|\becs\b"),
    (37, r"vacuum|suction"),
    (25, r"\bseat|belt|harness|carpet|interior"),
    (52, r"\bdoor|canopy|latch"),
    (56, r"window|windshield|windscreen"),
    (71, r"engine|cylinder|\bcyl\b|compression|rough|power loss|lost power|\brpm\b|idle|cowl|baffle|exhaust"),
]
_RULES = [(a, re.compile(p, re.I)) for a, p in RULES]


def weak_ata(text: str) -> int | None:
    for ata, rx in _RULES:
        if rx.search(text):
            return ata
    return None


def _vectorizer() -> FeatureUnion:
    return FeatureUnion([
        ("w", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)),
    ])


@dataclass
class SnagNLP:
    ata_model: Pipeline | None = None
    retr_vec: TfidfVectorizer | None = None
    corpus: pd.DataFrame | None = None
    corpus_X: object = None
    metrics: dict = field(default_factory=dict)

    # ------------------------------------------------------------ training
    def fit(self, verbose: bool = True) -> "SnagNLP":
        snags = history.load("snags")
        fleet = pd.DataFrame({"text": snags["text"], "ata": snags["ata"].astype(int), "src": "fleet",
                              "group": snags["tail"]})
        mn = load_logbook()
        mn = mn.assign(ata=mn["problem"].map(weak_ata)).dropna(subset=["ata"])
        mnet = pd.DataFrame({"text": mn["problem"], "ata": mn["ata"].astype(int), "src": "maintnet",
                             "group": "mn" + (mn.index // 20).astype(str)})
        data = pd.concat([fleet, mnet], ignore_index=True)
        data["norm"] = data["text"].map(normalise)
        gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=0)
        tr, te = next(gss.split(data, data["ata"], groups=data["group"]))
        model = Pipeline([("vec", _vectorizer()), ("clf", LogisticRegression(max_iter=2000, C=8.0))])
        model.fit(data["norm"].iloc[tr], data["ata"].iloc[tr])
        pred = model.predict(data["norm"].iloc[te])
        test = data.iloc[te].assign(pred=pred)
        m = {}
        for src, g in list(test.groupby("src")) + [("all", test)]:
            m[src] = {"n": int(len(g)), "accuracy": float(accuracy_score(g["ata"], g["pred"])),
                      "macro_f1": float(f1_score(g["ata"], g["pred"], average="macro"))}
        # Hinglish robustness: fleet snags written partly in Hinglish
        hing = test[(test["src"] == "fleet") & test["text"].str.contains(r"KE DAURAN|MEIN|AWAAZ|JAL RAHI|PAR\b")]
        if len(hing):
            m["fleet_hinglish"] = {"n": int(len(hing)), "accuracy": float(accuracy_score(hing["ata"], hing["pred"]))}
        m["maintnet_weak_label_coverage"] = float(len(mn) / max(1, len(load_logbook())))
        self.metrics = m
        model.fit(data["norm"], data["ata"])
        self.ata_model = model
        self._build_retrieval(snags)
        if verbose:
            print("snag NLP:", {k: v for k, v in m.items()})
        return self

    def _build_retrieval(self, snags: pd.DataFrame) -> None:
        snags = snags.sort_values("day")
        repeat = []
        for (tail, ata), g in snags.groupby(["tail", "ata"]):
            days = g["day"].to_numpy()
            for i, idx in enumerate(g.index):
                repeat.append((idx, bool(i + 1 < len(days) and days[i + 1] - days[i] <= 30)))
        rep = pd.Series(dict(repeat))
        fleet = pd.DataFrame({
            "source": "fleet", "ref": snags["snag_id"], "date": snags["date"].astype(str), "tail": snags["tail"],
            "ata": snags["ata"].astype(int), "problem": snags["text"], "action": snags["action"],
            "finding": snags["finding"], "repeat_30d": snags.index.map(rep),
        })
        mn = load_logbook()
        mnet = pd.DataFrame({
            "source": "maintnet", "ref": "MN-" + mn["ident"].astype(str), "date": "", "tail": "",
            "ata": mn["problem"].map(weak_ata).fillna(0).astype(int), "problem": mn["problem"],
            "action": mn["action"], "finding": "", "repeat_30d": None,
        })
        self.corpus = pd.concat([fleet, mnet], ignore_index=True)
        self.retr_vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        self.corpus_X = self.retr_vec.fit_transform(self.corpus["problem"].map(normalise))

    # ------------------------------------------------------------ inference
    def classify(self, text: str, k: int = 3) -> list[dict]:
        proba = self.ata_model.predict_proba([normalise(text)])[0]
        classes = self.ata_model.classes_
        top = np.argsort(proba)[::-1][:k]
        return [{"ata": int(classes[i]), "name": ATA_NAMES.get(int(classes[i]), "Other"), "p": float(proba[i])} for i in top]

    def similar(self, text: str, k: int = 8, source: str | None = None) -> list[dict]:
        q = self.retr_vec.transform([normalise(text)])
        sims = (self.corpus_X @ q.T).toarray().ravel()
        df = self.corpus.assign(similarity=sims)
        if source:
            df = df[df["source"] == source]
        df = df[df["similarity"] > 0.05].sort_values("similarity", ascending=False)
        df = df.groupby("problem", sort=False).head(2).head(k)   # variety over identical log wording
        return df.replace({np.nan: None}).to_dict("records")

    def fix_effectiveness(self, ata: int) -> list[dict]:
        """Fleet actions for an ATA chapter ranked by repeat-defect rate within 30 days."""
        f = self.corpus[(self.corpus["source"] == "fleet") & (self.corpus["ata"] == ata)].copy()
        if f.empty:
            return []
        f["action_kind"] = np.select(
            [f["finding"] == "NFF", f["finding"] == "RETEST", f["action"].str.contains("REPLACED|FITTED", case=False)],
            ["Removed — shop found no fault", "Ground re-test, no removal", "Replaced unserviceable unit"], "Other")
        g = f.groupby("action_kind").agg(cases=("ref", "size"), repeat_rate=("repeat_30d", "mean")).reset_index()
        return g.sort_values("repeat_rate").to_dict("records")

    def save(self, path=MODEL_PATH) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path=MODEL_PATH) -> "SnagNLP":
        return joblib.load(path)
