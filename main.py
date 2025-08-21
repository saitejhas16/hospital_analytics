from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import os
from fastapi.middleware.cors import CORSMiddleware
from datetime import date
from typing import Optional
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")

app = FastAPI()

# 👇 Add CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://saitejhas16.github.io",  # your GitHub Pages site
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
    # ✅ Default to 2018-08-18 → today
    if not start:
        start = "2018-08-18"
    if not end:
        end = str(date.today())   # YYYY-MM-DD format

    # ✅ Parse ward_ids and doctor_ids if passed
    ward_list = ward_ids.split(",") if ward_ids else []
    doctor_list = doctor_ids.split(",") if doctor_ids else []
    wids = parse_csv_ints(ward_ids)
    dids = parse_csv_ints(doctor_ids)

    with engine.connect() as conn:
        # TOTAL & OCCUPIED BEDS (by current bed flags, optionally filter by wards)
        bed_where, bed_params = [], {}
        if wids:
            bed_in, bed_in_params = build_in_clause("b.ward_id", wids, "wid")
            bed_where.append(bed_in)
            bed_params.update(bed_in_params)
        bed_where_sql = ("WHERE " + " AND ".join(bed_where)) if bed_where else ""
        bed_sql = f"""
            SELECT COUNT(*) AS total_beds,
                   SUM(CASE WHEN b.is_occupied=1 THEN 1 ELSE 0 END) AS occupied_beds
            FROM beds b
            {bed_where_sql}
        """
        beds_row = conn.execute(text(bed_sql), bed_params).mappings().first()
        total_beds = beds_row["total_beds"] or 0
        occupied_beds = beds_row["occupied_beds"] or 0
        occupancy_rate = (occupied_beds / total_beds) * 100 if total_beds else 0

        # DOCTORS ON DUTY / BUSY (optionally filter by doctor_ids)
        doc_where, doc_params = [], {}
        if dids:
            doc_in, doc_in_params = build_in_clause("d.doctor_id", dids, "did")
            doc_where.append(doc_in)
            doc_params.update(doc_in_params)
        doc_where_sql = ("WHERE " + " AND ".join(doc_where)) if doc_where else ""
        docs_sql = f"""
            SELECT SUM(CASE WHEN d.is_present=1 THEN 1 ELSE 0 END) AS doctors_present,
                   SUM(CASE WHEN d.is_busy=1 THEN 1 ELSE 0 END) AS doctors_busy,
                   COUNT(*) AS doctors_total
            FROM doctors d
            {doc_where_sql}
        """
        docs_row = conn.execute(text(docs_sql), doc_params).mappings().first()
        doctors_present = docs_row["doctors_present"] or 0
        doctors_busy = docs_row["doctors_busy"] or 0
        doctors_total = docs_row["doctors_total"] or 0

        # ADMISSIONS KPIs (filters by date, ward, doctor, status)
        adm_clauses, adm_params = [], {}
        # Date filter on admission_time by default
        date_clauses, date_params = build_date_clause(start, end, "a.admission_time")
        adm_clauses += date_clauses; adm_params.update(date_params)
        # Ward filter (via beds)
        if wids:
            ward_in, ward_params = build_in_clause("b.ward_id", wids, "w2")
            adm_clauses.append(ward_in); adm_params.update(ward_params)
        # Doctor filter
        if dids:
            doc_in2, doc_params2 = build_in_clause("a.attending_doctor_id", dids, "d2")
            adm_clauses.append(doc_in2); adm_params.update(doc_params2)
        # Status filter
        if status == "active":
            adm_clauses.append("a.discharge_time IS NULL")
        elif status == "discharged":
            adm_clauses.append("a.discharge_time IS NOT NULL")
        adm_where = ("WHERE " + " AND ".join(adm_clauses)) if adm_clauses else ""

        kpi_adm_sql = f"""
            SELECT
              SUM(CASE WHEN a.discharge_time IS NULL THEN 1 ELSE 0 END) AS active_admissions,
              SUM(CASE WHEN a.discharge_time IS NOT NULL THEN 1 ELSE 0 END) AS discharged_count,
              AVG(CASE WHEN a.discharge_time IS NOT NULL
                       THEN TIMESTAMPDIFF(HOUR, a.admission_time, a.discharge_time)
                       END) AS avg_los_hours
            FROM admissions a
            LEFT JOIN beds b ON a.bed_id = b.bed_id
            {adm_where}
        """
        adm_row = conn.execute(text(kpi_adm_sql), adm_params).mappings().first()
        active_adm = adm_row["active_admissions"] or 0
        discharged_count = adm_row["discharged_count"] or 0
        avg_los_hours = adm_row["avg_los_hours"] or 0
        avg_los_days = round(avg_los_hours/24, 2) if avg_los_hours else 0

        # Discharges today
        disch_clauses = adm_clauses.copy()
        # override to today if no start/end
        today_sql = "CURDATE()"
        disch_clauses = [c for c in disch_clauses if not c.startswith("a.admission_time")]
        disch_clauses.append("a.discharge_time IS NOT NULL")
        disch_clauses.append("DATE(a.discharge_time) = CURDATE()")
        disch_where = ("WHERE " + " AND ".join(disch_clauses)) if disch_clauses else "WHERE DATE(a.discharge_time)=CURDATE()"
        disch_sql = f"""
            SELECT COUNT(*) AS discharges_today
            FROM admissions a
            LEFT JOIN beds b ON a.bed_id=b.bed_id
            {disch_where}
        """
        disch_row = conn.execute(text(disch_sql), adm_params).mappings().first()
        discharges_today = disch_row["discharges_today"] or 0

        return {
            "beds": {
                "total": int(total_beds),
                "occupied": int(occupied_beds),
                "occupancy_rate": round(occupancy_rate, 1)
            },
            "admissions": {
                "active": int(active_adm),
                "discharged": int(discharged_count),
                "avg_length_of_stay_days": float(avg_los_days),
                "discharges_today": int(discharges_today)
            },
            "doctors": {
                "present": int(doctors_present),
                "busy": int(doctors_busy),
                "total": int(doctors_total)
            }
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
      SELECT d.doctor_id, d.name, d.specialty, d.is_present, d.is_busy
      FROM doctors d
      {where_sql}
      ORDER BY d.doctor_id
    """
    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(text(sql), params).mappings()]
    return {"doctors": rows}
