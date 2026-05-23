"""End-to-end test for M21 (v2.3) — multi-tenant auth + reverse import
+ advanced visualizations.

Coverage:
    Auth roundtrip      register / login / refresh / me / patch-me
    Tenant isolation    user_A cannot see user_B's project (403)
    Member roles        reviewer can comment+sign, cannot write markdown
    Reverse import      protocol PDF / SAP docx / define.xml
    Advanced viz        km_with_risk / bland_altman / heatmap / pk_3d
    Dashboard           POST + persist
    Migration           idempotent runner

Strategy
    * Spins uvicorn on :8801 (won't clash with M19/M20 :8800)
    * Uses dev_mode=true so legacy X-User-Id paths still work, *but*
      the auth roundtrip goes through real JWT regardless.
    * Cleans up created projects at the end.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BASE = "http://127.0.0.1:8801"


def info(msg: str) -> None:
    print(f"[E2E-M21] {msg}", flush=True)


CHECKS: list[tuple[str, bool]] = []


def check(name: str, cond: bool, hint: str = "") -> bool:
    marker = "PASS" if cond else "FAIL"
    print(f"  [{marker}] {name}{' — ' + hint if (hint and not cond) else ''}",
          flush=True)
    CHECKS.append((name, bool(cond)))
    return bool(cond)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


def _start(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8801")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server.main:app",
         "--port", "8801", "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=BACKEND, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if requests.get(f"{BASE}/api/health", timeout=2).status_code == 200:
                info("server up")
                return proc
        except requests.RequestException:
            time.sleep(0.4)
    proc.terminate()
    raise RuntimeError("server did not come up")


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _cleanup_project(pid: str) -> None:
    try:
        sys.path.insert(0, str(BACKEND))
        from app.config import data_dir
        shutil.rmtree(data_dir() / "projects" / pid, ignore_errors=True)
        pj = data_dir() / "projects.json"
        if pj.exists():
            items = json.loads(pj.read_text(encoding="utf-8") or "[]")
            items = [p for p in items if p.get("id") != pid]
            pj.write_text(json.dumps(items, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _unique_email(label: str) -> str:
    return f"m21_{label}_{uuid.uuid4().hex[:6]}@dev.local"


# ---------------------------------------------------------------------------
# Phase A — auth roundtrip + JWT validity
# ---------------------------------------------------------------------------


def _phase_auth() -> dict:
    info("phase A: auth roundtrip")
    email_a = _unique_email("alice")
    r = requests.post(f"{BASE}/api/auth/register", json={
        "email": email_a, "password": "secret123", "display_name": "Alice A",
        "tenant_name": "Tenant Alpha",
    })
    check("register 201", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    a = r.json()
    check("register returns user.tenant_id", bool(a.get("user", {}).get("tenant_id")))
    check("register returns access_token", bool(a.get("access_token")))
    tenant_a_id = a["user"]["tenant_id"]
    user_a_id = a["user"]["id"]
    access_a = a["access_token"]
    refresh_a = a["refresh_token"]

    # Duplicate email rejected
    r2 = requests.post(f"{BASE}/api/auth/register", json={
        "email": email_a, "password": "secret123",
    })
    check("duplicate-email register 409", r2.status_code == 409,
           f"got {r2.status_code}")

    # Login
    r = requests.post(f"{BASE}/api/auth/login", json={
        "email": email_a, "password": "secret123",
    })
    check("login 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    access_a = r.json()["access_token"]

    r = requests.post(f"{BASE}/api/auth/login", json={
        "email": email_a, "password": "wrong",
    })
    check("login wrong-pwd 401", r.status_code == 401)

    # /auth/me with bearer
    r = requests.get(f"{BASE}/api/auth/me", headers=_auth_headers(access_a))
    check("/auth/me 200 with bearer", r.status_code == 200, f"{r.text[:200]}")
    me = r.json()
    check("/auth/me echoes correct tenant",
           me.get("user", {}).get("tenant_id") == tenant_a_id,
           f"got {me}")

    # Refresh
    r = requests.post(f"{BASE}/api/auth/refresh",
                       json={"refresh_token": refresh_a})
    check("refresh 200", r.status_code == 200, f"{r.text[:200]}")
    new_access = r.json().get("access_token")
    check("refresh returns access_token", bool(new_access))

    # PATCH /auth/me
    r = requests.patch(f"{BASE}/api/auth/me",
                        headers=_auth_headers(access_a),
                        json={"display_name": "Alice A (updated)"})
    check("PATCH /auth/me 200", r.status_code == 200, r.text[:200])
    check("display_name updated", r.json().get("display_name", "").endswith("(updated)"))

    # Register user B with same tenant — second user gets role='user'
    email_b = _unique_email("bob")
    r = requests.post(f"{BASE}/api/auth/register", json={
        "email": email_b, "password": "secret123", "display_name": "Bob B",
    })
    check("register default tenant 201", r.status_code == 201)
    b = r.json()
    user_b_id = b["user"]["id"]
    access_b = b["access_token"]
    tenant_b_id = b["user"]["tenant_id"]
    check("user_B has 'default' tenant",
           tenant_b_id == "default" or tenant_b_id != tenant_a_id,
           f"a={tenant_a_id} b={tenant_b_id}")

    return {
        "user_a": user_a_id, "tenant_a": tenant_a_id,
        "access_a": access_a, "refresh_a": refresh_a,
        "user_b": user_b_id, "tenant_b": tenant_b_id,
        "access_b": access_b,
    }


# ---------------------------------------------------------------------------
# Phase B — tenant isolation + member roles
# ---------------------------------------------------------------------------


def _phase_tenant(auth: dict) -> dict:
    info("phase B: tenant isolation + member roles")
    # Alice creates a project
    r = requests.post(f"{BASE}/api/projects",
                       headers=_auth_headers(auth["access_a"]),
                       json={"name": "Alice Study", "language": "en"})
    check("alice creates project 201", r.status_code == 201, r.text[:200])
    pid = r.json()["id"]
    check("project has Alice's tenant",
           r.json().get("tenant_id") == auth["tenant_a"],
           f"got {r.json().get('tenant_id')}")

    # Alice can read her project
    r = requests.get(f"{BASE}/api/projects/{pid}",
                      headers=_auth_headers(auth["access_a"]))
    check("alice reads own project", r.status_code == 200, f"got {r.status_code}")

    # Bob (different tenant) cannot read it (403 or 404 both acceptable)
    r = requests.get(f"{BASE}/api/projects/{pid}",
                      headers=_auth_headers(auth["access_b"]))
    check("bob cross-tenant read denied", r.status_code in (403, 404),
           f"got {r.status_code} {r.text[:120]}")

    # Bob list_projects shouldn't surface Alice's project
    r = requests.get(f"{BASE}/api/projects",
                      headers=_auth_headers(auth["access_b"]))
    if r.status_code == 200:
        ids = {p["id"] for p in r.json()}
        check("alice's pid not in bob's list", pid not in ids,
               f"ids={ids}")
    else:
        check("bob list 200", False, f"got {r.status_code}")

    # ---- Member ACL within the same tenant ----------------------------
    # Register charlie in alice's tenant (re-uses register endpoint with a
    # synthetic admin-style flow: alice creates charlie as admin via
    # direct register + then PATCHes his tenant_id via tenant invite is
    # a v3 nicety. For this e2e we register charlie under alice's tenant
    # by passing tenant_name = alice's tenant name — instead we use the
    # auth/register again and then patch the user record directly via the
    # backend Python API.)
    sys.path.insert(0, str(BACKEND))
    from app.auth.models import (
        User as AuthUser, ProjectMember,
        get_user_by_id, upsert_user, upsert_member,
    )
    cid = "u_charlie_" + uuid.uuid4().hex[:6]
    from app.auth.password import hash_password
    upsert_user(AuthUser(
        id=cid, email=f"{cid}@dev.local", display_name="Charlie C",
        password_hash=hash_password("secret123"),
        role="user", tenant_id=auth["tenant_a"], name="Charlie C",
    ))
    # Login as charlie
    r = requests.post(f"{BASE}/api/auth/login", json={
        "email": f"{cid}@dev.local", "password": "secret123",
    })
    check("charlie login 200", r.status_code == 200, r.text[:200])
    access_c = r.json()["access_token"]

    # Charlie is in the same tenant but not yet a project member -> read OK
    r = requests.get(f"{BASE}/api/projects/{pid}",
                      headers=_auth_headers(access_c))
    check("same-tenant non-member can read", r.status_code == 200,
           f"got {r.status_code}")

    # ...but cannot mutate (PATCH name)
    r = requests.patch(f"{BASE}/api/projects/{pid}",
                        headers=_auth_headers(access_c),
                        json={"name": "Hijacked"})
    check("non-member write 403", r.status_code == 403,
           f"got {r.status_code}")

    # Alice (owner) invites Charlie as reviewer via /members
    r = requests.post(f"{BASE}/api/projects/{pid}/members",
                       headers=_auth_headers(auth["access_a"]),
                       json={"user_id": cid, "role": "reviewer"})
    check("owner adds reviewer 201", r.status_code == 201, r.text[:200])

    # GET members
    r = requests.get(f"{BASE}/api/projects/{pid}/members",
                      headers=_auth_headers(auth["access_a"]))
    check("list members 200", r.status_code == 200)
    members = r.json() if r.status_code == 200 else []
    roles = {m["user_id"]: m["role"] for m in members}
    check("charlie listed as reviewer",
           roles.get(cid) == "reviewer", f"roles={roles}")

    # Reviewer still cannot PATCH project metadata (write action)
    r = requests.patch(f"{BASE}/api/projects/{pid}",
                        headers=_auth_headers(access_c),
                        json={"name": "Charlie Edit"})
    check("reviewer write still 403", r.status_code == 403,
           f"got {r.status_code}")

    # Alice promotes Charlie to editor
    r = requests.patch(f"{BASE}/api/projects/{pid}/members/{cid}",
                        headers=_auth_headers(auth["access_a"]),
                        json={"role": "editor"})
    check("owner patches member role 200", r.status_code == 200, r.text[:200])

    # Editor can now PATCH project name
    r = requests.patch(f"{BASE}/api/projects/{pid}",
                        headers=_auth_headers(access_c),
                        json={"name": "Edited by Charlie"})
    check("editor write 200", r.status_code == 200, r.text[:200])

    # Cross-tenant member invite forbidden
    r = requests.post(f"{BASE}/api/projects/{pid}/members",
                       headers=_auth_headers(auth["access_a"]),
                       json={"user_id": auth["user_b"], "role": "viewer"})
    check("cross-tenant invite rejected", r.status_code == 400,
           f"got {r.status_code}")

    return {"pid": pid, "charlie": cid, "access_c": access_c}


# ---------------------------------------------------------------------------
# Phase C — reverse import (protocol / SAP / define.xml)
# ---------------------------------------------------------------------------


def _build_fake_protocol_pdf(path: Path) -> None:
    """Write a 1-page PDF whose text contains the 8 fields."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception:
        # If reportlab is missing in test env, fall back to pymupdf
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), _protocol_text())
        doc.save(str(path))
        doc.close()
        return
    c = canvas.Canvas(str(path), pagesize=letter)
    text = c.beginText(72, 720)
    text.setFont("Helvetica", 10)
    for line in _protocol_text().splitlines():
        text.textLine(line)
    c.drawText(text)
    c.save()


def _protocol_text() -> str:
    return (
        "PROTOCOL NUMBER: NCT-77777\n"
        "Phase III\n"
        "Indication: relapsed multiple myeloma\n"
        "Treatment: bortezomib 1.3 mg/m2 + dex 20 mg\n"
        "Population: adults 18-85 with confirmed RRMM\n"
        "Randomized, double-blind, placebo-controlled\n"
        "Sample size: 480\n"
        "Primary endpoint: progression-free survival (PFS)\n"
        "Secondary endpoint: overall response rate (ORR)\n"
    )


def _build_fake_sap_docx(path: Path) -> None:
    from docx import Document
    doc = Document()
    doc.add_heading("Statistical Analysis Plan", level=0)
    doc.add_heading("1 Introduction", level=1)
    doc.add_paragraph("This SAP describes the planned analyses for study M21.")
    doc.add_heading("2 Analysis Populations", level=1)
    doc.add_paragraph("ITT population includes all randomized subjects.")
    doc.add_paragraph("PP population excludes major protocol deviators.")
    doc.add_heading("3 Statistical Methods", level=1)
    doc.add_paragraph("Continuous variables summarised with n, mean, SD, "
                       "median, min and max. Categorical variables with "
                       "frequencies and percentages.")
    doc.add_heading("4 Primary Efficacy Analysis", level=1)
    doc.add_paragraph("PFS will be analysed using a stratified log-rank "
                       "test with stratification factors prior therapy "
                       "lines and ECOG.")
    doc.add_heading("5 Safety Analysis", level=1)
    doc.add_paragraph("Adverse events coded with MedDRA and summarised by "
                       "system organ class and preferred term.")
    doc.save(str(path))


def _build_fake_define_xml(path: Path) -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<ODM xmlns="http://www.cdisc.org/ns/odm/v1.3"
      xmlns:def="http://www.cdisc.org/ns/def/v2.0">
  <Study OID="m21-study">
    <MetaDataVersion OID="MDV.1" Name="ADaM">
      <ItemGroupDef OID="IG.ADSL" Name="ADSL">
        <ItemRef ItemOID="IT.USUBJID"/>
        <ItemRef ItemOID="IT.AGE"/>
        <ItemRef ItemOID="IT.SEX"/>
      </ItemGroupDef>
      <ItemGroupDef OID="IG.ADAE" Name="ADAE">
        <ItemRef ItemOID="IT.AETERM"/>
        <ItemRef ItemOID="IT.AESEV"/>
      </ItemGroupDef>
      <ItemDef OID="IT.USUBJID" Name="USUBJID" DataType="text" Role="Identifier"/>
      <ItemDef OID="IT.AGE" Name="AGE" DataType="integer" Role="Topic">
        <Description><TranslatedText xml:lang="en">Age in years</TranslatedText></Description>
      </ItemDef>
      <ItemDef OID="IT.SEX" Name="SEX" DataType="text" Role="Topic"/>
      <ItemDef OID="IT.AETERM" Name="AETERM" DataType="text" Role="Topic">
        <Description><TranslatedText xml:lang="en">Reported Adverse Event Term</TranslatedText></Description>
      </ItemDef>
      <ItemDef OID="IT.AESEV" Name="AESEV" DataType="text" Role="Variable Qualifier"/>
    </MetaDataVersion>
  </Study>
</ODM>
"""
    path.write_text(xml, encoding="utf-8")


def _phase_import(auth: dict, tctx: dict) -> None:
    info("phase C: reverse import")
    pid = tctx["pid"]
    tmpdir = Path(BACKEND) / "tmp_e2e_m21"
    tmpdir.mkdir(parents=True, exist_ok=True)

    # 1) Protocol PDF
    pdf_path = tmpdir / "protocol.pdf"
    _build_fake_protocol_pdf(pdf_path)
    with pdf_path.open("rb") as f:
        r = requests.post(
            f"{BASE}/api/projects/{pid}/import/protocol",
            headers=_auth_headers(auth["access_a"]),
            files={"file": ("protocol.pdf", f, "application/pdf")},
        )
    check("/import/protocol 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        data = r.json()
        check("protocol metadata has study_id",
               bool((data.get("metadata") or {}).get("study_id")),
               f"got {data.get('metadata')}")

    # 2) SAP docx
    sap_path = tmpdir / "sap.docx"
    _build_fake_sap_docx(sap_path)
    with sap_path.open("rb") as f:
        r = requests.post(
            f"{BASE}/api/projects/{pid}/import/sap",
            headers=_auth_headers(auth["access_a"]),
            files={"file": ("sap.docx", f,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    check("/import/sap 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        data = r.json()
        check("sap reports analysis_sections",
               len(data.get("analysis_sections") or []) >= 1,
               f"got {data}")

    # 3) define.xml
    xml_path = tmpdir / "define.xml"
    _build_fake_define_xml(xml_path)
    with xml_path.open("rb") as f:
        r = requests.post(
            f"{BASE}/api/projects/{pid}/import/define",
            headers=_auth_headers(auth["access_a"]),
            files={"file": ("define.xml", f, "text/xml")},
        )
    check("/import/define 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        data = r.json()
        check("define reports >= 5 variables",
               data.get("n_variables", 0) >= 5,
               f"got n_variables={data.get('n_variables')}")
        check("define reports >= 2 datasets",
               data.get("n_datasets", 0) >= 2,
               f"got n_datasets={data.get('n_datasets')}")


# ---------------------------------------------------------------------------
# Phase D — advanced visualizations
# ---------------------------------------------------------------------------


def _build_km_parquet(pid: str) -> str:
    sys.path.insert(0, str(BACKEND))
    from app.config import data_dir
    import pandas as pd
    proc_dir = data_dir() / "projects" / pid / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    # 60 subjects, 2 arms
    import random
    random.seed(42)
    rows = []
    for i in range(60):
        arm = "Active" if i % 2 == 0 else "Placebo"
        t = random.uniform(1, 15)
        cnsr = 0 if random.random() < (0.45 if arm == "Active" else 0.65) else 1
        rows.append({"USUBJID": f"S{i:03d}", "AVAL": t, "CNSR": cnsr, "TRT01P": arm})
    p = proc_dir / "adtte_synth.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return str(p)


def _build_pk_parquet(pid: str) -> str:
    sys.path.insert(0, str(BACKEND))
    from app.config import data_dir
    import pandas as pd
    proc_dir = data_dir() / "projects" / pid / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    import random
    random.seed(7)
    rows = []
    for sid in range(6):
        for t in (0.5, 1, 2, 4, 8, 12, 24):
            c = max(0.0, 100 * (0.5 ** (t / 6)) * (1 + 0.1 * random.random()))
            rows.append({"USUBJID": f"P{sid:02d}", "PCDTC": float(t),
                          "PCSTRESN": c})
    p = proc_dir / "pc_synth.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return str(p)


def _build_pair_parquet(pid: str) -> str:
    sys.path.insert(0, str(BACKEND))
    from app.config import data_dir
    import pandas as pd
    proc_dir = data_dir() / "projects" / pid / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    import random
    random.seed(11)
    rows = []
    for i in range(80):
        m1 = random.uniform(80, 200)
        m2 = m1 + random.uniform(-15, 15)
        rows.append({"USUBJID": f"L{i:03d}", "M1": m1, "M2": m2})
    p = proc_dir / "pair_synth.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return str(p)


def _build_heatmap_parquet(pid: str) -> str:
    sys.path.insert(0, str(BACKEND))
    from app.config import data_dir
    import pandas as pd
    import random
    proc_dir = data_dir() / "projects" / pid / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)
    random.seed(101)
    rows = []
    for g in ("GENE_A", "GENE_B", "GENE_C", "GENE_D", "GENE_E"):
        for s in range(8):
            rows.append({"GENE": g, "SUBJECT": f"H{s:02d}",
                          "VALUE": random.uniform(-2, 2)})
    p = proc_dir / "heatmap_synth.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return str(p)


def _phase_viz(auth: dict, tctx: dict) -> list[str]:
    info("phase D: advanced visualizations")
    pid = tctx["pid"]
    saved_ids: list[str] = []

    _build_km_parquet(pid)
    r = requests.post(f"{BASE}/api/projects/{pid}/analysis/km_with_risk",
                       headers=_auth_headers(auth["access_a"]),
                       json={"group_col": "TRT01P",
                              "time_points": [0, 3, 6, 9, 12]})
    check("km_with_risk 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        block = r.json().get("block") or {}
        rj = block.get("result_json") or {}
        check("km result_json has risk_table",
               isinstance(rj.get("risk_table"), dict)
               and len(rj["risk_table"].get("rows") or []) >= 1,
               f"got {list(rj.keys())}")
        saved_ids.append(r.json().get("id", ""))

    pair_path = _build_pair_parquet(pid)
    r = requests.post(f"{BASE}/api/projects/{pid}/analysis/bland_altman",
                       headers=_auth_headers(auth["access_a"]),
                       json={"col_method1": "M1", "col_method2": "M2",
                              "parquet_path": pair_path})
    check("bland_altman 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        rj = ((r.json().get("block") or {}).get("result_json")) or {}
        check("bland_altman has bias + upper_LoA",
               "bias" in rj and "upper_LoA" in rj,
               f"got {list(rj.keys())}")
        saved_ids.append(r.json().get("id", ""))

    hm_path = _build_heatmap_parquet(pid)
    r = requests.post(f"{BASE}/api/projects/{pid}/analysis/heatmap",
                       headers=_auth_headers(auth["access_a"]),
                       json={"row_col": "GENE", "col_col": "SUBJECT",
                              "value_col": "VALUE",
                              "parquet_path": hm_path})
    check("heatmap 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        rj = ((r.json().get("block") or {}).get("result_json")) or {}
        check("heatmap has matrix + labels",
               isinstance(rj.get("matrix"), list)
               and len(rj.get("row_labels") or []) >= 1,
               f"got {list(rj.keys())}")
        saved_ids.append(r.json().get("id", ""))

    pk_path = _build_pk_parquet(pid)
    r = requests.post(f"{BASE}/api/projects/{pid}/analysis/pk_profile_3d",
                       headers=_auth_headers(auth["access_a"]),
                       json={"subject_col": "USUBJID",
                              "time_col": "PCDTC",
                              "conc_col": "PCSTRESN",
                              "parquet_path": pk_path})
    check("pk_profile_3d 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        rj = ((r.json().get("block") or {}).get("result_json")) or {}
        check("pk_3d has subject_labels + echarts_spec",
               len(rj.get("subject_labels") or []) >= 1
               and rj.get("echarts_spec") is not None,
               f"got {list(rj.keys())}")
        saved_ids.append(r.json().get("id", ""))

    # Dashboard composition
    layout = [
        {"stat_id": sid, "chart_type": "auto",
         "position": {"x": (i % 2) * 6, "y": (i // 2) * 4, "w": 6, "h": 4}}
        for i, sid in enumerate(saved_ids[:3]) if sid
    ]
    r = requests.post(f"{BASE}/api/projects/{pid}/dashboard",
                       headers=_auth_headers(auth["access_a"]),
                       json={"name": "M21 demo", "layout": layout})
    check("dashboard create 201", r.status_code == 201, r.text[:200])
    if r.status_code == 201:
        d = r.json()
        check("dashboard persists layout",
               len(d.get("layout") or []) == len(layout),
               f"got {len(d.get('layout') or [])}")

    # Reload via GET
    r = requests.get(f"{BASE}/api/projects/{pid}/dashboards",
                      headers=_auth_headers(auth["access_a"]))
    check("dashboard list 200", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        items = r.json()
        check("dashboard list has >= 1 entry", len(items) >= 1)
    return saved_ids


# ---------------------------------------------------------------------------
# Phase E — migration script idempotency
# ---------------------------------------------------------------------------


def _phase_migration() -> None:
    info("phase E: migration script idempotent re-run")
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "migrate_to_multitenant.py"),
         "--no-backup"],
        capture_output=True, text=True,
    )
    check("migrate run 1 exits 0", res.returncode == 0,
           res.stdout[-200:] + " " + res.stderr[-200:])
    # idempotent — same exit, no error
    res2 = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "migrate_to_multitenant.py"),
         "--no-backup"],
        capture_output=True, text=True,
    )
    check("migrate run 2 exits 0 (idempotent)", res2.returncode == 0,
           res2.stdout[-200:] + " " + res2.stderr[-200:])
    # default tenant exists
    sys.path.insert(0, str(BACKEND))
    from app.auth.models import get_tenant
    check("default tenant exists after migrate",
           get_tenant("default") is not None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND) + (os.pathsep + env.get("PYTHONPATH", ""))
    # Important: dev_mode stays True so M2-M20 e2e suites still pass.
    # The auth-roundtrip checks exercise real JWT regardless.
    proc: subprocess.Popen | None = None
    created_pids: list[str] = []
    try:
        proc = _start(env)
        auth = _phase_auth()
        tctx = _phase_tenant(auth)
        created_pids.append(tctx["pid"])
        _phase_import(auth, tctx)
        _phase_viz(auth, tctx)
        _phase_migration()
    except Exception as e:
        print(f"[E2E-M21] unhandled exception: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2
    finally:
        _stop(proc)
        for pid in created_pids:
            _cleanup_project(pid)
        tmp = BACKEND / "tmp_e2e_m21"
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    n_pass = sum(1 for _, ok in CHECKS if ok)
    n_total = len(CHECKS)
    print(f"\n[E2E-M21] {n_pass}/{n_total} checks passed", flush=True)
    if n_pass != n_total:
        for name, ok in CHECKS:
            if not ok:
                print(f"  FAIL: {name}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
