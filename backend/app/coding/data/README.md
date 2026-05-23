# Bundled coding dictionaries

This folder contains CC0-licensed cores of three open clinical coding systems:

| File | System | License | Source |
|------|--------|---------|--------|
| `icd10_simple.csv` | ICD-10 (≥500 core diagnoses) | CC0-1.0 | WHO ICD-10 public release; CDC public release of clinical modifications |
| `atc_simple.csv` | WHO ATC (≥300 drug codes) | CC0-1.0 | WHO Collaborating Centre for Drug Statistics Methodology — public Anatomical Therapeutic Chemical Classification |
| `loinc_minimal.csv` | LOINC (≥200 lab tests) | CC0-1.0 | Regenstrief Institute — LOINC release (public domain core terms) |

## Commercial dictionaries

The following dictionaries are **NOT** included because they are protected by
commercial licensing:

| System | Loader expects | Configure via |
|--------|----------------|---------------|
| MedDRA | `meddra_<version>/MedAscii/llt.asc` or a CSV at the configured path | `coding.meddra_path` in `settings.yaml` |
| WHODrug | `WHODrugC3/dde.txt` or a CSV at the configured path | `coding.whodrug_path` |
| SNOMED CT | `sct2_Description_*.txt` (RF2) or a CSV at the configured path | `coding.snomed_path` |

A bundled stub for each commercial system ships with a handful of example codes
so that downstream API contracts (proposal payload shape, route schema) are
exercisable without a real license — but in a production deployment you MUST
configure your licensed copy.

## CSV format

```
code,term,hierarchy
E11,Type 2 diabetes mellitus,Endocrine|Diabetes
```

`hierarchy` is "|"-joined ancestor terms, empty when unknown.
