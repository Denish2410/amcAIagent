"""Mock AMC (Ahmedabad Municipal Corporation) backend, stored in SQLite.

Nothing here talks to a real portal. The seed data lives in data/amc_seed.json.
"""
import json
import os
import sqlite3
from pathlib import Path

BASE = Path(__file__).parent
DB_PATH = Path(os.getenv("AMC_DB_PATH", BASE / "data" / "amc_mock.db"))
SEED_PATH = BASE / "data" / "amc_seed.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS zones (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wards (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    zone_code TEXT NOT NULL REFERENCES zones(code),
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    aliases TEXT NOT NULL              -- JSON list of lowercase area names
);
CREATE TABLE IF NOT EXISTS departments (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    issues TEXT NOT NULL,              -- JSON list of issue categories handled
    sla_days INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS officers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_code TEXT NOT NULL,
    dept_code TEXT NOT NULL,
    designation TEXT NOT NULL,
    phone TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaints (
    tracking_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    ward_id TEXT NOT NULL REFERENCES wards(id),
    dept_code TEXT NOT NULL REFERENCES departments(code),
    officer_id INTEGER REFERENCES officers(id),
    lat REAL,
    lon REAL,
    landmark TEXT,
    image_path TEXT,
    status TEXT NOT NULL,
    upvotes INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    due_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaint_followers (   -- citizens who re-reported the same issue
    tracking_id TEXT NOT NULL REFERENCES complaints(tracking_id),
    user_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaint_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tracking_id TEXT NOT NULL REFERENCES complaints(tracking_id),
    status TEXT NOT NULL,
    note TEXT NOT NULL,
    at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    conn = connect()
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM wards").fetchone()[0] == 0:
        _seed(conn)
    conn.commit()
    conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    seed = json.loads(SEED_PATH.read_text())
    conn.executemany("INSERT INTO zones VALUES (?, ?)", seed["zones"].items())
    conn.executemany(
        "INSERT INTO wards VALUES (?, ?, ?, ?, ?, ?)",
        [(w["id"], w["name"], w["zone"], w["lat"], w["lon"], json.dumps(w["aliases"]))
         for w in seed["wards"]],
    )
    conn.executemany(
        "INSERT INTO departments VALUES (?, ?, ?, ?)",
        [(d["code"], d["name"], json.dumps(d["issues"]), d["sla_days"]) for d in seed["departments"]],
    )
    # One mock officer per zone x department (designations only, no real people).
    rows = []
    for i, zone in enumerate(seed["zones"]):
        for j, dept in enumerate(seed["departments"]):
            rows.append((zone, dept["code"],
                         f"Assistant Engineer ({dept['code']}), {seed['zones'][zone]}",
                         f"079-2{i}{j}0-{1000 + 37 * (i * 7 + j)}"))
    conn.executemany(
        "INSERT INTO officers (zone_code, dept_code, designation, phone) VALUES (?, ?, ?, ?)", rows)


if __name__ == "__main__":
    init_db(reset=True)
    print(f"Mock AMC database created at {DB_PATH}")
