from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import os
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")

app = FastAPI()

# -----------------------------
# Database Connection
# -----------------------------
DB_USER = "saitejhas"         # AlwaysData MySQL username
DB_PASS = "Saitejhas1610*"         # AlwaysData MySQL password
DB_HOST = "mysql-saitejhas.alwaysdata.net"  # Replace with your actual host from AlwaysData
DB_NAME = "saitejhas_hospital_db"

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

# -----------------------------
# Routes
# -----------------------------

@app.get("/")
def root():
    return {"message": "Hospital Analytics API is running 🚀"}

@app.get("/patients")
def get_patients():
    """Fetch all patients"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM patients"))
        rows = [dict(row) for row in result.mappings()]
    return {"patients": rows}

@app.get("/admissions")
def get_admissions():
    """Fetch all admissions"""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM admissions"))
        rows = [dict(row) for row in result.mappings()]
    return {"admissions": rows}

# Example Predictive Model Stub (replace later with ML model)
class PredictRequest(BaseModel):
    age: int
    symptoms: str

@app.post("/predict")
def predict_outcome(request: PredictRequest):
    """Dummy predictive model — replace with real ML later"""
    if request.age > 60:
        return {"risk": "High", "message": "Elderly patient, high monitoring required"}
    else:
        return {"risk": "Moderate", "message": "Standard monitoring"}
