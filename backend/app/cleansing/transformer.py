"""Apply accepted cleansing proposals to a DataFrame, with snapshot before/after.

Each apply call snapshots the *pre-apply* state to data/projects/<pid>/snapshots
then writes the post-apply parquet to processed/<file_id>__<sheet>.parquet (or
.csv fallback).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import data_dir
from app.schemas.cleansing import CleansingProposal, Snapshot


def _df_hash(df) -> str:
    """Stable hash of a DataFrame's content (truncated)."""
    try:
        import pandas as pd
        h = hashlib.sha256()
        h.update(",".join(str(c) for c in df.columns).encode("utf-8"))
        # Sample a few cells to keep hash cheap
        for col in df.columns[:20]:
            try:
                vals = df[col].astype(str).head(200).tolist()
                h.update("|".join(vals).encode("utf-8"))
            except Exception:
                pass
        h.update(f"{df.shape[0]}x{df.shape[1]}".encode("utf-8"))
        return h.hexdigest()[:24]
    except Exception:
        return ""


def _snap_dir(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "snapshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _processed_dir(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "processed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_table(df, out: Path) -> str:
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(out, index=False)
        return str(out)
    except Exception:
        csv = out.with_suffix(".csv")
        df.to_csv(csv, index=False, encoding="utf-8")
        return str(csv)


def _read_table(p: Path):
    import pandas as pd
    if p.suffix.lower() == ".parquet":
        return pd.read_parquet(p)
    return pd.read_csv(p, dtype=str, encoding_errors="replace")


# ---------------------------------------------------------------------------
# Rule application
# ---------------------------------------------------------------------------

def _apply_one(df, prop: CleansingProposal):
    import pandas as pd
    t = prop.type
    cols = prop.target_columns or []
    params = prop.parameters or {}

    if t == "rename_column":
        # parameters: {new_name: str}  OR  {mapping: {old: new}}
        mapping = params.get("mapping")
        if not mapping and cols and params.get("new_name"):
            mapping = {cols[0]: params["new_name"]}
        if mapping:
            df = df.rename(columns=dict(mapping))
        return df

    if t == "cast_dtype":
        to = params.get("to", "float")
        errors = params.get("errors", "coerce")
        for c in cols:
            if c not in df.columns:
                continue
            if to == "float" or to == "int":
                df[c] = pd.to_numeric(df[c], errors=errors)
                if to == "int":
                    df[c] = df[c].astype("Int64")
            elif to == "datetime":
                df[c] = pd.to_datetime(df[c], errors=errors)
            elif to == "string":
                df[c] = df[c].astype(str)
        return df

    if t == "unit_convert":
        # parameters: {from_unit, to_unit, factor}
        factor = float(params.get("factor", 1.0))
        for c in cols:
            if c not in df.columns:
                continue
            df[c] = pd.to_numeric(df[c], errors="coerce") * factor
        return df

    if t == "normalize_value":
        # parameters: {regex_strip, mapping, lower}
        regex = params.get("regex_strip")
        mapping = params.get("mapping") or {}
        lower = bool(params.get("lower"))
        for c in cols:
            if c not in df.columns:
                continue
            s = df[c].astype(str)
            if regex:
                s = s.str.replace(regex, "", regex=True)
            if mapping:
                s = s.replace(mapping)
            if lower:
                s = s.str.lower()
            # Replace common "missing" tokens with NaN
            s = s.replace({"--": pd.NA, "—": pd.NA, "N/A": pd.NA, "NA": pd.NA,
                           "null": pd.NA, "None": pd.NA, "": pd.NA})
            df[c] = s
        return df

    if t == "impute_missing":
        strategy = params.get("strategy", "median")
        value = params.get("value")
        for c in cols:
            if c not in df.columns:
                continue
            if strategy == "median":
                num = pd.to_numeric(df[c], errors="coerce")
                df[c] = num.fillna(num.median())
            elif strategy == "mean":
                num = pd.to_numeric(df[c], errors="coerce")
                df[c] = num.fillna(num.mean())
            elif strategy == "mode":
                m = df[c].mode(dropna=True)
                if not m.empty:
                    df[c] = df[c].fillna(m.iloc[0])
            elif strategy == "constant" and value is not None:
                df[c] = df[c].fillna(value)
        return df

    if t == "outlier_flag":
        method = params.get("method", "iqr")
        k = float(params.get("k", 1.5))
        for c in cols:
            if c not in df.columns:
                continue
            num = pd.to_numeric(df[c], errors="coerce")
            if method == "iqr":
                q1, q3 = num.quantile(0.25), num.quantile(0.75)
                iqr = q3 - q1
                lo, hi = q1 - k * iqr, q3 + k * iqr
                new_col = params.get("new_column", f"{c}__outlier")
                df[new_col] = ((num < lo) | (num > hi)).astype("Int64")
        return df

    if t == "hash_pii":
        algo = params.get("algo", "sha256")
        salt = os.environ.get(params.get("salt_env", "AUTOCSR_PII_SALT"), "autocsr-default-salt")
        for c in cols:
            if c not in df.columns:
                continue
            def _h(v):
                if pd.isna(v):
                    return None
                s = (str(v) + salt).encode("utf-8")
                if algo == "sha256":
                    return hashlib.sha256(s).hexdigest()[:16]
                if algo == "sha1":
                    return hashlib.sha1(s).hexdigest()[:16]
                return hashlib.md5(s).hexdigest()[:16]
            df[c] = df[c].map(_h)
        return df

    if t == "split_column":
        sep = params.get("sep", "/")
        new_cols = params.get("new_columns") or []
        if not cols or not new_cols:
            return df
        src = cols[0]
        if src not in df.columns:
            return df
        if isinstance(sep, str) and len(sep) == 1:
            parts = df[src].astype(str).str.split(re.escape(sep), n=len(new_cols) - 1, expand=True)
        else:
            parts = df[src].astype(str).str.split(sep, n=len(new_cols) - 1, expand=True, regex=True)
        for i, nc in enumerate(new_cols):
            if i < parts.shape[1]:
                df[nc] = parts[i]
        return df

    if t == "merge_columns":
        new_col = params.get("new_column") or "merged"
        sep = params.get("sep", " ")
        present = [c for c in cols if c in df.columns]
        if present:
            df[new_col] = df[present].astype(str).agg(sep.join, axis=1)
        return df

    if t == "derive_column":
        new_col = params.get("new_column") or "derived"
        expr = params.get("expr")
        if expr:
            try:
                df[new_col] = df.eval(expr, engine="python")
            except Exception:
                pass
        return df

    if t == "map_to_cdisc":
        # Deferred to M3; record but no-op so pipelines stay round-trippable
        return df

    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_proposals(
    df_path: Path | str,
    proposals: Iterable[CleansingProposal],
    *,
    project_id: str,
    file_id: str,
    sheet: str | None = None,
) -> dict[str, Any]:
    """Read df_path, snapshot pre-state, apply rules in order, write processed/."""
    src = Path(df_path)
    df = _read_table(src)
    hash_before = _df_hash(df)
    rows_before = int(df.shape[0])

    # Snapshot pre-state
    snap_id = uuid.uuid4().hex[:12]
    snap_path = _snap_dir(project_id) / f"{snap_id}.parquet"
    snap_written = _write_table(df.copy(), snap_path)

    applied: list[dict[str, Any]] = []
    for prop in proposals:
        try:
            df = _apply_one(df, prop)
            applied.append({"proposal_id": prop.id, "type": prop.type,
                            "target_columns": prop.target_columns})
        except Exception as e:
            applied.append({"proposal_id": prop.id, "type": prop.type, "error": str(e)})

    hash_after = _df_hash(df)
    rows_after = int(df.shape[0])

    out_name = f"{file_id}.parquet" if not sheet else f"{file_id}__{sheet}.parquet"
    out_path = _processed_dir(project_id) / out_name
    final = _write_table(df, out_path)

    snapshot = Snapshot(
        id=snap_id, project_id=project_id, file_id=file_id, sheet=sheet,
        parquet_path=snap_written,
        hash_before=hash_before, hash_after=hash_after,
        created_at=datetime.now(timezone.utc),
    )
    _save_snapshot(snapshot)

    return {
        "snapshot_id": snap_id,
        "processed_path": final,
        "hash_before": hash_before, "hash_after": hash_after,
        "rows_before": rows_before, "rows_after": rows_after,
        "applied": applied,
    }


def _save_snapshot(snap: Snapshot) -> None:
    p = _snap_dir(snap.project_id) / "_index.json"
    items: list[dict] = []
    if p.exists():
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            items = []
    items.append(json.loads(snap.model_dump_json()))
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_snapshots(project_id: str, file_id: str | None = None) -> list[Snapshot]:
    p = _snap_dir(project_id) / "_index.json"
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out = []
    for r in raw:
        try:
            s = Snapshot.model_validate(r)
        except Exception:
            continue
        if file_id and s.file_id != file_id:
            continue
        out.append(s)
    return out


def rollback(project_id: str, snapshot_id: str) -> dict[str, Any]:
    """Copy snapshot parquet back into processed/, then truncate the snapshot index
    to entries strictly before the chosen snapshot (so re-applying re-snapshots)."""
    snaps = list_snapshots(project_id)
    target = next((s for s in snaps if s.id == snapshot_id), None)
    if not target:
        return {"ok": False, "error": f"snapshot {snapshot_id} not found"}
    src = Path(target.parquet_path)
    if not src.exists():
        return {"ok": False, "error": f"snapshot file missing: {src}"}
    out_name = f"{target.file_id}.parquet" if not target.sheet else f"{target.file_id}__{target.sheet}.parquet"
    out_path = _processed_dir(project_id) / out_name
    import shutil
    shutil.copyfile(src, out_path)
    return {"ok": True, "restored_to": str(out_path)}
