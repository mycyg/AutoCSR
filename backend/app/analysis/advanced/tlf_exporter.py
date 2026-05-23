"""TLF (Table-Listing-Figure) zip exporter.

Bundles every persisted StatBlock for a project into a single .zip:

    <project>/exports/TLF_<yyyymmdd_hhmmss>.zip
        manifest.json               — list of tables + analysis types
        define.xml                  — minimal define-XML style summary
        README.md                   — human-readable index
        tables/
            <slug>.rtf              — one RTF per StatBlock
            <slug>.csv              — one CSV per StatBlock
        figures/
            <slug>.png              — any PNG referenced by result_json

The RTFs are not full sponsor-template RTF — they're a clean Word-openable
serialization of the markdown table so QC reviewers can diff them.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.analysis.store import get as get_block, list_blocks
from app.config import data_dir


def _exports_dir(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip().lower()
    s = re.sub(r"[\s/\\]+", "_", s)
    return s[:60] or "table"


def _markdown_table_to_rows(md: str) -> list[list[str]]:
    """Extract the first markdown table from a string into row-of-cells form."""
    rows: list[list[str]] = []
    in_table = False
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?[-]+:?", c) for c in cells):
                in_table = True
                continue
            rows.append(cells)
            in_table = True
        elif in_table and not line:
            break
    return rows


def _md_table_to_rtf(rows: list[list[str]], title: str) -> str:
    if not rows:
        return "{\\rtf1\\ansi\\deff0\n" + _escape_rtf(title) + "\\par}"
    n_cols = max(len(r) for r in rows)
    rows = [r + [""] * (n_cols - len(r)) for r in rows]
    cellx = "".join(f"\\cellx{(i + 1) * 2000}" for i in range(n_cols))
    body_lines: list[str] = []
    for r in rows:
        body_lines.append("\\trowd\\trgaph100" + cellx)
        for c in r:
            body_lines.append(f"\\intbl {_escape_rtf(c)}\\cell")
        body_lines.append("\\row")
    return (
        "{\\rtf1\\ansi\\deff0\n"
        + "{\\b " + _escape_rtf(title) + "}\\par\\par\n"
        + "\n".join(body_lines)
        + "\\par}"
    )


def _escape_rtf(text: str) -> str:
    out: list[str] = []
    for ch in (text or ""):
        if ch == "\\":
            out.append("\\\\")
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        elif ord(ch) < 128:
            out.append(ch)
        else:
            out.append(f"\\u{ord(ch)}?")
    return "".join(out)


def _md_table_to_csv(rows: list[list[str]]) -> str:
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def _define_xml(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3" FileType="Snapshot">')
    parts.append('  <Study OID="AUTOCSR_TLF">')
    parts.append('    <MetaDataVersion OID="MDV.AUTOCSR.TLF" Name="AutoCSR TLF bundle">')
    for b in blocks:
        slug = _slugify(b["title"])
        cols = b.get("columns") or []
        parts.append(f'      <ItemGroupDef OID="IG.{slug}" Name="{slug}" Repeating="Yes">')
        parts.append(f'        <Description><TranslatedText xml:lang="en">{_xml_escape(b["title"])}</TranslatedText></Description>')
        for i, c in enumerate(cols):
            parts.append(f'        <ItemRef ItemOID="IT.{slug}.{i}" OrderNumber="{i+1}"/>')
        parts.append('      </ItemGroupDef>')
        for i, c in enumerate(cols):
            parts.append(f'      <ItemDef OID="IT.{slug}.{i}" Name="{_xml_escape(c)}" DataType="text" Length="200"/>')
    parts.append('    </MetaDataVersion>')
    parts.append('  </Study>')
    parts.append('</ODM>')
    return "\n".join(parts)


def _xml_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def export_tlf(project_id: str, *, progress=None) -> Path:
    """Build the zip and return its path. ``progress`` is an optional async
    callable ``progress(phase, **meta)`` for WS updates.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_zip = _exports_dir(project_id) / f"TLF_{ts}.zip"

    summaries = list_blocks(project_id)
    if progress:
        try:
            progress("collect", n=len(summaries))
        except Exception:
            pass

    manifest: list[dict[str, Any]] = []
    define_blocks: list[dict[str, Any]] = []

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, s in enumerate(summaries):
            block = get_block(project_id, s["id"])
            if block is None:
                continue
            slug = _slugify(f"{s['analysis_type']}_{block.title}_{s['id'][:6]}")
            rows = _markdown_table_to_rows(block.markdown_table)
            csv_text = _md_table_to_csv(rows)
            rtf_text = _md_table_to_rtf(rows, block.title)
            cols = rows[0] if rows else []
            zf.writestr(f"tables/{slug}.csv", csv_text)
            zf.writestr(f"tables/{slug}.rtf", rtf_text)
            # Embed any PNG referenced in result_json
            rj = block.result_json or {}
            png_path = rj.get("png_path") if isinstance(rj, dict) else None
            if png_path and Path(png_path).exists():
                try:
                    zf.write(png_path, arcname=f"figures/{slug}.png")
                except Exception:
                    pass
            manifest.append({
                "id": block.id,
                "slug": slug,
                "title": block.title,
                "analysis_type": block.analysis_type,
                "rtf": f"tables/{slug}.rtf",
                "csv": f"tables/{slug}.csv",
                "ref_code": block.ref_code,
            })
            define_blocks.append({
                "title": block.title, "columns": cols,
            })
            if progress:
                try:
                    progress("write", index=i + 1, total=len(summaries))
                except Exception:
                    pass

        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("define.xml", _define_xml(define_blocks))
        readme = _readme(project_id, manifest)
        zf.writestr("README.md", readme)

    if progress:
        try:
            progress("done", path=str(out_zip), size=out_zip.stat().st_size)
        except Exception:
            pass
    return out_zip


def _readme(project_id: str, items: list[dict[str, Any]]) -> str:
    lines = [f"# TLF bundle for project {project_id}", "",
             f"Generated {datetime.now(timezone.utc).isoformat()}", "",
             f"Tables included: **{len(items)}**", "", "## Index"]
    for it in items:
        lines.append(f"- [{it['title']}] ({it['rtf']} / {it['csv']}) — `{it['analysis_type']}`")
    lines.append("")
    lines.append("`define.xml` provides a minimal CDISC-style schema description.")
    return "\n".join(lines)


def list_tlf_exports(project_id: str) -> list[dict[str, Any]]:
    p = _exports_dir(project_id)
    out: list[dict[str, Any]] = []
    for f in sorted(p.glob("TLF_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        out.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
            "path": str(f),
        })
    return out
