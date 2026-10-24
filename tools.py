"""The agent's tools: image analysis -> photo GPS -> ward lookup -> department lookup
-> ticket creation -> status fetch (+ list and escalate).

Every tool takes plain JSON-able arguments and returns a JSON-able dict, so the same
functions serve the Gemini agent, the offline fallback agent and the tests.
"""
import json
import math
import os
import random
import re
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches
from pathlib import Path

from PIL import Image

import db

IST = timezone(timedelta(hours=5, minutes=30))
UPLOAD_DIR = db.BASE / "data" / "uploads"

ISSUE_TYPES = [
    "pothole", "damaged_road", "broken_footpath", "garbage", "overflowing_bin",
    "dead_animal", "streetlight", "water_logging", "blocked_drain", "sewage_overflow",
    "open_manhole", "water_leakage", "other",
]
STAGES = ["FILED", "ASSIGNED", "IN_PROGRESS", "RESOLVED"]
OUTSIDE_AMC_KM = 6.0          # farther than this from every ward centroid = outside AMC
DUPLICATE_RADIUS_M = 150

WORK_NOTES = {
    "RDB": "Road repair crew dispatched; patching work scheduled.",
    "SWM": "Sanitation vehicle dispatched to the spot.",
    "LGT": "Electrician team assigned to replace/repair the fitting.",
    "SWD": "Dewatering pump deployed; drain line being cleared.",
    "SEW": "Jetting machine dispatched to clear the sewer line.",
    "WTR": "Water supply team inspecting the leaking line.",
    "GEN": "Ward office is reviewing the grievance.",
}


def now() -> datetime:
    return datetime.now(IST)


def _stage_offsets() -> list[timedelta]:
    """Demo clock: minutes after filing at which each stage is reached."""
    m = float(os.getenv("DEMO_STAGE_MINUTES", "1"))
    return [timedelta(minutes=x * m) for x in (0, 1, 3, 6)]


def _fast_forward_enabled() -> bool:
    return os.getenv("FAST_FORWARD", "1") == "1"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def image_path(image_id: str) -> Path:
    matches = [p for p in UPLOAD_DIR.glob(f"{image_id}.*") if p.suffix != ".name"]
    if not matches:
        raise FileNotFoundError(f"No uploaded image with id '{image_id}'")
    return matches[0]


def save_upload(data: bytes, filename: str) -> str:
    """Store an uploaded photo and return its image_id."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower() or ".jpg"
    image_id = f"img_{now():%H%M%S}_{random.randint(1000, 9999)}"
    (UPLOAD_DIR / f"{image_id}{ext}").write_bytes(data)
    # Remember the original name; the offline analyzer uses it as a hint.
    (UPLOAD_DIR / f"{image_id}.name").write_text(filename)
    return image_id


# --------------------------------------------------------------------------- #
# Tool 1: image analysis
# --------------------------------------------------------------------------- #
VISION_PROMPT = f"""You are the intake officer of the Ahmedabad Municipal Corporation.
Look at this citizen's photo and classify the civic problem in it.
Return ONLY a JSON object with these keys:
  "is_civic_issue": true/false (false for selfies, documents, unrelated photos),
  "issue_type": one of {ISSUE_TYPES},
  "severity": "low" | "medium" | "high"  (high = safety risk, e.g. deep pothole on a busy road, live wires, flooding),
  "description": one or two plain sentences a municipal worker can act on,
  "visible_landmarks": any shop names, signboards or landmarks readable in the photo, or "",
  "confidence": number between 0 and 1
"""


def analyze_image(image_id: str) -> dict:
    """Classify the civic issue in an uploaded photo."""
    path = image_path(image_id)
    if os.getenv("GEMINI_API_KEY") and os.getenv("OFFLINE_MODE", "0") != "1":
        try:
            return _analyze_with_gemini(path)
        except Exception as e:  # keep the demo alive if the vision call fails
            result = _analyze_offline(path)
            result["warning"] = f"Gemini vision failed ({type(e).__name__}); used offline guess."
            return result
    return _analyze_offline(path)


def _analyze_with_gemini(path: Path) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    mime = Image.MIME.get(Image.open(path).format, "image/jpeg")
    resp = client.models.generate_content(
        model=os.getenv("GEMINI_VISION_MODEL", os.getenv("GEMINI_MODEL", "gemini-flash-latest")),
        contents=[types.Part.from_bytes(data=path.read_bytes(), mime_type=mime), VISION_PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
    )
    data = json.loads(re.sub(r"^```(json)?|```$", "", resp.text.strip()).strip())
    if data.get("issue_type") not in ISSUE_TYPES:
        data["issue_type"] = "other"
    data["source"] = "gemini-vision"
    return data


OFFLINE_KEYWORDS = {
    "pothole": ["pothole", "pot_hole", "khada", "road", "crack"],
    "garbage": ["garbage", "trash", "waste", "kachra", "dump", "litter"],
    "streetlight": ["streetlight", "street_light", "lamp", "light", "pole"],
    "water_logging": ["waterlog", "water_log", "flood", "logging", "rain", "puddle"],
    "sewage_overflow": ["sewage", "gutter", "sewer"],
    "open_manhole": ["manhole"],
    "water_leakage": ["leak", "pipe"],
}


def _analyze_offline(path: Path) -> dict:
    """No API key: guess from the original filename so the pipeline still runs."""
    name_file = path.with_suffix(".name")
    name = (name_file.read_text() if name_file.exists() else path.name).lower()
    for issue, words in OFFLINE_KEYWORDS.items():
        if any(w in name for w in words):
            return {"is_civic_issue": True, "issue_type": issue, "severity": "medium",
                    "description": f"Reported {issue.replace('_', ' ')} (offline mock analysis).",
                    "visible_landmarks": "", "confidence": 0.5, "source": "offline-mock"}
    return {"is_civic_issue": True, "issue_type": "other", "severity": "medium",
            "description": "Civic issue reported by citizen (offline mock analysis could not classify it).",
            "visible_landmarks": "", "confidence": 0.2, "source": "offline-mock"}


# --------------------------------------------------------------------------- #
# Tool 2: photo location (EXIF GPS)
# --------------------------------------------------------------------------- #
def extract_photo_location(image_id: str) -> dict:
    """Read GPS coordinates from the photo's EXIF data, if the phone saved them."""
    try:
        exif = Image.open(image_path(image_id)).getexif()
        gps = exif.get_ifd(0x8825)
    except Exception as e:
        return {"has_location": False, "reason": f"Could not read EXIF: {e}"}
    if not gps or 2 not in gps or 4 not in gps:
        return {"has_location": False,
                "reason": "Photo has no GPS data (location was off, or it was stripped on upload). Ask the user for the area name."}

    def to_deg(dms, ref):
        d, m, s = (float(x) for x in dms)
        val = d + m / 60 + s / 3600
        return -val if ref in ("S", "W") else val

    lat = to_deg(gps[2], gps.get(1, "N"))
    lon = to_deg(gps[4], gps.get(3, "E"))
    return {"has_location": True, "lat": round(lat, 6), "lon": round(lon, 6)}


# --------------------------------------------------------------------------- #
# Tool 3: ward lookup
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def lookup_ward(lat: float | None = None, lon: float | None = None, area_name: str | None = None) -> dict:
    """Find the AMC ward from GPS coordinates (preferred) or a typed area/landmark name."""
    conn = db.connect()
    wards = [dict(r) for r in conn.execute(
        "SELECT w.*, z.name AS zone_name FROM wards w JOIN zones z ON z.code = w.zone_code")]
    conn.close()

    def pack(w, **extra):
        return {"found": True, "ward_id": w["id"], "ward_name": w["name"],
                "zone": w["zone_name"], "zone_code": w["zone_code"], **extra}

    if lat is not None and lon is not None:
        best = min(wards, key=lambda w: haversine_km(lat, lon, w["lat"], w["lon"]))
        dist = haversine_km(lat, lon, best["lat"], best["lon"])
        if dist > OUTSIDE_AMC_KM:
            return {"found": False, "reason": f"Location is {dist:.1f} km from the nearest AMC ward; "
                                              "it looks outside AMC limits. Ask the user to confirm the area."}
        return pack(best, matched_by="gps", distance_km=round(dist, 2))

    if area_name:
        q = _norm(area_name)
        # 1) alias appears in the text (longest alias wins: "vastrapur lake" over "vastrapur")
        hits = [(len(a), w) for w in wards for a in json.loads(w["aliases"]) if re.search(rf"\b{re.escape(a)}\b", q)]
        if hits:
            return pack(max(hits, key=lambda h: h[0])[1], matched_by="area_name")
        # 2) fuzzy match for typos ("navrangpur", "bodakdeo")
        alias_map = {a: w for w in wards for a in json.loads(w["aliases"])}
        for token in [q] + q.split():
            close = get_close_matches(token, alias_map.keys(), n=1, cutoff=0.8)
            if close:
                return pack(alias_map[close[0]], matched_by="fuzzy_area_name", interpreted_as=close[0])
        return {"found": False, "reason": f"'{area_name}' did not match any AMC ward or known area. "
                                          "Ask for a nearby landmark or locality name."}

    return {"found": False, "reason": "Need either lat/lon or area_name."}


# --------------------------------------------------------------------------- #
# Tool 4: department lookup
# --------------------------------------------------------------------------- #
def lookup_department(issue_type: str, ward_id: str) -> dict:
    """Pick the responsible AMC department and the zonal officer for an issue in a ward."""
    conn = db.connect()
    ward = conn.execute("SELECT * FROM wards WHERE id = ?", (ward_id,)).fetchone()
    if not ward:
        conn.close()
        return {"found": False, "reason": f"Unknown ward_id {ward_id}"}
    dept = None
    for d in conn.execute("SELECT * FROM departments"):
        if issue_type in json.loads(d["issues"]):
            dept = d
            break
    dept = dept or conn.execute("SELECT * FROM departments WHERE code = 'GEN'").fetchone()
    officer = conn.execute("SELECT * FROM officers WHERE zone_code = ? AND dept_code = ?",
                           (ward["zone_code"], dept["code"])).fetchone()
    conn.close()
    return {"found": True, "dept_code": dept["code"], "dept_name": dept["name"],
            "sla_days": dept["sla_days"], "officer_designation": officer["designation"],
            "officer_phone": officer["phone"]}


# --------------------------------------------------------------------------- #
# Tool 5: ticket creation
# --------------------------------------------------------------------------- #
def _new_tracking_id(conn, ward_id: str) -> str:
    while True:
        tid = f"AMC-{now():%y%m%d}-{ward_id}-{random.randint(1000, 9999)}"
        if not conn.execute("SELECT 1 FROM complaints WHERE tracking_id = ?", (tid,)).fetchone():
            return tid


def create_complaint(user_id: str, issue_type: str, severity: str, description: str,
                     ward_id: str, dept_code: str, lat: float | None = None, lon: float | None = None,
                     landmark: str | None = None, image_id: str | None = None) -> dict:
    """File a complaint in the mock AMC system. Merges into an open duplicate nearby if one exists."""
    conn = db.connect()
    if not conn.execute("SELECT 1 FROM wards WHERE id = ?", (ward_id,)).fetchone():
        return {"created": False, "reason": f"Unknown ward_id {ward_id}"}
    dept = conn.execute("SELECT * FROM departments WHERE code = ?", (dept_code,)).fetchone()
    if not dept:
        return {"created": False, "reason": f"Unknown dept_code {dept_code}"}

    # Duplicate check: same issue, same ward, still open, within 150 m.
    if lat is not None and lon is not None:
        for c in conn.execute("""SELECT * FROM complaints WHERE ward_id = ? AND issue_type = ?
                                 AND status != 'RESOLVED' AND lat IS NOT NULL""", (ward_id, issue_type)):
            if haversine_km(lat, lon, c["lat"], c["lon"]) * 1000 <= DUPLICATE_RADIUS_M:
                conn.execute("UPDATE complaints SET upvotes = upvotes + 1 WHERE tracking_id = ?", (c["tracking_id"],))
                conn.execute("INSERT INTO complaint_followers VALUES (?, ?)", (c["tracking_id"], user_id))
                conn.execute("INSERT INTO complaint_events (tracking_id, status, note, at) VALUES (?, ?, ?, ?)",
                             (c["tracking_id"], c["status"], "Another citizen reported the same issue; priority raised.",
                              now().isoformat()))
                conn.commit()
                conn.close()
                return {"created": False, "duplicate": True, "tracking_id": c["tracking_id"],
                        "upvotes": c["upvotes"] + 1, "status": c["status"],
                        "message": "An open complaint for this exact issue already exists within 150 m. "
                                   "The user was added as a supporter instead of filing a duplicate."}

    zone = conn.execute("SELECT zone_code FROM wards WHERE id = ?", (ward_id,)).fetchone()[0]
    officer = conn.execute("SELECT * FROM officers WHERE zone_code = ? AND dept_code = ?", (zone, dept_code)).fetchone()
    created = now()
    sla = dept["sla_days"] - (1 if severity == "high" and dept["sla_days"] > 1 else 0)
    due = created + timedelta(days=sla)
    tid = _new_tracking_id(conn, ward_id)
    conn.execute("""INSERT INTO complaints (tracking_id, user_id, issue_type, severity, description, ward_id,
                    dept_code, officer_id, lat, lon, landmark, image_path, status, created_at, due_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'FILED', ?, ?)""",
                 (tid, user_id, issue_type, severity, description, ward_id, dept_code, officer["id"], lat, lon,
                  landmark, str(image_path(image_id)) if image_id else None, created.isoformat(), due.isoformat()))
    conn.execute("INSERT INTO complaint_events (tracking_id, status, note, at) VALUES (?, 'FILED', ?, ?)",
                 (tid, "Complaint registered via citizen app.", created.isoformat()))
    conn.commit()
    conn.close()
    return {"created": True, "tracking_id": tid, "status": "FILED", "dept_name": dept["name"],
            "officer_designation": officer["designation"], "sla_days": sla,
            "expected_resolution_by": due.strftime("%d %b %Y")}


# --------------------------------------------------------------------------- #
# Tool 6: status fetch
# --------------------------------------------------------------------------- #
def _advance_by_clock(conn, c) -> None:
    """Demo-only: move a complaint along its lifecycle as minutes pass."""
    if not _fast_forward_enabled() or c["status"] in ("RESOLVED",):
        return
    created = datetime.fromisoformat(c["created_at"])
    elapsed = now() - created
    current = STAGES.index(c["status"]) if c["status"] in STAGES else 0
    for i in range(current + 1, len(STAGES)):
        if elapsed >= _stage_offsets()[i]:
            _add_stage(conn, c, STAGES[i], created + _stage_offsets()[i])


def _add_stage(conn, c, stage: str, at: datetime) -> None:
    officer = conn.execute("SELECT designation FROM officers WHERE id = ?", (c["officer_id"],)).fetchone()
    note = {
        "ASSIGNED": f"Assigned to {officer['designation'] if officer else 'zonal officer'}.",
        "IN_PROGRESS": WORK_NOTES.get(c["dept_code"], "Work in progress."),
        "RESOLVED": "Work completed. Citizen asked to confirm the fix.",
    }[stage]
    conn.execute("UPDATE complaints SET status = ? WHERE tracking_id = ?", (stage, c["tracking_id"]))
    conn.execute("INSERT INTO complaint_events (tracking_id, status, note, at) VALUES (?, ?, ?, ?)",
                 (c["tracking_id"], stage, note, at.isoformat()))


def advance_status(tracking_id: str) -> dict:
    """Officer console: push a complaint to its next stage (used by the demo sidebar)."""
    conn = db.connect()
    c = conn.execute("SELECT * FROM complaints WHERE tracking_id = ?", (tracking_id,)).fetchone()
    if not c or c["status"] == "RESOLVED":
        conn.close()
        return {"ok": False}
    nxt = STAGES[STAGES.index(c["status"]) + 1] if c["status"] in STAGES else "ASSIGNED"
    _add_stage(conn, c, nxt, now())
    conn.commit()
    conn.close()
    return {"ok": True, "status": nxt}


def _user_complaint_ids(conn, user_id: str) -> list[str]:
    rows = conn.execute("""SELECT tracking_id, created_at FROM complaints WHERE user_id = ?
                           UNION SELECT c.tracking_id, c.created_at FROM complaints c
                           JOIN complaint_followers f ON f.tracking_id = c.tracking_id WHERE f.user_id = ?
                           ORDER BY created_at DESC""", (user_id, user_id)).fetchall()
    return [r[0] for r in rows]


def get_complaint_status(user_id: str, tracking_id: str | None = None) -> dict:
    """Current status + timeline of a complaint. Without an ID, returns the user's latest complaint."""
    conn = db.connect()
    if not tracking_id:
        ids = _user_complaint_ids(conn, user_id)
        if not ids:
            conn.close()
            return {"found": False, "reason": "This user has not filed any complaints yet."}
        tracking_id = ids[0]
    tracking_id = tracking_id.strip().upper()
    c = conn.execute("SELECT * FROM complaints WHERE tracking_id = ?", (tracking_id,)).fetchone()
    if not c:
        conn.close()
        return {"found": False, "reason": f"No complaint with tracking ID {tracking_id}."}
    _advance_by_clock(conn, c)
    conn.commit()
    c = conn.execute("""SELECT c.*, w.name AS ward_name, d.name AS dept_name, o.designation, o.phone
                        FROM complaints c JOIN wards w ON w.id = c.ward_id
                        JOIN departments d ON d.code = c.dept_code
                        LEFT JOIN officers o ON o.id = c.officer_id
                        WHERE c.tracking_id = ?""", (tracking_id,)).fetchone()
    events = conn.execute("SELECT status, note, at FROM complaint_events WHERE tracking_id = ? ORDER BY id",
                          (tracking_id,)).fetchall()
    conn.close()
    due = datetime.fromisoformat(c["due_at"])
    return {
        "found": True, "tracking_id": c["tracking_id"], "status": c["status"],
        "issue_type": c["issue_type"], "description": c["description"], "ward": c["ward_name"],
        "department": c["dept_name"], "officer": c["designation"], "officer_phone": c["phone"],
        "supporters": c["upvotes"], "filed_on": datetime.fromisoformat(c["created_at"]).strftime("%d %b %Y, %I:%M %p"),
        "expected_resolution_by": due.strftime("%d %b %Y"),
        "overdue": c["status"] != "RESOLVED" and now() > due,
        "timeline": [{"status": e["status"], "note": e["note"],
                      "at": datetime.fromisoformat(e["at"]).strftime("%d %b, %I:%M %p")} for e in events],
    }


def list_my_complaints(user_id: str) -> dict:
    """All complaints this user filed or supports, newest first."""
    conn = db.connect()
    ids = _user_complaint_ids(conn, user_id)
    conn.close()
    items = []
    for tid in ids:
        s = get_complaint_status(user_id, tid)
        items.append({k: s[k] for k in ("tracking_id", "issue_type", "ward", "status", "filed_on", "overdue")})
    return {"count": len(items), "complaints": items}


def escalate_complaint(user_id: str, tracking_id: str, reason: str = "") -> dict:
    """Send a reminder / escalate an unresolved complaint to the zonal Deputy Commissioner."""
    status = get_complaint_status(user_id, tracking_id)
    if not status.get("found"):
        return status
    if status["status"] == "RESOLVED":
        return {"escalated": False, "reason": "Complaint is already resolved."}
    conn = db.connect()
    zone = conn.execute("""SELECT z.name FROM complaints c JOIN wards w ON w.id = c.ward_id
                           JOIN zones z ON z.code = w.zone_code WHERE c.tracking_id = ?""",
                        (status["tracking_id"],)).fetchone()[0]
    note = f"Escalated by citizen to Deputy Municipal Commissioner, {zone}." + (f" Reason: {reason}" if reason else "")
    conn.execute("INSERT INTO complaint_events (tracking_id, status, note, at) VALUES (?, ?, ?, ?)",
                 (status["tracking_id"], status["status"], note, now().isoformat()))
    conn.commit()
    conn.close()
    return {"escalated": True, "tracking_id": status["tracking_id"], "escalated_to": f"Deputy Municipal Commissioner, {zone}",
            "was_overdue": status["overdue"]}


# --------------------------------------------------------------------------- #
# Registry + declarations for the LLM
# --------------------------------------------------------------------------- #
# Tools that need the logged-in user get user_id injected by the agent, never from the model.
USER_SCOPED = {"create_complaint", "get_complaint_status", "list_my_complaints", "escalate_complaint"}

TOOL_FUNCS = {f.__name__: f for f in (
    analyze_image, extract_photo_location, lookup_ward, lookup_department,
    create_complaint, get_complaint_status, list_my_complaints, escalate_complaint)}

TOOL_DECLARATIONS = [
    {"name": "analyze_image",
     "description": "Classify the civic issue visible in a citizen's uploaded photo. Always call this first when a photo is attached.",
     "parameters": {"type": "object", "properties": {
         "image_id": {"type": "string", "description": "ID of the uploaded photo, e.g. img_172301_4821"}},
         "required": ["image_id"]}},
    {"name": "extract_photo_location",
     "description": "Read GPS coordinates saved in the photo's EXIF metadata. Call right after analyze_image.",
     "parameters": {"type": "object", "properties": {
         "image_id": {"type": "string"}}, "required": ["image_id"]}},
    {"name": "lookup_ward",
     "description": "Find the AMC ward and zone. Pass lat/lon from the photo when available, otherwise the area/landmark name the user typed.",
     "parameters": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"},
         "area_name": {"type": "string", "description": "Locality or landmark, e.g. 'Vastrapur lake' or 'near CG Road'"}}}},
    {"name": "lookup_department",
     "description": "Find the AMC department, zonal officer and SLA responsible for an issue type in a ward.",
     "parameters": {"type": "object", "properties": {
         "issue_type": {"type": "string", "enum": ISSUE_TYPES},
         "ward_id": {"type": "string"}}, "required": ["issue_type", "ward_id"]}},
    {"name": "create_complaint",
     "description": "File the complaint in the AMC system and get a tracking ID. Only call after ward and department are known.",
     "parameters": {"type": "object", "properties": {
         "issue_type": {"type": "string", "enum": ISSUE_TYPES},
         "severity": {"type": "string", "enum": ["low", "medium", "high"]},
         "description": {"type": "string"},
         "ward_id": {"type": "string"}, "dept_code": {"type": "string"},
         "lat": {"type": "number"}, "lon": {"type": "number"},
         "landmark": {"type": "string", "description": "Area/landmark the user gave, if any"},
         "image_id": {"type": "string"}},
         "required": ["issue_type", "severity", "description", "ward_id", "dept_code"]}},
    {"name": "get_complaint_status",
     "description": "Get the live status and timeline of a complaint. Omit tracking_id to get the user's most recent complaint.",
     "parameters": {"type": "object", "properties": {
         "tracking_id": {"type": "string", "description": "e.g. AMC-261024-W09-4821"}}}},
    {"name": "list_my_complaints",
     "description": "List all complaints the current user has filed or supports.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "escalate_complaint",
     "description": "Escalate / send a reminder on an unresolved complaint to the zonal Deputy Municipal Commissioner.",
     "parameters": {"type": "object", "properties": {
         "tracking_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["tracking_id"]}},
]


def call_tool(name: str, args: dict, user_id: str) -> dict:
    fn = TOOL_FUNCS.get(name)
    if not fn:
        return {"error": f"Unknown tool {name}"}
    args = dict(args or {})
    if name in USER_SCOPED:
        args["user_id"] = user_id
    try:
        return fn(**args)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
