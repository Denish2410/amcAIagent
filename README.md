# AMC Sahayak — photo-to-complaint civic agent

Snap a pothole, garbage pile, dead streetlight or water logging. The agent works out what it is,
which Ahmedabad ward it's in, which AMC department owns it, files the complaint, and gives you a
tracking ID. Ask *"what's the status?"* later and it tells you — and escalates if it's overdue.

> The AMC backend is **mocked** (SQLite seeded from `data/amc_seed.json`). Ward centroids are
> approximate and IDs are invented. Nothing connects to a real portal.

## Run it (5 minutes)

```bash
pip install -r requirements.txt
cp .env.example .env          # paste your Gemini key into .env
python test_flow.py           # sanity check, no key needed
streamlit run app.py
```

No key or no internet? The app automatically switches to an **offline agent** that runs the
same tools with rule-based decisions, so the demo never dies on stage.

## How the agent works

```
photo ─► analyze_image ─► extract_photo_location ─► lookup_ward ─► lookup_department ─► create_complaint ─► tracking ID
          (Gemini vision)   (EXIF GPS)              (GPS → nearest ward,   (issue → dept,     (dedupe within 150 m,
                            no GPS? ask user ──────► or typed area name,    zone officer,       SLA-based due date)
                                                     fuzzy for typos)       SLA)
"what's the status?" ─► get_complaint_status ─► (overdue?) ─► escalate_complaint
```

Gemini drives the loop through real function calling (`agent.py → GeminiAgent`). Every tool call
and its result is shown in the chat under **🔧 Agent steps**, so judges can see the reasoning.

| Tool | What it does |
|---|---|
| `analyze_image` | Gemini vision → issue type, severity, description, landmarks; rejects non-civic photos |
| `extract_photo_location` | Reads GPS from EXIF |
| `lookup_ward` | Nearest ward centroid from GPS (flags locations outside AMC), or alias/fuzzy match on a typed area ("near Iscon" → Jodhpur ward) |
| `lookup_department` | Issue → department, zonal officer, SLA days |
| `create_complaint` | Writes the ticket; merges duplicates within 150 m and raises priority instead of double-filing |
| `get_complaint_status` | Live stage + timeline; no ID needed (defaults to your latest) |
| `list_my_complaints`, `escalate_complaint` | History, and escalation to the zonal Deputy Commissioner |

## 3-minute demo script

1. **Photo with GPS** — upload a pothole photo. Agent files it in one go: ward, department, tracking ID, due date. Open *Agent steps* to show the 5 tool calls.
2. **Photo without GPS** — upload a garbage photo. Agent asks for the area; type *"near Kankaria lake"* → filed in Maninagar ward, Solid Waste Management.
3. **Status** — ask *"what's the status?"*. With fast-forward on, the ticket moves Filed → Assigned (1 min) → In progress (3 min) → Resolved (6 min); or click **Next ▶** in the officer console to advance it on demand.
4. **Duplicate** — change the citizen ID in the sidebar and upload the same geotagged pothole: the agent attaches them to the existing ticket instead of filing a new one.
5. **Language** — ask *"મારી ફરિયાદનું શું થયું?"* (Gujarati) — Gemini replies in Gujarati.

### Preparing demo photos

Photos sent over WhatsApp or downloaded from the web usually have no GPS. Stamp a location in:

```bash
python geotag.py pothole.jpg --area "Vastrapur"     # writes pothole_geo.jpg
python geotag.py garbage.jpg --check                # shows what GPS a photo has
```

In offline mode the image "analysis" uses the filename (`pothole_*.jpg`, `garbage_*.jpg`, `streetlight_*.jpg`, `waterlogging_*.jpg`), so name demo photos accordingly as a backup.

## Files

- `app.py` — Streamlit chat UI, officer console, complaint map
- `agent.py` — Gemini function-calling loop + offline fallback agent
- `tools.py` — the tools and their declarations
- `db.py`, `data/amc_seed.json` — mock AMC: 7 zones, 33 wards, 7 departments, zonal officers
- `geotag.py` — add GPS to demo photos
- `test_flow.py` — end-to-end test of every path

## Ideas if you have time left

- WhatsApp bot front end (Twilio sandbox) — the agent interface is just `run(text, image_id)`.
- Before/after photo on resolution, verified by the same vision tool.
- Ward-level heatmap of open complaints for the corporator.
