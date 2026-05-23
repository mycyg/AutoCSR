"""Generate fake ADaM-style sample data for the 5 M20 domain templates.

Run from repo root:
    python scripts/generate_sample_data.py

Output: data/sample_projects/<domain>/{ADSL,ADAE,ADEFF}.parquet

All data is synthesised with seeded NumPy — zero real patient records. Column
naming follows CDISC ADaM conventions so the analyst agent can recognise the
shapes without bespoke schema hints. Domains:

  - oncology         : ADSL + ADAE + ADEFF (RECIST best response + PFS time)
  - rare_disease     : ADSL + ADAE + ADEFF (rare-disease biomarker + small N)
  - vaccine          : ADSL + ADAE + ADEFF (GMT pre/post + SCR)
  - pediatric        : ADSL + ADAE + ADEFF (age strata + growth z-scores)
  - cardiovascular   : ADSL + ADAE + ADEFF (MACE time-to-event)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample_projects"


def _seed(domain: str) -> np.random.Generator:
    """Deterministic per-domain seed so re-runs produce identical files."""
    return np.random.default_rng(hash(domain) & 0xFFFF_FFFF)


def _adsl_skeleton(rng: np.random.Generator, n: int, *, arms: list[str],
                    age_low: int = 18, age_high: int = 75) -> pd.DataFrame:
    """Common ADSL columns used by every domain."""
    usubjid = [f"DEMO-{i + 1001:04d}" for i in range(n)]
    arm = rng.choice(arms, size=n).tolist()
    age = rng.integers(age_low, age_high, size=n)
    sex = rng.choice(["M", "F"], size=n).tolist()
    race = rng.choice(["WHITE", "ASIAN", "BLACK", "OTHER"], size=n,
                       p=[0.45, 0.35, 0.15, 0.05]).tolist()
    weight = np.round(rng.normal(70, 12, size=n), 1)
    height = np.round(rng.normal(168, 9, size=n), 1)
    bmi = np.round(weight / ((height / 100) ** 2), 1)
    return pd.DataFrame({
        "USUBJID": usubjid,
        "ARM": arm,
        "TRT01P": arm,           # planned treatment
        "TRT01A": arm,           # actual treatment
        "AGE": age,
        "AGEU": ["YEARS"] * n,
        "SEX": sex,
        "RACE": race,
        "WEIGHT": weight,
        "HEIGHT": height,
        "BMI": bmi,
        "SAFFL": ["Y"] * n,
        "ITTFL": ["Y"] * n,
    })


def _adae_skeleton(rng: np.random.Generator, adsl: pd.DataFrame,
                    *, soc_pool: list[str], pt_pool: list[str],
                    rate: float = 1.4) -> pd.DataFrame:
    """Common ADAE columns. ``rate`` ≈ mean AEs per subject (Poisson)."""
    n_subj = len(adsl)
    n_per_subj = rng.poisson(rate, size=n_subj)
    rows: list[dict] = []
    for i, k in enumerate(n_per_subj):
        for j in range(int(k)):
            soc = rng.choice(soc_pool)
            pt = rng.choice(pt_pool)
            sev = rng.choice(["MILD", "MODERATE", "SEVERE"],
                              p=[0.55, 0.30, 0.15])
            rel = rng.choice(["NOT RELATED", "POSSIBLY RELATED",
                               "PROBABLY RELATED", "RELATED"],
                              p=[0.40, 0.30, 0.20, 0.10])
            ser = "Y" if (sev == "SEVERE" and rng.random() < 0.4) else "N"
            day = int(rng.integers(1, 180))
            rows.append({
                "USUBJID": adsl.iloc[i]["USUBJID"],
                "ARM": adsl.iloc[i]["ARM"],
                "AESEQ": j + 1,
                "AESOC": soc,
                "AETERM": pt,
                "AEDECOD": pt,
                "AESEV": sev,
                "AEREL": rel,
                "AESER": ser,
                "ASTDY": day,
                "AENDY": day + int(rng.integers(1, 30)),
                "AEACN": rng.choice(["DOSE NOT CHANGED", "DOSE REDUCED",
                                       "DRUG INTERRUPTED", "DRUG WITHDRAWN"],
                                      p=[0.65, 0.15, 0.12, 0.08]),
            })
    if not rows:
        # ensure at least one row for tiny N
        rows.append({
            "USUBJID": adsl.iloc[0]["USUBJID"], "ARM": adsl.iloc[0]["ARM"],
            "AESEQ": 1, "AESOC": soc_pool[0], "AETERM": pt_pool[0],
            "AEDECOD": pt_pool[0], "AESEV": "MILD", "AEREL": "NOT RELATED",
            "AESER": "N", "ASTDY": 5, "AENDY": 7,
            "AEACN": "DOSE NOT CHANGED",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Domain builders
# ---------------------------------------------------------------------------

def build_oncology() -> dict[str, pd.DataFrame]:
    rng = _seed("oncology")
    adsl = _adsl_skeleton(rng, 50, arms=["Drug A", "Standard Care"],
                            age_low=30, age_high=78)
    # Tumor-specific extras
    adsl["ECOGBL"] = rng.choice([0, 1], size=len(adsl), p=[0.55, 0.45])
    adsl["PDL1"] = rng.choice(["<1%", "1-49%", ">=50%"], size=len(adsl),
                                p=[0.30, 0.35, 0.35])
    adsl["EGFRMUT"] = rng.choice(["WILD-TYPE", "MUTANT"], size=len(adsl),
                                   p=[0.70, 0.30])
    adsl["TUMORTYPE"] = rng.choice(["NSCLC", "MELANOMA", "BREAST",
                                      "COLORECTAL"], size=len(adsl),
                                     p=[0.45, 0.20, 0.20, 0.15])

    adae = _adae_skeleton(rng, adsl,
        soc_pool=["GASTROINTESTINAL DISORDERS",
                   "GENERAL DISORDERS",
                   "BLOOD AND LYMPHATIC SYSTEM DISORDERS",
                   "RESPIRATORY THORACIC DISORDERS",
                   "IMMUNE SYSTEM DISORDERS",
                   "SKIN AND SUBCUTANEOUS TISSUE DISORDERS"],
        pt_pool=["Nausea", "Fatigue", "Diarrhoea", "Neutropenia",
                  "Pneumonitis", "Rash", "Pruritus", "Hypothyroidism",
                  "Anaemia", "Vomiting", "Decreased appetite", "Cough"],
        rate=2.5,
    )

    # ADEFF — best overall response per RECIST + PFS time
    n = len(adsl)
    best_resp = rng.choice(["CR", "PR", "SD", "PD"], size=n,
                            p=[0.10, 0.35, 0.30, 0.25])
    pfs_days = rng.integers(30, 540, size=n)
    pfs_event = rng.choice([0, 1], size=n, p=[0.30, 0.70])    # 1=event, 0=censored
    os_days = pfs_days + rng.integers(0, 360, size=n)
    os_event = rng.choice([0, 1], size=n, p=[0.50, 0.50])
    adeff = pd.DataFrame({
        "USUBJID": adsl["USUBJID"],
        "ARM": adsl["ARM"],
        "PARAMCD": ["BESTRESP"] * n,
        "PARAM": ["Best Overall Response per RECIST 1.1"] * n,
        "AVALC": best_resp,
        "AVAL": [{"CR": 4, "PR": 3, "SD": 2, "PD": 1}[r] for r in best_resp],
        "PFSDY": pfs_days,
        "PFSCNSR": 1 - pfs_event,   # CDISC convention: 1=censor
        "OSDY": os_days,
        "OSCNSR": 1 - os_event,
    })
    return {"ADSL": adsl, "ADAE": adae, "ADEFF": adeff}


def build_rare_disease() -> dict[str, pd.DataFrame]:
    rng = _seed("rare_disease")
    # Very small N typical of rare-disease trials
    adsl = _adsl_skeleton(rng, 25, arms=["Active", "Historical Control"],
                            age_low=2, age_high=55)
    adsl["GENMUT"] = rng.choice(["GENE-A_PATHOGENIC", "GENE-A_VUS",
                                   "GENE-B_PATHOGENIC", "UNKNOWN"],
                                  size=len(adsl), p=[0.55, 0.10, 0.25, 0.10])
    adsl["DISSEV"] = rng.choice(["MILD", "MODERATE", "SEVERE"],
                                  size=len(adsl), p=[0.20, 0.50, 0.30])
    adsl["NHSTUDY"] = rng.choice(["Y", "N"], size=len(adsl), p=[0.45, 0.55])

    adae = _adae_skeleton(rng, adsl,
        soc_pool=["NERVOUS SYSTEM DISORDERS",
                   "METABOLISM AND NUTRITION DISORDERS",
                   "GENERAL DISORDERS",
                   "INVESTIGATIONS",
                   "GASTROINTESTINAL DISORDERS"],
        pt_pool=["Headache", "Fatigue", "Hypoglycaemia", "Hyperphosphataemia",
                  "Liver function abnormal", "Nausea", "Seizure", "Tremor"],
        rate=1.4,
    )

    # ADEFF — biomarker level + response
    n = len(adsl)
    base = rng.normal(150, 40, size=n)        # disease biomarker baseline
    chg = rng.normal(-35, 25, size=n)         # mean reduction
    adeff = pd.DataFrame({
        "USUBJID": adsl["USUBJID"],
        "ARM": adsl["ARM"],
        "PARAMCD": ["BIOMARKER"] * n,
        "PARAM": ["Disease-specific biomarker (units/mL)"] * n,
        "AVISIT": ["Week 24"] * n,
        "AVISITN": [24] * n,
        "BASE": np.round(base, 1),
        "AVAL": np.round(base + chg, 1),
        "CHG": np.round(chg, 1),
        "PCHG": np.round(chg / base * 100, 1),
        "RESPFL": ["Y" if c < -20 else "N" for c in chg],
    })
    return {"ADSL": adsl, "ADAE": adae, "ADEFF": adeff}


def build_vaccine() -> dict[str, pd.DataFrame]:
    rng = _seed("vaccine")
    adsl = _adsl_skeleton(rng, 50, arms=["Vaccine", "Placebo"],
                            age_low=18, age_high=70)
    adsl["BLSEROSTAT"] = rng.choice(["NEGATIVE", "POSITIVE"], size=len(adsl),
                                       p=[0.85, 0.15])
    adsl["REGION"] = rng.choice(["North America", "Europe", "Asia"],
                                  size=len(adsl), p=[0.4, 0.3, 0.3])

    adae = _adae_skeleton(rng, adsl,
        soc_pool=["GENERAL DISORDERS",
                   "MUSCULOSKELETAL DISORDERS",
                   "NERVOUS SYSTEM DISORDERS",
                   "GASTROINTESTINAL DISORDERS"],
        pt_pool=["Injection site pain", "Fatigue", "Headache", "Myalgia",
                  "Fever", "Chills", "Arthralgia", "Nausea", "Lymphadenopathy"],
        rate=2.8,
    )

    # ADEFF — GMT pre/post + SCR
    n = len(adsl)
    pre = np.round(rng.lognormal(mean=2.0, sigma=0.7, size=n), 1)
    fold_rise = np.where(
        adsl["ARM"].values == "Vaccine",
        rng.lognormal(mean=2.2, sigma=0.6, size=n),       # ~9x mean
        rng.lognormal(mean=0.1, sigma=0.3, size=n),       # ~1x mean
    )
    post = np.round(pre * fold_rise, 1)
    scr = (post / pre >= 4).astype(int)
    adeff = pd.DataFrame({
        "USUBJID": np.concatenate([adsl["USUBJID"], adsl["USUBJID"]]),
        "ARM": np.concatenate([adsl["ARM"], adsl["ARM"]]),
        "PARAMCD": ["TITER"] * (n * 2),
        "PARAM": ["Antibody Titer (IU/mL)"] * (n * 2),
        "AVISIT": ["Day 1 (Pre-vaccination)"] * n + ["Day 56 (Post-dose-2)"] * n,
        "AVISITN": [1] * n + [56] * n,
        "AVAL": np.concatenate([pre, post]),
        "LOGAVAL": np.round(np.log10(np.concatenate([pre, post])), 3),
        "SCRFL": ["N"] * n + ["Y" if s else "N" for s in scr],
    })
    return {"ADSL": adsl, "ADAE": adae, "ADEFF": adeff}


def build_pediatric() -> dict[str, pd.DataFrame]:
    rng = _seed("pediatric")
    n = 40
    usubjid = [f"DEMO-{i + 1001:04d}" for i in range(n)]
    arm = rng.choice(["Drug X 5mg/kg", "Drug X 10mg/kg", "Placebo"],
                       size=n, p=[0.4, 0.4, 0.2]).tolist()
    age_months = rng.integers(1, 17 * 12, size=n)
    age_years = (age_months / 12).round(1)
    age_stratum = []
    for m in age_months:
        if m < 1:
            age_stratum.append("Term newborn (0-27d)")
        elif m < 24:
            age_stratum.append("Infant (28d-23m)")
        elif m < 12 * 12:
            age_stratum.append("Child (2-11y)")
        else:
            age_stratum.append("Adolescent (12-17y)")
    weight = np.round(rng.uniform(3, 70, size=n), 1)
    height = np.round(rng.uniform(50, 175, size=n), 1)
    bmi_z = np.round(rng.normal(0, 1, size=n), 2)
    height_z = np.round(rng.normal(0, 1, size=n), 2)
    sex = rng.choice(["M", "F"], size=n).tolist()
    adsl = pd.DataFrame({
        "USUBJID": usubjid,
        "ARM": arm, "TRT01P": arm, "TRT01A": arm,
        "AGE": age_years,
        "AGEU": ["YEARS"] * n,
        "AGEMOS": age_months,
        "AGESTRAT": age_stratum,
        "SEX": sex,
        "WEIGHT": weight,
        "HEIGHT": height,
        "BMIZ": bmi_z,           # BMI z-score (WHO/CDC)
        "HTZ": height_z,         # Height z-score
        "TANNER": rng.choice([1, 2, 3, 4, 5], size=n,
                              p=[0.35, 0.15, 0.15, 0.15, 0.20]),
        "SAFFL": ["Y"] * n,
        "ITTFL": ["Y"] * n,
    })

    adae = _adae_skeleton(rng, adsl,
        soc_pool=["INFECTIONS AND INFESTATIONS",
                   "GASTROINTESTINAL DISORDERS",
                   "GENERAL DISORDERS",
                   "RESPIRATORY THORACIC DISORDERS",
                   "SKIN AND SUBCUTANEOUS TISSUE DISORDERS"],
        pt_pool=["Pyrexia", "Upper respiratory tract infection",
                  "Vomiting", "Diarrhoea", "Rash", "Cough",
                  "Decreased appetite", "Otitis media"],
        rate=1.8,
    )

    # ADEFF — growth z-score change over study + palatability
    base_htz = height_z
    chg_htz = np.round(rng.normal(0.0, 0.3, size=n), 2)
    palatability = rng.integers(1, 6, size=n)    # 1-5 hedonic
    adeff = pd.DataFrame({
        "USUBJID": adsl["USUBJID"],
        "ARM": adsl["ARM"],
        "AGESTRAT": adsl["AGESTRAT"],
        "PARAMCD": ["HTZSDS"] * n,
        "PARAM": ["Height-for-age z-score (WHO)"] * n,
        "AVISIT": ["Week 24"] * n,
        "AVISITN": [24] * n,
        "BASE": base_htz,
        "AVAL": np.round(base_htz + chg_htz, 2),
        "CHG": chg_htz,
        "PALATABILITY": palatability,
        "PALATABILITY_LABEL": ["Bad", "Poor", "Neutral", "Good", "Excellent"][:5][
            palatability.max() - 1] if n > 0 else "",
    })
    # Fix per-row label
    pal_map = {1: "Bad", 2: "Poor", 3: "Neutral", 4: "Good", 5: "Excellent"}
    adeff["PALATABILITY_LABEL"] = [pal_map[int(p)] for p in palatability]
    return {"ADSL": adsl, "ADAE": adae, "ADEFF": adeff}


def build_cardiovascular() -> dict[str, pd.DataFrame]:
    rng = _seed("cardiovascular")
    adsl = _adsl_skeleton(rng, 60, arms=["Drug B", "Placebo"],
                            age_low=50, age_high=85)
    adsl["PRIORMI"] = rng.choice(["Y", "N"], size=len(adsl), p=[0.55, 0.45])
    adsl["DIABETES"] = rng.choice(["Y", "N"], size=len(adsl), p=[0.40, 0.60])
    adsl["EGFRBL"] = np.round(rng.normal(70, 18, size=len(adsl)), 1).clip(20, 120)
    adsl["LVEFBL"] = np.round(rng.normal(38, 8, size=len(adsl)), 1).clip(15, 60)
    adsl["NYHACL"] = rng.choice(["I", "II", "III", "IV"], size=len(adsl),
                                  p=[0.10, 0.50, 0.35, 0.05])

    adae = _adae_skeleton(rng, adsl,
        soc_pool=["CARDIAC DISORDERS",
                   "VASCULAR DISORDERS",
                   "RENAL AND URINARY DISORDERS",
                   "GENERAL DISORDERS",
                   "METABOLISM AND NUTRITION DISORDERS"],
        pt_pool=["Hypotension", "Bradycardia", "Atrial fibrillation",
                  "Hyperkalaemia", "Renal impairment", "Syncope",
                  "Dizziness", "Cardiac failure", "Bleeding", "Stroke"],
        rate=2.0,
    )

    # ADEFF — MACE time-to-first-event + LVEF change
    n = len(adsl)
    mace_days = rng.integers(30, 720, size=n)
    mace_event = rng.choice([0, 1], size=n, p=[0.65, 0.35])    # 1=event
    mace_type = rng.choice(["CV Death", "Non-fatal MI", "Non-fatal Stroke",
                              "HF Hospitalization"], size=n,
                             p=[0.20, 0.30, 0.20, 0.30])
    base_lvef = adsl["LVEFBL"].values
    chg_lvef = rng.normal(2.0, 4.0, size=n)         # mean +2% in active arm
    adeff = pd.DataFrame({
        "USUBJID": adsl["USUBJID"],
        "ARM": adsl["ARM"],
        "PARAMCD": ["MACE"] * n,
        "PARAM": ["Time to first MACE (3-pt + HF Hospitalization)"] * n,
        "AVAL": mace_days,
        "CNSR": 1 - mace_event,
        "EVNTDESC": [t if e else "Censored" for t, e in zip(mace_type, mace_event)],
        "LVEFBASE": np.round(base_lvef, 1),
        "LVEFCHG": np.round(chg_lvef, 1),
        "LVEFAVAL": np.round(base_lvef + chg_lvef, 1),
    })
    return {"ADSL": adsl, "ADAE": adae, "ADEFF": adeff}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_BUILDERS = {
    "oncology": build_oncology,
    "rare_disease": build_rare_disease,
    "vaccine": build_vaccine,
    "pediatric": build_pediatric,
    "cardiovascular": build_cardiovascular,
}


def generate_all(out_dir: Path | None = None) -> dict[str, dict[str, Path]]:
    target = out_dir or OUT
    target.mkdir(parents=True, exist_ok=True)
    written: dict[str, dict[str, Path]] = {}
    for domain, builder in _BUILDERS.items():
        domain_dir = target / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        tables = builder()
        written[domain] = {}
        for table_name, df in tables.items():
            out_path = domain_dir / f"{table_name}.parquet"
            df.to_parquet(out_path, index=False)
            written[domain][table_name] = out_path
            print(f"  [{domain}] wrote {out_path.name}: "
                  f"{len(df)} rows x {len(df.columns)} cols")
    return written


def main() -> int:
    print(f"[sample-data] writing to {OUT}")
    written = generate_all()
    print(f"[sample-data] done — 5 domains x 3 tables = "
          f"{sum(len(v) for v in written.values())} parquet files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
