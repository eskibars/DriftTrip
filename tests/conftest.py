"""
Shared fixtures for all tests.
"""

import json
import os
import tempfile

import pytest

# Ensure db.py uses a temp database for every test
import db as db_module


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Redirect db.DB_PATH to a fresh temp file for every test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture
def sample_videos_json(tmp_path):
    """Create a temporary city_videos.json file with sample data."""
    data = {
        "Columbus, OH": {
            "youtube_id": "abc123",
            "title": "Visit Columbus",
            "duration_seconds": 300,
        },
        "Dayton, OH": {
            "youtube_id": "def456",
            "title": "Dayton Travel Guide",
            "duration_seconds": 240,
        },
        "Portland": {
            "youtube_id": "ghi789",
            "title": "Portland City Tour",
        },
    }
    path = tmp_path / "city_videos.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def sample_stations_json(tmp_path):
    """Create a temporary radio_stations.json file with sample data."""
    data = {
        "stations": [
            {
                "id": "lofi-beats",
                "name": "98.1 Lofi FM",
                "frequency": "98.1",
                "type": "youtube",
                "source": "jfKfPfyJRdk",
                "description": "Lofi beats",
            },
            {
                "id": "rock-fm",
                "name": "97.7 Rock",
                "frequency": "97.7",
                "type": "mp3",
                "source": "rock.mp3",
                "description": "Classic rock",
            },
        ]
    }
    path = tmp_path / "radio_stations.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def app_client():
    """Flask test client with database pointing at temp db (inherited from temp_db autouse)."""
    from app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def seed_videos():
    """Insert a handful of videos into the test DB and return them."""
    import db

    v1 = db.add_video("Columbus", "OH", "abc123", "Visit Columbus", 300)
    v2 = db.add_video("Dayton", "OH", "def456", "Dayton Guide", 240)
    v3 = db.add_video("Akron", "OH", "ghi789", "Akron Tour", 180)
    v4 = db.add_video("Portland", "OR", "jkl012", "Portland Travel", 360)
    return [v1, v2, v3, v4]


@pytest.fixture
def seed_stations():
    """Insert a handful of stations into the test DB and return them."""
    import db

    s1 = db.add_station("lofi", "98.1 Lofi FM", "98.1", "youtube", "jfKfPfyJRdk", "Lofi beats", 0)
    s2 = db.add_station("rock", "97.7 Rock", "97.7", "mp3", "rock.mp3", "Classic rock", 1)
    s3 = db.add_station("jazz", "103.5 Jazz", "103.5", "youtube", "HcEGMi5MPTM", "Smooth jazz", 2)
    return [s1, s2, s3]
