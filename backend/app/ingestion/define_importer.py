"""M21 — define.xml (ADaM/SDTM metadata) → corpus notes.

CDISC define.xml exposes ItemGroupDef / ItemDef trees describing every
variable in a study dataset. Importing them lets writer agents cite the
variable's official label, codelist, role and origin instead of
guessing from the column header.

We try lxml first, then fall back to the stdlib ``xml.etree`` so the
module degrades gracefully on installs without lxml.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("autocsr.ingestion.define")


class VariableDef(BaseModel):
    oid: str
    name: str
    label: str = ""
    data_type: str = ""
    origin: str = ""
    role: str = ""
    codelist_oid: str | None = None
    dataset: str = ""


class DefineImportResult(BaseModel):
    project_id: str
    source_filename: str
    n_datasets: int
    n_variables: int
    corpus_block_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# define.xml uses the CDISC ODM namespace
_ODM_NS = "{http://www.cdisc.org/ns/odm/v1.3}"
_DEF_NS = "{http://www.cdisc.org/ns/def/v2.0}"


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _parse(path: Path):
    try:
        from lxml import etree  # type: ignore
        return etree.parse(str(path)).getroot()
    except Exception:
        try:
            import xml.etree.ElementTree as ET
            return ET.parse(str(path)).getroot()
        except Exception as e:
            logger.warning("define_xml_parse_failed: %s", e)
            return None


def import_define(project_id: str, xml_path: str | Path,
                    source_filename: str | None = None) -> DefineImportResult:
    p = Path(xml_path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    root = _parse(p)
    if root is None:
        return DefineImportResult(
            project_id=project_id,
            source_filename=source_filename or p.name,
            n_datasets=0, n_variables=0,
            notes=["xml parse failed; install lxml for better error reporting"],
        )
    # Walk ItemDef / ItemGroupDef regardless of namespace.
    item_defs: dict[str, VariableDef] = {}
    dataset_for_oid: dict[str, str] = {}
    n_datasets = 0
    for el in root.iter():
        tag = _strip_ns(el.tag)
        if tag == "ItemGroupDef":
            n_datasets += 1
            ds_name = el.attrib.get("Name") or el.attrib.get("OID") or ""
            for child in el.iter():
                ctag = _strip_ns(child.tag)
                if ctag == "ItemRef":
                    item_oid = child.attrib.get("ItemOID")
                    if item_oid:
                        dataset_for_oid.setdefault(item_oid, ds_name)
        elif tag == "ItemDef":
            oid = el.attrib.get("OID") or ""
            name = el.attrib.get("Name") or oid
            data_type = el.attrib.get("DataType") or ""
            role = el.attrib.get("Role") or ""
            origin = el.attrib.get("Origin") or ""
            codelist_oid = None
            label = ""
            for child in el:
                ctag = _strip_ns(child.tag)
                if ctag == "CodeListRef":
                    codelist_oid = child.attrib.get("CodeListOID")
                elif ctag == "Description":
                    for tx in child.iter():
                        if _strip_ns(tx.tag) == "TranslatedText":
                            label = (tx.text or "").strip()
                            break
                elif ctag in ("Label", "ItemLabel"):
                    label = (el.attrib.get("Label") or label or "").strip()
            if origin == "":
                # def: namespace puts Origin as a child element with the
                # actual text inside <Description>/<TranslatedText>.
                for child in el:
                    if _strip_ns(child.tag) == "Origin":
                        for tx in child.iter():
                            if _strip_ns(tx.tag) == "TranslatedText":
                                origin = (tx.text or "").strip()
                                break
            item_defs[oid] = VariableDef(
                oid=oid, name=name, label=label, data_type=data_type,
                role=role, origin=origin, codelist_oid=codelist_oid,
            )
    # attach dataset name
    for oid, vd in item_defs.items():
        vd.dataset = dataset_for_oid.get(oid, "")
    # Push into corpus -----------------------------------------------------
    block_ids: list[str] = []
    try:
        from app.corpus.index import Block, add_block
        for i, vd in enumerate(item_defs.values()):
            text = (
                f"[define.xml] dataset={vd.dataset} variable={vd.name} "
                f"label={vd.label!r} type={vd.data_type} role={vd.role} "
                f"origin={vd.origin}"
                + (f" codelist={vd.codelist_oid}" if vd.codelist_oid else "")
            )
            block = Block(
                id=f"def_{vd.dataset or 'NA'}_{vd.name}"[:60],
                project_id=project_id,
                type="note",
                page=1, col=1, para=i + 1,
                text=text,
                meta={
                    "kind": "define_xml_variable",
                    "dataset": vd.dataset,
                    "variable": vd.name,
                    "label": vd.label,
                    "data_type": vd.data_type,
                    "role": vd.role,
                    "origin": vd.origin,
                    "codelist_oid": vd.codelist_oid,
                },
            )
            try:
                bid = add_block(project_id, block)
                block_ids.append(bid)
            except Exception:
                continue
    except Exception as e:
        logger.warning("define_corpus_save_failed: %s", e)
    # Persist raw extract --------------------------------------------------
    try:
        from app.config import data_dir
        import json as _json
        notes_dir = data_dir() / "projects" / project_id / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "define.json").write_text(
            _json.dumps({
                "source": source_filename or p.name,
                "n_datasets": n_datasets,
                "n_variables": len(item_defs),
                "variables": [v.model_dump() for v in item_defs.values()][:200],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return DefineImportResult(
        project_id=project_id,
        source_filename=source_filename or p.name,
        n_datasets=n_datasets,
        n_variables=len(item_defs),
        corpus_block_ids=block_ids,
    )
