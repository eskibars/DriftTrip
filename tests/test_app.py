"""
Unit tests for app.py Flask API endpoints.
"""

import json

import pytest

import db


# ── Page routes ──────────────────────────────────────────────────────────────


class TestPageRoutes:
    def test_index_returns_200(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200

    def test_admin_returns_200(self, app_client):
        resp = app_client.get("/admin")
        assert resp.status_code == 200

    def test_favicon_returns_ico_or_404(self, app_client):
        resp = app_client.get("/favicon.ico")
        # Might be 404 if no favicon file exists in tests, or 200 if it does
        assert resp.status_code in (200, 404)


# ── Radio Stations API (GET /api/radio-stations) ────────────────────────────


class TestRadioStationsFrontendEndpoint:
    def test_empty_returns_empty_stations(self, app_client):
        resp = app_client.get("/api/radio-stations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"stations": []}

    def test_returns_frontend_format(self, app_client, seed_stations):
        resp = app_client.get("/api/radio-stations")
        data = resp.get_json()
        assert len(data["stations"]) == 3
        s = data["stations"][0]
        # Frontend format uses "id" not "station_id"
        assert "id" in s
        assert "station_id" not in s
        assert "sort_order" not in s


# ── Stations CRUD API ────────────────────────────────────────────────────────


class TestListStations:
    def test_empty(self, app_client):
        resp = app_client.get("/api/stations")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_with_data(self, app_client, seed_stations):
        resp = app_client.get("/api/stations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3
        assert "station_id" in data[0]


class TestCreateStation:
    def test_success(self, app_client):
        resp = app_client.post("/api/stations", json={
            "station_id": "test-fm",
            "name": "Test FM",
            "frequency": "99.9",
            "type": "youtube",
            "source": "vid123",
            "description": "A test",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["station_id"] == "test-fm"
        assert data["name"] == "Test FM"

    def test_missing_required_fields(self, app_client):
        resp = app_client.post("/api/stations", json={"station_id": "x"})
        assert resp.status_code == 400

    def test_invalid_type(self, app_client):
        resp = app_client.post("/api/stations", json={
            "station_id": "bad", "name": "Bad", "type": "spotify", "source": "x",
        })
        assert resp.status_code == 400
        assert "type" in resp.get_json()["error"]

    def test_duplicate_station_id(self, app_client, seed_stations):
        resp = app_client.post("/api/stations", json={
            "station_id": "lofi", "name": "Dup", "type": "youtube", "source": "x",
        })
        assert resp.status_code == 409

    def test_missing_json_body(self, app_client):
        resp = app_client.post("/api/stations", content_type="application/json", data="")
        assert resp.status_code == 400

    def test_trims_whitespace(self, app_client):
        resp = app_client.post("/api/stations", json={
            "station_id": "  trimmed  ",
            "name": "  Trimmed FM  ",
            "type": "mp3",
            "source": "  file.mp3  ",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["station_id"] == "trimmed"
        assert data["name"] == "Trimmed FM"
        assert data["source"] == "file.mp3"

    def test_sort_order_default_zero(self, app_client):
        resp = app_client.post("/api/stations", json={
            "station_id": "def", "name": "Default", "type": "youtube", "source": "x",
        })
        assert resp.get_json()["sort_order"] == 0


class TestUpdateStation:
    def test_update_name(self, app_client, seed_stations):
        sid = seed_stations[0]["id"]
        resp = app_client.put(f"/api/stations/{sid}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Renamed"

    def test_not_found(self, app_client):
        resp = app_client.put("/api/stations/99999", json={"name": "x"})
        assert resp.status_code == 404

    def test_missing_json_body(self, app_client, seed_stations):
        sid = seed_stations[0]["id"]
        resp = app_client.put(f"/api/stations/{sid}", content_type="application/json", data="")
        assert resp.status_code == 400

    def test_invalid_type_on_update(self, app_client, seed_stations):
        sid = seed_stations[0]["id"]
        resp = app_client.put(f"/api/stations/{sid}", json={"type": "invalid"})
        assert resp.status_code == 400


class TestDeleteStation:
    def test_delete_existing(self, app_client, seed_stations):
        sid = seed_stations[0]["id"]
        resp = app_client.delete(f"/api/stations/{sid}")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_delete_nonexistent(self, app_client):
        resp = app_client.delete("/api/stations/99999")
        assert resp.status_code == 404


class TestImportStations:
    def test_import_success(self, app_client, monkeypatch):
        monkeypatch.setattr(db, "import_stations_from_json", lambda _path: 2)
        resp = app_client.post("/api/stations/import")
        assert resp.status_code == 200
        assert resp.get_json()["imported"] == 2

    def test_import_file_not_found(self, app_client, monkeypatch):
        monkeypatch.setattr(db, "import_stations_from_json", lambda _path: (_ for _ in ()).throw(FileNotFoundError("not found")))
        resp = app_client.post("/api/stations/import")
        assert resp.status_code == 404


# ── Videos CRUD API ──────────────────────────────────────────────────────────


class TestListVideos:
    def test_empty(self, app_client):
        resp = app_client.get("/api/videos")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_with_data(self, app_client, seed_videos):
        resp = app_client.get("/api/videos")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 4


class TestCreateVideo:
    def test_success(self, app_client):
        resp = app_client.post("/api/videos", json={
            "city_name": "Toledo",
            "state": "OH",
            "youtube_id": "xyz999",
            "title": "Toledo Tour",
            "duration_seconds": 120,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["full_name"] == "Toledo, OH"
        assert data["youtube_id"] == "xyz999"

    def test_missing_city_name(self, app_client):
        resp = app_client.post("/api/videos", json={"youtube_id": "abc"})
        assert resp.status_code == 400

    def test_missing_youtube_id(self, app_client):
        resp = app_client.post("/api/videos", json={"city_name": "Test"})
        assert resp.status_code == 400

    def test_missing_json_body(self, app_client):
        resp = app_client.post("/api/videos", content_type="application/json", data="")
        assert resp.status_code == 400

    def test_duplicate_full_name(self, app_client, seed_videos):
        resp = app_client.post("/api/videos", json={
            "city_name": "Columbus", "state": "OH", "youtube_id": "different",
        })
        assert resp.status_code == 409

    def test_optional_fields_omitted(self, app_client):
        resp = app_client.post("/api/videos", json={
            "city_name": "Bare", "state": "OH", "youtube_id": "bare123",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] is None
        assert data["duration_seconds"] is None

    def test_invalid_duration_becomes_none(self, app_client):
        resp = app_client.post("/api/videos", json={
            "city_name": "Test", "state": "OH", "youtube_id": "t123",
            "duration_seconds": "not_a_number",
        })
        assert resp.status_code == 201
        assert resp.get_json()["duration_seconds"] is None

    def test_trims_whitespace(self, app_client):
        resp = app_client.post("/api/videos", json={
            "city_name": "  Toledo  ",
            "state": "  OH  ",
            "youtube_id": "  xyz  ",
            "title": "  Toledo Tour  ",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["city_name"] == "Toledo"


class TestUpdateVideo:
    def test_update_title(self, app_client, seed_videos):
        vid = seed_videos[0]["id"]
        resp = app_client.put(f"/api/videos/{vid}", json={"title": "New Title"})
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "New Title"

    def test_not_found(self, app_client):
        resp = app_client.put("/api/videos/99999", json={"title": "x"})
        assert resp.status_code == 404

    def test_missing_json_body(self, app_client, seed_videos):
        vid = seed_videos[0]["id"]
        resp = app_client.put(f"/api/videos/{vid}", content_type="application/json", data="")
        assert resp.status_code == 400


class TestDeleteVideo:
    def test_delete_existing(self, app_client, seed_videos):
        vid = seed_videos[0]["id"]
        resp = app_client.delete(f"/api/videos/{vid}")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_delete_nonexistent(self, app_client):
        resp = app_client.delete("/api/videos/99999")
        assert resp.status_code == 404


# ── Videos Lookup API ────────────────────────────────────────────────────────


class TestLookupVideos:
    def test_lookup_found(self, app_client, seed_videos):
        resp = app_client.post("/api/videos/lookup", json={
            "cities": ["Columbus, OH", "Dayton, OH"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "Columbus, OH" in data
        assert data["Columbus, OH"]["youtube_id"] == "abc123"

    def test_lookup_not_found(self, app_client, seed_videos):
        resp = app_client.post("/api/videos/lookup", json={
            "cities": ["Nonexistent, XX"],
        })
        data = resp.get_json()
        assert "Nonexistent, XX" not in data

    def test_lookup_mixed(self, app_client, seed_videos):
        resp = app_client.post("/api/videos/lookup", json={
            "cities": ["Columbus, OH", "Nonexistent, XX"],
        })
        data = resp.get_json()
        assert "Columbus, OH" in data
        assert "Nonexistent, XX" not in data

    def test_lookup_empty_cities(self, app_client):
        resp = app_client.post("/api/videos/lookup", json={"cities": []})
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_lookup_no_body(self, app_client):
        resp = app_client.post("/api/videos/lookup", json={})
        assert resp.status_code == 200
        assert resp.get_json() == {}


# ── Route API (basic validation, without real Google Maps calls) ─────────────


class TestRouteValidation:
    def test_missing_source(self, app_client):
        resp = app_client.post("/api/route", json={"destination": "Cleveland, OH"})
        assert resp.status_code == 400

    def test_missing_destination(self, app_client):
        resp = app_client.post("/api/route", json={"source": "Cincinnati, OH"})
        assert resp.status_code == 400

    def test_empty_source(self, app_client):
        resp = app_client.post("/api/route", json={"source": "  ", "destination": "Cleveland"})
        assert resp.status_code == 400

    def test_no_api_key_returns_500(self, app_client):
        resp = app_client.post("/api/route", json={
            "source": "Cincinnati, OH",
            "destination": "Cleveland, OH",
        })
        # With no real API key configured, should get 500
        assert resp.status_code == 500
        assert "API key" in resp.get_json()["error"]


# ── Import Videos API ────────────────────────────────────────────────────────


class TestImportVideos:
    def test_import_success(self, app_client, monkeypatch):
        monkeypatch.setattr(db, "import_from_json", lambda _path: 3)
        resp = app_client.post("/api/videos/import")
        assert resp.status_code == 200
        assert resp.get_json()["imported"] == 3

    def test_import_file_not_found(self, app_client, monkeypatch):
        monkeypatch.setattr(db, "import_from_json", lambda _path: (_ for _ in ()).throw(FileNotFoundError("not found")))
        resp = app_client.post("/api/videos/import")
        assert resp.status_code == 404
