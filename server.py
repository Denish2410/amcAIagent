"""FastAPI backend for AMC Sahayak Civic Complaint Agent.

Provides REST APIs for:
- Chat & photo submission to the civic agent (Gemini with offline fallback)
- Live complaint status & officer console
- Complaint lifecycle fast-forward and advancement
- Sample demo photos & static upload serving
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Load .env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import agent as agent_mod
import db
import geotag
import tools

# Initialize database
db.init_db()

app = FastAPI(
    title="AMC Sahayak API",
    description="Ahmedabad Municipal Corporation AI Civic Agent API",
    version="1.0.0"
)

# Enable CORS for React frontend (Vite default: http://localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory agent sessions: {user_id: {"agent": agent_instance, "fallback": fallback_instance}}
sessions = {}


def get_agent_for_user(user_id: str):
    offline = os.getenv("OFFLINE_MODE", "0") == "1" or not bool(os.getenv("GEMINI_API_KEY"))
    key = (user_id, offline)
    if user_id not in sessions or sessions[user_id].get("key") != key:
        sessions[user_id] = {
            "key": key,
            "agent": agent_mod.make_agent(user_id),
            "fallback": agent_mod.OfflineAgent(user_id)
        }
    return sessions[user_id]["agent"], sessions[user_id]["fallback"]


class ConfigUpdate(BaseModel):
    offline_mode: Optional[bool] = None
    fast_forward: Optional[bool] = None


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "AMC Sahayak API",
        "time": tools.now().isoformat()
    }


@app.get("/api/config")
def get_config():
    return {
        "offline_mode": os.getenv("OFFLINE_MODE", "0") == "1",
        "has_gemini_key": bool(os.getenv("GEMINI_API_KEY")),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        "fast_forward": os.getenv("FAST_FORWARD", "1") == "1",
        "demo_stage_minutes": os.getenv("DEMO_STAGE_MINUTES", "1")
    }


@app.post("/api/config")
def update_config(cfg: ConfigUpdate):
    if cfg.offline_mode is not None:
        os.environ["OFFLINE_MODE"] = "1" if cfg.offline_mode else "0"
        sessions.clear()  # reset session agents to apply change
    if cfg.fast_forward is not None:
        os.environ["FAST_FORWARD"] = "1" if cfg.fast_forward else "0"
    return get_config()


@app.post("/api/chat")
async def chat_endpoint(
    text: Optional[str] = Form(""),
    user_id: Optional[str] = Form("9876543210"),
    file: Optional[UploadFile] = File(None)
):
    """Submit a message or photo to the AMC Sahayak civic agent."""
    user_id = user_id.strip() if user_id else "9876543210"
    image_id = None
    original_filename = None

    if file and file.filename:
        content = await file.read()
        if content:
            original_filename = file.filename
            image_id = tools.save_upload(content, original_filename)

    agent_inst, fallback_inst = get_agent_for_user(user_id)

    used_fallback = False
    warning_msg = None
    try:
        reply, trace = agent_inst.run(text or "", image_id=image_id)
    except Exception as e:
        used_fallback = True
        reply, trace = fallback_inst.run(text or "", image_id=image_id)
        warning_msg = f"Gemini API returned error ({type(e).__name__}); seamlessly answered with the offline agent."

    return {
        "reply": reply,
        "trace": trace,
        "image_id": image_id,
        "filename": original_filename,
        "user_id": user_id,
        "used_fallback": used_fallback,
        "warning": warning_msg,
        "timestamp": tools.now().isoformat()
    }


@app.get("/api/complaints")
def list_complaints(user_id: Optional[str] = None, limit: int = 50):
    """Return all filed complaints with live timeline and SLA status."""
    conn = db.connect()
    query = """
        SELECT c.tracking_id, c.user_id, c.issue_type, c.severity, c.description,
               c.lat, c.lon, c.landmark, c.image_path, c.upvotes, c.created_at, c.due_at,
               w.id AS ward_id, w.name AS ward_name, z.name AS zone_name,
               d.code AS dept_code, d.name AS dept_name, d.sla_days,
               o.designation AS officer_designation, o.phone AS officer_phone
        FROM complaints c
        JOIN wards w ON w.id = c.ward_id
        JOIN zones z ON z.code = w.zone_code
        JOIN departments d ON d.code = c.dept_code
        LEFT JOIN officers o ON o.id = c.officer_id
    """
    params = []
    if user_id:
        query += " WHERE c.user_id = ?"
        params.append(user_id)
    query += " ORDER BY c.created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        c_dict = dict(r)
        # Calculate dynamic status with demo clock / fast forward
        status_info = tools.get_complaint_status(c_dict["tracking_id"], c_dict["user_id"])
        c_dict["status"] = status_info.get("status", "FILED")
        c_dict["timeline"] = status_info.get("timeline", [])
        c_dict["overdue"] = status_info.get("overdue", False)
        c_dict["expected_resolution_by"] = status_info.get("expected_resolution_by", c_dict["due_at"])
        results.append(c_dict)

    return {"complaints": results, "total": len(results)}


@app.post("/api/complaints/{tracking_id}/advance")
def advance_complaint_status(tracking_id: str):
    """Advance a complaint through its lifecycle (FILED -> ASSIGNED -> IN_PROGRESS -> RESOLVED)."""
    res = tools.advance_status(tracking_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("reason", "Cannot advance complaint"))
    return res


@app.post("/api/reset")
def reset_database():
    """Reset the mock database and clear agent sessions."""
    db.init_db(reset=True)
    sessions.clear()
    return {"success": True, "message": "AMC civic database has been reset to seed data."}


@app.get("/api/wards")
def list_wards():
    """List all Ahmedabad wards with coordinates and zone information."""
    conn = db.connect()
    rows = conn.execute("""
        SELECT w.id, w.name, w.lat, w.lon, w.aliases, z.code AS zone_code, z.name AS zone_name
        FROM wards w JOIN zones z ON z.code = w.zone_code
        ORDER BY w.name ASC
    """).fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"], "lat": r["lat"], "lon": r["lon"],
             "aliases": json.loads(r["aliases"]), "zone": r["zone_name"]} for r in rows]


@app.get("/api/departments")
def list_departments():
    """List AMC civic departments and their SLAs."""
    conn = db.connect()
    rows = conn.execute("SELECT code, name, issues, sla_days FROM departments ORDER BY name ASC").fetchall()
    conn.close()
    return [{"code": r["code"], "name": r["name"], "issues": json.loads(r["issues"]),
             "sla_days": r["sla_days"]} for r in rows]


@app.get("/api/uploads/{filename}")
def get_uploaded_image(filename: str):
    """Serve uploaded images."""
    p = tools.UPLOAD_DIR / filename
    if not p.exists():
        # Check by image_id
        try:
            p = tools.image_path(filename)
        except Exception:
            raise HTTPException(status_code=404, detail="Image not found")
    media_type = "image/jpeg"
    if p.suffix.lower() == ".png":
        media_type = "image/png"
    elif p.suffix.lower() == ".webp":
        media_type = "image/webp"
    return FileResponse(p, media_type=media_type)


@app.get("/api/samples")
def get_sample_issues():
    """Pre-configured demo test cases with description, issue type and pre-bundled photo."""
    samples_dir = db.BASE / "data" / "sample_assets"
    samples_dir.mkdir(parents=True, exist_ok=True)

    samples = [
        {
            "id": "pothole_bodakdev",
            "title": "Severe Pothole (with GPS)",
            "issue_type": "pothole",
            "has_gps": True,
            "location_name": "Bodakdev (Vastrapur Lake)",
            "filename": "pothole_vastrapur_geo.jpg",
            "description": "Deep crater on main road with EXIF GPS coordinates embedded (Bodakdev ward). Files in one shot!",
            "suggested_prompt": "Found this dangerous pothole on the road, please fix it ASAP."
        },
        {
            "id": "garbage_kankaria",
            "title": "Garbage Dump (No GPS)",
            "issue_type": "garbage",
            "has_gps": False,
            "location_name": "Maninagar (Kankaria)",
            "filename": "garbage_pile.jpg",
            "description": "Garbage pile without GPS. The agent will ask for location, then you type 'near Kankaria lake'.",
            "suggested_prompt": "There is a huge pile of garbage rotting here."
        },
        {
            "id": "streetlight_navrangpura",
            "title": "Broken Streetlight (with GPS)",
            "issue_type": "streetlight",
            "has_gps": True,
            "location_name": "Navrangpura (CG Road)",
            "filename": "streetlight_navrangpura_geo.jpg",
            "description": "Damaged pole and dark light fixture with Navrangpura GPS coordinates.",
            "suggested_prompt": "Streetlight has been broken for 3 days."
        },
        {
            "id": "waterlogging_usmanpura",
            "title": "Monsoon Water Logging (with GPS)",
            "issue_type": "water_logging",
            "has_gps": True,
            "location_name": "Usmanpura (Ashram Road)",
            "filename": "waterlogging_usmanpura_geo.jpg",
            "description": "Flooded street with embedded GPS coordinates.",
            "suggested_prompt": "Heavy water logging blocking traffic completely."
        }
    ]
    return {"samples": samples}


@app.get("/api/samples/{filename}")
def get_sample_image(filename: str):
    p = db.BASE / "data" / "sample_assets" / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Sample photo not found")
    return FileResponse(p, media_type="image/jpeg")


from fastapi.staticfiles import StaticFiles

# Mount static React frontend if built
dist_dir = Path(__file__).parent / "frontend" / "dist"
if dist_dir.exists():
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
