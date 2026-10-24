"""End-to-end smoke test of the tool pipeline (no API key needed).

    python test_flow.py
"""
import os
import tempfile
from datetime import timedelta
from pathlib import Path

os.environ["AMC_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["OFFLINE_MODE"] = "1"

from PIL import Image  # noqa: E402

import agent  # noqa: E402
import db  # noqa: E402
import geotag  # noqa: E402
import tools  # noqa: E402

db.init_db(reset=True)
tmp = Path(tempfile.mkdtemp())


def make_photo(name, lat=None, lon=None) -> str:
    p = tmp / name
    Image.new("RGB", (64, 64), (90, 90, 90)).save(p)
    if lat is not None:
        p = geotag.geotag(p, lat, lon)
    return tools.save_upload(p.read_bytes(), name)


# 1. Ward lookup
assert tools.lookup_ward(area_name="near Vastrapur lake")["ward_name"] == "Bodakdev"
assert tools.lookup_ward(area_name="CG road")["ward_name"] == "Navrangpura"
assert tools.lookup_ward(area_name="navrangpur")["ward_name"] == "Navrangpura"      # typo
assert tools.lookup_ward(lat=22.998, lon=72.603)["ward_name"] == "Maninagar"
assert not tools.lookup_ward(lat=22.30, lon=70.80)["found"]                         # Rajkot: outside AMC
assert not tools.lookup_ward(area_name="Hogwarts")["found"]
print("ward lookup ok")

# 2. Department lookup
d = tools.lookup_department("streetlight", "W09")
assert d["dept_code"] == "LGT" and "North West" in d["officer_designation"]
assert tools.lookup_department("other", "W09")["dept_code"] == "GEN"
print("department lookup ok")

# 3. Photo WITH GPS -> filed in one shot
a = agent.OfflineAgent("user1")
img = make_photo("pothole_road.jpg", 23.0401, 72.5102)
assert tools.extract_photo_location(img)["has_location"]
reply, trace = a.run("", image_id=img)
assert [t["tool"] for t in trace] == ["analyze_image", "extract_photo_location", "lookup_ward",
                                      "lookup_department", "create_complaint"], trace
tid = trace[-1]["result"]["tracking_id"]
assert "Bodakdev" in reply and tid in reply
print("photo+GPS flow ok:", tid)

# 4. Photo WITHOUT GPS -> agent asks for area -> user types it
img2 = make_photo("garbage_pile.jpg")
reply, trace = a.run("", image_id=img2)
assert "Which area" in reply
reply, trace = a.run("near Kankaria lake")
assert trace[-1]["tool"] == "create_complaint" and "Maninagar" in reply
print("photo without GPS + typed area ok")

# 5. Status, with demo clock fast-forwarded 4 minutes -> IN_PROGRESS
conn = db.connect()
old = (tools.now() - timedelta(minutes=4)).isoformat()
conn.execute("UPDATE complaints SET created_at = ? WHERE tracking_id = ?", (old, tid))
conn.commit()
reply, trace = a.run(f"what's the status of {tid}?")
s = trace[-1]["result"]
assert s["status"] == "IN_PROGRESS" and [e["status"] for e in s["timeline"]] == ["FILED", "ASSIGNED", "IN_PROGRESS"]
print("status ok:", s["status"])
reply, _ = a.run("what's the status?")   # no ID -> latest complaint (the garbage one)
assert "Solid Waste" in reply

# 6. Duplicate report from another citizen 50 m away -> merged
b = agent.OfflineAgent("user2")
reply, trace = b.run("", image_id=make_photo("pothole2.jpg", 23.0404, 72.5104))
assert trace[-1]["result"].get("duplicate") and trace[-1]["result"]["tracking_id"] == tid
assert tools.list_my_complaints("user2")["count"] == 1
print("duplicate merge ok")

# 7. Overdue -> escalate
conn.execute("UPDATE complaints SET due_at = ?, created_at = ? WHERE tracking_id != ?",
             ((tools.now() - timedelta(days=1)).isoformat(), tools.now().isoformat(), tid))
conn.commit()
os.environ["FAST_FORWARD"] = "0"
reply, _ = a.run("status")
assert "overdue" in reply
reply, trace = a.run("please escalate")
assert trace[-1]["result"]["escalated"]
print("escalation ok")

# 8. Text-only report
reply, trace = a.run("broken streetlight near Iscon")
assert trace[-1]["result"]["created"] and "Jodhpur" in reply
print(f"\nAll checks passed. {tools.list_my_complaints('user1')['count']} complaints for user1.")
