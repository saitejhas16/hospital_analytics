from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import os
from fastapi.middleware.cors import CORSMiddleware
from datetime import date
from typing import Optional, List

app = FastAPI()

# 👇 Add CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 🔥 for testing; later restrict to "https://saitejhas16.github.io"
    allow_origin_regex="https://.*",  # ensure GitHub Pages is matched
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
# -----------------------------
# Database Connection
# -----------------------------
DB_USER = "saitejhas"         # AlwaysData MySQL username
DB_PASS = "Saitejhas1610*"         # AlwaysData MySQL password
DB_HOST = "mysql-saitejhas.alwaysdata.net"  # Replace with your actual host from AlwaysData
DB_NAME = "saitejhas_hospital_db"

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

# --- Helpers ---
def parse_csv_ints(s: Optional[str]) -> List[int]:
    if not s: return []
    return [int(x) for x in s.split(",") if x.strip().isdigit()]

def build_date_clause(start, end, field="admission_time"):
    clauses, params = [], {}
    if start:
        clauses.append(f"{field} >= :start")
        params["start"] = f"{start} 00:00:00"
    if end:
        clauses.append(f"{field} <= :end")
        params["end"] = f"{end} 23:59:59"
    return clauses, params

def build_in_clause(col, values, param_prefix):
    if not values: return "", {}
    ph = ", ".join([f":{param_prefix}{i}" for i,_ in enumerate(values)])
    params = {f"{param_prefix}{i}": v for i, v in enumerate(values)}
    return f"{col} IN ({ph})", params

# --- KPIs endpoint ---
@app.get("/kpis")
def kpis(
    start: Optional[str] = None,
    end: Optional[str] = None,
    ward_ids: Optional[str] = None,
    doctor_ids: Optional[str] = None,
    status: str = "all"   # "active", "discharged", "all"
):
    dids = parse_csv_ints(doctor_ids)
    wids = parse_csv_ints(ward_ids)

    where_sql, params = [], {}

    if start:
        where_sql.append("a.admission_time >= :start")
        params["start"] = start
    if end:
        where_sql.append("a.admission_time <= :end")
        params["end"] = end
    if status == "active":
        where_sql.append("a.discharge_time IS NULL")
    elif status == "discharged":
        where_sql.append("a.discharge_time IS NOT NULL")
    if dids:
        sql_part, p = build_in_clause("a.attending_doctor_id", dids, "dsel")
        where_sql.append(sql_part)
        params.update(p)
    if wids:
        sql_part, p = build_in_clause("b.ward_id", wids, "wsel")
        where_sql.append(sql_part)
        params.update(p)

    where_clause = "WHERE " + " AND ".join(where_sql) if where_sql else ""

    sql = f"""
      SELECT
        COUNT(DISTINCT a.patient_id) AS total_patients,
        COUNT(DISTINCT a.admission_id) AS total_admissions,
        COUNT(DISTINCT CASE WHEN a.discharge_time IS NULL THEN a.admission_id END) AS active_admissions,
        COUNT(DISTINCT CASE WHEN a.discharge_time IS NOT NULL THEN a.admission_id END) AS discharged_admissions,
        COUNT(DISTINCT d.doctor_id) AS total_doctors,
        SUM(CASE WHEN a.discharge_time IS NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0) * 100 AS occupancy_rate
      FROM admissions a
      LEFT JOIN beds b ON a.bed_id = b.bed_id
      LEFT JOIN doctors d ON a.attending_doctor_id = d.doctor_id
      {where_clause}
    """

    with engine.connect() as conn:
        row = dict(conn.execute(text(sql), params).mappings().first() or {})

    # Add per-doctor workload
    sql_doctors = f"""
      SELECT d.doctor_id, d.name, d.specialty,
             COUNT(a.admission_id) AS active_patients
      FROM doctors d
      LEFT JOIN admissions a
        ON d.doctor_id = a.attending_doctor_id
       AND a.discharge_time IS NULL
      GROUP BY d.doctor_id, d.name, d.specialty
      ORDER BY active_patients DESC
    """
    with engine.connect() as conn:
        doctors = [dict(r) for r in conn.execute(text(sql_doctors)).mappings()]

    return {
        "summary": row,
        "doctors": doctors
    }

# Admissions time series (hour/day)
@app.get("/admissions/series")
def admissions_series(
    start: Optional[str] = None,
    end: Optional[str] = None,
    granularity: str = "day",   # "hour" or "day"
    ward_ids: Optional[str] = None,
    doctor_ids: Optional[str] = None,
    status: str = "all"
):
    wids = parse_csv_ints(ward_ids)
    dids = parse_csv_ints(doctor_ids)

    bucket = "DATE(a.admission_time)" if granularity == "day" else "DATE_FORMAT(a.admission_time, '%Y-%m-%d %H:00:00')"

    clauses, params = [], {}
    dc, dp = build_date_clause(start, end, "a.admission_time")
    clauses += dc; params.update(dp)
    if wids:
        wi, wp = build_in_clause("b.ward_id", wids, "w3"); clauses.append(wi); params.update(wp)
    if dids:
        di, dp2 = build_in_clause("a.attending_doctor_id", dids, "d3"); clauses.append(di); params.update(dp2)
    if status == "active":
        clauses.append("a.discharge_time IS NULL")
    elif status == "discharged":
        clauses.append("a.discharge_time IS NOT NULL")
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
      SELECT {bucket} AS bucket,
             COUNT(*) AS admissions
      FROM admissions a
      LEFT JOIN beds b ON a.bed_id=b.bed_id
      {where_sql}
      GROUP BY bucket
      ORDER BY bucket
    """
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), params).mappings()]
    return {"series": rows}

# Ward utilization (by current bed flags)
@app.get("/wards/utilization")
def ward_utilization(status: str = "all"):
    sql = """
      SELECT w.ward_id, w.ward_name, w.capacity,
             COUNT(b.bed_id) AS configured_beds,
             SUM(CASE WHEN b.is_occupied=1 THEN 1 ELSE 0 END) AS occupied
      FROM wards w
      LEFT JOIN beds b ON w.ward_id=b.ward_id
      GROUP BY w.ward_id, w.ward_name, w.capacity
      ORDER BY w.ward_id
    """
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql)).mappings()]

    for r in rows:
        denom = r["configured_beds"] or r["capacity"] or 0
        r["occupancy_rate"] = round((r["occupied"]/denom)*100, 1) if denom else 0

    return {"wards": rows}


# Doctor workload snapshot
@app.get("/doctors/workload")
def doctor_workload(doctor_ids: Optional[str] = None):
    dids = parse_csv_ints(doctor_ids)
    where_sql, params = "", {}
    if dids:
        where_sql, params = build_in_clause("d.doctor_id", dids, "d4")
        where_sql = "WHERE " + where_sql

    sql = f"""
      SELECT d.doctor_id, d.name, d.specialty,
             COUNT(a.admission_id) AS active_patients
      FROM doctors d
      LEFT JOIN admissions a
        ON d.doctor_id = a.attending_doctor_id
       AND a.discharge_time IS NULL
      {where_sql}
      GROUP BY d.doctor_id, d.name, d.specialty
      ORDER BY d.doctor_id
    """

    with engine.connect() as conn:
        rows = [dict(r) for r in]()
