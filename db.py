"""
db.py — SQLite database module for city tourism videos and radio stations.

Provides CRUD operations and one-time migration helpers from the old JSON formats.
"""

import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "city_videos.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS city_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_name TEXT NOT NULL,
    state TEXT,
    full_name TEXT UNIQUE NOT NULL,
    youtube_id TEXT NOT NULL,
    title TEXT,
    duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rank INTEGER,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    full_name TEXT UNIQUE NOT NULL,
    population INTEGER,
    growth TEXT
);

CREATE TABLE IF NOT EXISTS radio_stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    frequency TEXT,
    type TEXT NOT NULL CHECK(type IN ('youtube', 'mp3')),
    source TEXT NOT NULL,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db():
    """Create the database and table if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def _get_conn():
    """Context manager that yields a connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_all_videos():
    """Return all city videos as a list of dicts."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, city_name, state, full_name, youtube_id, title, duration_seconds, created_at "
            "FROM city_videos ORDER BY full_name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_video_for_city(full_name):
    """Look up a video by city full_name (e.g. 'Columbus, OH'). Returns dict or None."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT youtube_id, title, duration_seconds FROM city_videos WHERE full_name = ?",
            (full_name,),
        ).fetchone()
    return dict(row) if row else None


def add_video(city_name, state, youtube_id, title=None, duration_seconds=None):
    """Insert a new city video. Returns the new record as a dict."""
    full_name = f"{city_name}, {state}" if state else city_name
    with _get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO city_videos (city_name, state, full_name, youtube_id, title, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (city_name, state, full_name, youtube_id, title, duration_seconds),
        )
        row = conn.execute("SELECT * FROM city_videos WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def update_video(video_id, **fields):
    """Update an existing video. Accepts any subset of: city_name, state, youtube_id, title, duration_seconds."""
    allowed = {"city_name", "state", "youtube_id", "title", "duration_seconds"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return None

    # If city_name or state changed, recompute full_name
    needs_full_name = "city_name" in updates or "state" in updates

    with _get_conn() as conn:
        if needs_full_name:
            # Fetch current values to fill in whichever wasn't provided
            current = conn.execute("SELECT city_name, state FROM city_videos WHERE id = ?", (video_id,)).fetchone()
            if not current:
                return None
            cn = updates.get("city_name", current["city_name"])
            st = updates.get("state", current["state"])
            updates["full_name"] = f"{cn}, {st}" if st else cn

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [video_id]
        conn.execute(f"UPDATE city_videos SET {set_clause} WHERE id = ?", values)
        row = conn.execute("SELECT * FROM city_videos WHERE id = ?", (video_id,)).fetchone()
    return dict(row) if row else None


def delete_video(video_id):
    """Delete a video by ID. Returns True if a row was deleted."""
    with _get_conn() as conn:
        cursor = conn.execute("DELETE FROM city_videos WHERE id = ?", (video_id,))
    return cursor.rowcount > 0


def import_from_json(json_path="data/city_videos.json"):
    """One-time migration: import entries from the old JSON file into SQLite.
    Returns the count of records imported."""
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    with _get_conn() as conn:
        for full_name, video in data.items():
            # Split "Columbus, OH" into city_name and state
            parts = full_name.split(", ", 1)
            city_name = parts[0]
            state = parts[1] if len(parts) > 1 else None

            try:
                conn.execute(
                    "INSERT OR IGNORE INTO city_videos (city_name, state, full_name, youtube_id, title, duration_seconds) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (city_name, state, full_name, video.get("youtube_id", ""),
                     video.get("title"), video.get("duration_seconds")),
                )
                count += 1
            except sqlite3.IntegrityError:
                pass  # Duplicate full_name, skip

    return count


# ── Radio Stations ───────────────────────────────────────────────────────────

def get_all_stations():
    """Return all radio stations ordered by sort_order then name."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, station_id, name, frequency, type, source, description, sort_order, created_at "
            "FROM radio_stations ORDER BY sort_order, name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_stations_for_frontend():
    """Return stations in the format the frontend radio.js expects."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT station_id AS id, name, frequency, type, source, description "
            "FROM radio_stations ORDER BY sort_order, name"
        ).fetchall()
    return [dict(r) for r in rows]


def add_station(station_id, name, frequency, stype, source, description=None, sort_order=0):
    """Insert a new radio station. Returns the new record as a dict."""
    with _get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO radio_stations (station_id, name, frequency, type, source, description, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (station_id, name, frequency, stype, source, description, sort_order),
        )
        row = conn.execute("SELECT * FROM radio_stations WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def update_station(row_id, **fields):
    """Update an existing station. Accepts any subset of: station_id, name, frequency, type, source, description, sort_order."""
    allowed = {"station_id", "name", "frequency", "type", "source", "description", "sort_order"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return None

    with _get_conn() as conn:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [row_id]
        conn.execute(f"UPDATE radio_stations SET {set_clause} WHERE id = ?", values)
        row = conn.execute("SELECT * FROM radio_stations WHERE id = ?", (row_id,)).fetchone()
    return dict(row) if row else None


def delete_station(row_id):
    """Delete a radio station by ID. Returns True if a row was deleted."""
    with _get_conn() as conn:
        cursor = conn.execute("DELETE FROM radio_stations WHERE id = ?", (row_id,))
    return cursor.rowcount > 0


def import_stations_from_json(json_path="radio_stations.json"):
    """One-time migration: import stations from the old JSON file into SQLite.
    Returns the count of records imported."""
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stations = data.get("stations", [])
    count = 0
    with _get_conn() as conn:
        for i, s in enumerate(stations):
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO radio_stations (station_id, name, frequency, type, source, description, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (s.get("id", ""), s.get("name", ""), s.get("frequency"),
                     s.get("type", "youtube"), s.get("source", ""),
                     s.get("description"), i),
                )
                count += 1
            except sqlite3.IntegrityError:
                pass
    return count


# ── Cities Checklist ─────────────────────────────────────────────────────────

CITIES_CSV_URL = (
    "https://gist.githubusercontent.com/Miserlou/11500b2345d3fe850c92/"
    "raw/e36859a9eef58c231865429ade1c142a2b75f16e/gistfile1.txt"
)


def populate_cities(csv_text):
    """Parse the top-1000 cities CSV and insert into the cities table.
    Expects header: rank,city,state,population,2000-2013 growth
    Returns count of rows inserted."""
    import csv
    import io

    reader = csv.DictReader(io.StringIO(csv_text))
    count = 0
    with _get_conn() as conn:
        for row in reader:
            city = row.get("city", "").strip()
            state = row.get("state", "").strip()
            if not city or not state:
                continue
            # Convert state full name to abbreviation for matching with city_videos
            abbr = STATE_ABBREVS.get(state, state)
            full_name = f"{city}, {abbr}"
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO cities (rank, city, state, full_name, population, growth) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        int(row.get("rank", 0)),
                        city,
                        abbr,
                        full_name,
                        int(row.get("population", "0").replace(",", "")),
                        row.get("2000-2013 growth", ""),
                    ),
                )
                count += 1
            except (sqlite3.IntegrityError, ValueError):
                pass
    return count


def get_cities_with_status():
    """Return all cities with a flag indicating whether a video exists.
    LEFT JOINs cities against city_videos on full_name."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT c.id, c.rank, c.city, c.state, c.full_name, c.population, c.growth, "
            "       CASE WHEN v.id IS NOT NULL THEN 1 ELSE 0 END AS has_video, "
            "       v.youtube_id, v.title AS video_title "
            "FROM cities c "
            "LEFT JOIN city_videos v ON c.full_name = v.full_name "
            "ORDER BY c.rank"
        ).fetchall()
    return [dict(r) for r in rows]


def get_cities_count():
    """Return total cities and how many have videos."""
    with _get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
        with_video = conn.execute(
            "SELECT COUNT(*) FROM cities c "
            "INNER JOIN city_videos v ON c.full_name = v.full_name"
        ).fetchone()[0]
    return {"total": total, "with_video": with_video}


# US state name -> abbreviation mapping for the CSV which uses full names
STATE_ABBREVS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}
