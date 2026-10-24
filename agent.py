"""Two interchangeable agents with the same interface:

    reply, trace = agent.run(user_text, image_id=None)

* GeminiAgent  - Gemini decides which tools to call (real function calling loop).
* OfflineAgent - deterministic rule-based pipeline over the same tools, so the demo
                 still works with no API key / no internet.

`trace` is a list of {"tool", "args", "result"} so the UI can show the agent's work.
"""
import os
import re

import tools

SYSTEM_PROMPT = """You are "AMC Sahayak", a civic-complaint agent for the Ahmedabad Municipal Corporation (AMC).
You help citizens report potholes, garbage, broken streetlights, water logging and similar problems,
and you track complaints until they are fixed. You act through tools; never invent ward names,
departments, tracking IDs or statuses — they must come from tool results.

When the user attaches a photo (you will see "[photo attached: image_id=...]"):
  1. analyze_image(image_id). If is_civic_issue is false, politely say this doesn't look like a civic issue and stop.
  2. extract_photo_location(image_id).
  3. lookup_ward: use lat/lon if the photo has GPS; otherwise use the area/landmark the user typed.
     If you have neither, ASK the user for the area or a nearby landmark and wait. Do not guess.
     If the photo's GPS and a typed area both exist, prefer GPS.
  4. lookup_department(issue_type, ward_id).
  5. create_complaint with the analysis, ward, department, coordinates/landmark and image_id.
  6. Reply briefly: what you saw, ward + zone, department, the tracking ID (in bold), and expected resolution date.
     If create_complaint reports a duplicate, tell the user an open complaint already exists, give its ID,
     and say their report was added as support (raises priority).

A user can also report without a photo ("garbage pile near Kankaria") - then skip steps 1-2,
infer issue_type and severity from their words, and continue from step 3.

For "what's the status?" / "any update?" call get_complaint_status (omit tracking_id to get their latest).
Summarise the current stage, the latest timeline note, the officer, and whether it is overdue.
Offer escalate_complaint if it is overdue or the user is unhappy; call it only when they agree.
For "my complaints" call list_my_complaints.

Keep replies short and friendly, suited to a phone screen. Reply in the user's language
(English, Hindi or Gujarati), keeping tracking IDs and department names as-is."""

MAX_STEPS = 10


def _schema_for_gemini(schema: dict) -> dict:
    """JSON-schema dict -> Gemini Schema dict (upper-case types)."""
    out = {}
    for k, v in schema.items():
        if k == "type":
            out[k] = v.upper()
        elif k == "properties":
            out[k] = {p: _schema_for_gemini(s) for p, s in v.items()}
        else:
            out[k] = v
    return out


class GeminiAgent:
    def __init__(self, user_id: str):
        from google import genai
        from google.genai import types

        self.types = types
        self.user_id = user_id
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        decls = []
        for d in tools.TOOL_DECLARATIONS:
            params = d["parameters"]
            decls.append(types.FunctionDeclaration(
                name=d["name"], description=d["description"],
                parameters=types.Schema(**_schema_for_gemini(params)) if params.get("properties") else None))
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=decls)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )
        self.history = []

    def run(self, user_text: str, image_id: str | None = None):
        types = self.types
        text = user_text or ""
        if image_id:
            text = f"[photo attached: image_id={image_id}]\n{text or '(no message, just the photo)'}"
        self.history.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
        trace = []
        for _ in range(MAX_STEPS):
            resp = self.client.models.generate_content(model=self.model, contents=self.history, config=self.config)
            content = resp.candidates[0].content
            self.history.append(content)  # keep the model turn as-is (preserves thought signatures)
            calls = [p.function_call for p in (content.parts or []) if p.function_call]
            if not calls:
                return "".join(p.text for p in (content.parts or []) if p.text).strip(), trace
            responses = []
            for fc in calls:
                args = dict(fc.args or {})
                result = tools.call_tool(fc.name, args, self.user_id)
                trace.append({"tool": fc.name, "args": args, "result": result})
                responses.append(types.Part.from_function_response(name=fc.name, response=result))
            self.history.append(types.Content(role="user", parts=responses))
        return "Sorry, I couldn't finish that request. Please try again.", trace


# --------------------------------------------------------------------------- #
# Offline fallback
# --------------------------------------------------------------------------- #
TRACKING_RE = re.compile(r"AMC-\d{6}-W\d{2}-\d{4}", re.I)
TEXT_ISSUES = {
    "pothole": ["pothole", "khada", "khaddo", "crater", "road broken"],
    "garbage": ["garbage", "trash", "kachra", "waste", "dump"],
    "streetlight": ["streetlight", "street light", "light not working", "lamp", "dark street"],
    "water_logging": ["water logging", "waterlogging", "water logged", "flooded", "paani bharay"],
    "sewage_overflow": ["sewage", "gutter overflow", "drainage overflow"],
    "open_manhole": ["manhole"],
    "water_leakage": ["leak", "pipeline burst"],
}


def _issue_from_text(text: str) -> str | None:
    t = (text or "").lower()
    for issue, words in TEXT_ISSUES.items():
        if any(w in t for w in words):
            return issue
    return None


class OfflineAgent:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.pending = None  # {"analysis":..., "image_id":...} waiting for a location

    def _call(self, trace, name, **args):
        result = tools.call_tool(name, args, self.user_id)
        trace.append({"tool": name, "args": args, "result": result})
        return result

    def run(self, user_text: str, image_id: str | None = None):
        trace, text = [], (user_text or "").strip()
        low = text.lower()

        if image_id:
            analysis = self._call(trace, "analyze_image", image_id=image_id)
            if analysis.get("issue_type") == "other" and _issue_from_text(text):
                analysis["issue_type"] = _issue_from_text(text)
            loc = self._call(trace, "extract_photo_location", image_id=image_id)
            self.pending = {"analysis": analysis, "image_id": image_id,
                            "lat": loc.get("lat"), "lon": loc.get("lon")}
            if loc.get("has_location"):
                return self._finish(trace, self._call(trace, "lookup_ward", lat=loc["lat"], lon=loc["lon"]), None)
            if text:
                ward = self._call(trace, "lookup_ward", area_name=text)
                if ward.get("found"):
                    return self._finish(trace, ward, text)
            seen = analysis["issue_type"].replace("_", " ")
            return (f"I can see a **{seen}** in your photo, but it has no location data. "
                    "Which area or nearby landmark is this? (e.g. *Vastrapur lake*, *CG Road*)"), trace

        if self.pending and text and not TRACKING_RE.search(text) and "status" not in low:
            ward = self._call(trace, "lookup_ward", area_name=text)
            if ward.get("found"):
                return self._finish(trace, ward, text)
            return "I couldn't place that in an AMC ward. Could you give a nearby landmark or locality name?", trace

        if any(w in low for w in ("escalate", "remind", "follow up", "follow-up")):
            m = TRACKING_RE.search(text)
            tid = m.group(0) if m else (self._call(trace, "get_complaint_status").get("tracking_id"))
            if not tid:
                return "You don't have any complaints to escalate yet.", trace
            r = self._call(trace, "escalate_complaint", tracking_id=tid)
            if r.get("escalated"):
                return f"Escalated **{tid}** to the {r['escalated_to']}. I'll keep tracking it.", trace
            return f"Couldn't escalate: {r.get('reason', 'unknown error')}", trace

        if "my complaints" in low or "all complaints" in low or low in ("list", "history"):
            r = self._call(trace, "list_my_complaints")
            if not r["count"]:
                return "You haven't filed any complaints yet. Send a photo to start.", trace
            lines = [f"- **{c['tracking_id']}** · {c['issue_type'].replace('_', ' ')} · {c['ward']} · {c['status']}"
                     for c in r["complaints"]]
            return "Your complaints:\n" + "\n".join(lines), trace

        if TRACKING_RE.search(text) or any(w in low for w in ("status", "update", "progress", "kya hua", "shu thayu")):
            m = TRACKING_RE.search(text)
            s = self._call(trace, "get_complaint_status", **({"tracking_id": m.group(0)} if m else {}))
            return format_status(s), trace

        issue = _issue_from_text(text)
        if issue:
            ward = self._call(trace, "lookup_ward", area_name=text)
            self.pending = {"analysis": {"issue_type": issue, "severity": "medium",
                                         "description": text, "is_civic_issue": True},
                            "image_id": None, "lat": None, "lon": None}
            if ward.get("found"):
                return self._finish(trace, ward, text)
            return f"Got it — a **{issue.replace('_', ' ')}**. Which area or landmark is it near?", trace

        return ("Send me a photo of the problem (pothole, garbage, broken streetlight, water logging…) "
                "and I'll file it with the right AMC ward and department. "
                "You can also ask **what's the status?** anytime."), trace

    def _finish(self, trace, ward, landmark):
        p = self.pending
        if not ward.get("found"):
            return ward["reason"], trace
        a = p["analysis"]
        if not a.get("is_civic_issue", True):
            self.pending = None
            return "This photo doesn't look like a civic issue. Please send a photo of the problem.", trace
        dept = self._call(trace, "lookup_department", issue_type=a["issue_type"], ward_id=ward["ward_id"])
        args = dict(issue_type=a["issue_type"], severity=a.get("severity", "medium"),
                    description=a.get("description", ""), ward_id=ward["ward_id"], dept_code=dept["dept_code"])
        for k, v in (("lat", p["lat"]), ("lon", p["lon"]), ("landmark", landmark), ("image_id", p["image_id"])):
            if v is not None:
                args[k] = v
        r = self._call(trace, "create_complaint", **args)
        self.pending = None
        if r.get("duplicate"):
            return (f"This issue is already reported nearby as **{r['tracking_id']}** (status: {r['status']}). "
                    f"I've added your report as support — {r['upvotes']} citizens now back it, which raises its priority."), trace
        if not r.get("created"):
            return f"Couldn't file the complaint: {r.get('reason')}", trace
        return (f"Filed! I saw a **{a['issue_type'].replace('_', ' ')}** ({a.get('severity', 'medium')} severity).\n\n"
                f"- Ward: **{ward['ward_name']}** ({ward['zone']})\n"
                f"- Department: **{dept['dept_name']}**\n"
                f"- Assigned to: {dept['officer_designation']}\n"
                f"- Tracking ID: **{r['tracking_id']}**\n"
                f"- Expected resolution by: **{r['expected_resolution_by']}**\n\n"
                "Ask me *what's the status?* anytime."), trace


def format_status(s: dict) -> str:
    if not s.get("found"):
        return s.get("reason", "Complaint not found.")
    last = s["timeline"][-1]
    label = {"FILED": "📝 Filed", "ASSIGNED": "👷 Assigned", "IN_PROGRESS": "🚧 In progress",
             "RESOLVED": "✅ Resolved"}.get(s["status"], s["status"])
    msg = (f"**{s['tracking_id']}** — {label}\n\n"
           f"Latest: {last['note']} ({last['at']})\n\n"
           f"{s['department']}, {s['ward']} ward · {s['officer']} ({s['officer_phone']})\n\n"
           f"Expected by {s['expected_resolution_by']}")
    if s["overdue"]:
        msg += " — ⚠️ **overdue**. Say *escalate* and I'll raise it to the Deputy Commissioner."
    return msg


def make_agent(user_id: str):
    """Gemini if a key is configured, otherwise the offline agent."""
    if os.getenv("GEMINI_API_KEY") and os.getenv("OFFLINE_MODE", "0") != "1":
        return GeminiAgent(user_id)
    return OfflineAgent(user_id)
