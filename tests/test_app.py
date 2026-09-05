"""
Unit tests for app.py Flask API endpoints.
"""

import base64
import json

import pytest

import db


# ── Page routes ──────────────────────────────────────────────────────────────


class TestPageRoutes:
    def test_index_returns_200(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200

    def test_index_uses_frontend_google_maps_key(self, app_client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module.config, "GOOGLE_MAPS_FRONTEND_API_KEY", "frontend-key")
        monkeypatch.setattr(app_module.config, "GOOGLE_MAPS_SERVER_API_KEY", "server-key")

        resp = app_client.get("/")
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "key=frontend-key" in body
        assert 'window.GOOGLE_MAPS_API_KEY = "frontend-key";' in body
        assert "server-key" not in body

    def test_admin_requires_auth(self, app_client):
        resp = app_client.get("/admin")
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers

    def test_admin_returns_200_with_auth(self, app_client, admin_auth):
        resp = app_client.get("/admin", headers=admin_auth)
        assert resp.status_code == 200

    def test_favicon_returns_ico_or_404(self, app_client):
        resp = app_client.get("/favicon.ico")
        # Might be 404 if no favicon file exists in tests, or 200 if it does
        assert resp.status_code in (200, 404)


# ── Authentication on mutating endpoints ─────────────────────────────────────


class TestAuthentication:
    def test_write_requires_auth(self, app_client):
        resp = app_client.post("/api/stations", json={
            "station_id": "x", "name": "X", "type": "youtube", "source": "x",
        })
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers

    def test_wrong_password_rejected(self, app_client):
        bad = {"Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode("ascii")}
        resp = app_client.post("/api/stations", json={}, headers=bad)
        assert resp.status_code == 401

    def test_wrong_username_rejected(self, app_client):
        bad = {"Authorization": "Basic " + base64.b64encode(b"nobody:test-admin-password").decode("ascii")}
        resp = app_client.post("/api/stations", json={}, headers=bad)
        assert resp.status_code == 401

    def test_correct_credentials_pass(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", json={
            "station_id": "auth-test", "name": "Auth FM", "type": "youtube", "source": "x",
        }, headers=admin_auth)
        assert resp.status_code == 201

    def test_public_gets_stay_open(self, app_client):
        for path in ("/", "/api/stations", "/api/videos", "/api/cities", "/api/radio-stations"):
            resp = app_client.get(path)
            assert resp.status_code == 200, path

    def test_public_writes_stay_open(self, app_client):
        resp = app_client.post("/api/videos/lookup", json={})
        assert resp.status_code == 200
        # Missing fields still 400s (validation), not 401 (auth)
        resp = app_client.post("/api/route", json={})
        assert resp.status_code == 400

    def test_delete_requires_auth(self, app_client, seed_stations):
        resp = app_client.delete(f"/api/stations/{seed_stations[0]['id']}")
        assert resp.status_code == 401
        assert db.get_all_stations(), "no auth must not delete anything"

    def test_fails_closed_without_admin_password(self, app_client, admin_auth, monkeypatch):
        import config as config_module

        monkeypatch.setattr(config_module, "ADMIN_PASSWORD", "")
        resp = app_client.post("/api/stations", json={
            "station_id": "x", "name": "X", "type": "youtube", "source": "x",
        }, headers=admin_auth)
        assert resp.status_code == 503

    def test_failed_auth_attempts_are_throttled(self, app_client, clean_rate_limiter, monkeypatch):
        import config as config_module

        monkeypatch.setattr(config_module, "RATE_LIMIT_AUTH_FAILURES_PER_MINUTE", 2)
        bad = {"Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode("ascii")}
        for _ in range(2):
            resp = app_client.post("/api/stations", json={}, headers=bad)
            assert resp.status_code == 401
        resp = app_client.post("/api/stations", json={}, headers=bad)
        assert resp.status_code == 429


# ── Request hardening ────────────────────────────────────────────────────────


class TestRequestHardening:
    def test_non_dict_json_rejected(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", json=[1, 2, 3], headers=admin_auth)
        assert resp.status_code == 400

    def test_route_non_dict_json_rejected(self, app_client):
        resp = app_client.post("/api/route", json=[1, 2, 3])
        assert resp.status_code == 400

    def test_route_non_string_field_rejected(self, app_client):
        resp = app_client.post("/api/route", json={"source": 5, "destination": "B"})
        assert resp.status_code == 400

    def test_field_too_long_rejected(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", json={
            "station_id": "x", "name": "a" * 5000, "type": "youtube", "source": "x",
        }, headers=admin_auth)
        assert resp.status_code == 400

    def test_non_string_field_rejected(self, app_client, admin_auth):
        resp = app_client.post("/api/videos", json={"city_name": 5, "youtube_id": "abc"}, headers=admin_auth)
        assert resp.status_code == 400

    def test_oversized_body_rejected(self, app_client, admin_auth):
        import config as config_module

        big = "a" * (config_module.MAX_CONTENT_LENGTH + 10)
        resp = app_client.post(
            "/api/stations",
            content_type="application/json",
            data=json.dumps({"name": big}),
            headers=admin_auth,
        )
        assert resp.status_code == 413

    def test_security_headers_present(self, app_client):
        resp = app_client.get("/")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
        assert "Referrer-Policy" in resp.headers

    def test_duplicate_error_is_generic(self, app_client, admin_auth, seed_stations):
        resp = app_client.post("/api/stations", json={
            "station_id": "lofi", "name": "Dup", "type": "youtube", "source": "x",
        }, headers=admin_auth)
        assert resp.status_code == 409
        error = resp.get_json()["error"].lower()
        assert "unique" not in error
        assert "sqlite" not in error

    def test_unhandled_exceptions_return_generic_500(self, app_client, admin_auth, monkeypatch):
        monkeypatch.setattr(db, "delete_station", lambda _id: (_ for _ in ()).throw(RuntimeError("boom /etc/passwd")))
        resp = app_client.delete("/api/stations/1", headers=admin_auth)
        assert resp.status_code == 500
        body = resp.get_data(as_text=True)
        assert "boom" not in body
        assert "/etc/passwd" not in body


# ── Rate limiting on public write endpoints ──────────────────────────────────


class TestRateLimiting:
    def test_route_rate_limited(self, app_client, clean_rate_limiter, monkeypatch):
        import config as config_module

        monkeypatch.setattr(config_module, "RATE_LIMIT_ROUTE_PER_MINUTE", 1)
        body = {"source": "Cincinnati, OH", "destination": "Cleveland, OH"}
        resp = app_client.post("/api/route", json=body)  # no API key -> 500, still a hit
        assert resp.status_code == 500
        resp = app_client.post("/api/route", json=body)
        assert resp.status_code == 429

    def test_lookup_rate_limited(self, app_client, clean_rate_limiter, monkeypatch):
        import config as config_module

        monkeypatch.setattr(config_module, "RATE_LIMIT_LOOKUP_PER_MINUTE", 2)
        for _ in range(2):
            resp = app_client.post("/api/videos/lookup", json={"cities": []})
            assert resp.status_code == 200
        resp = app_client.post("/api/videos/lookup", json={"cities": []})
        assert resp.status_code == 429


# ── Route response cache ─────────────────────────────────────────────────────


class TestRouteCache:
    def test_identical_requests_are_cached(self, app_client, monkeypatch):
        import app as app_module

        calls = {"directions": 0}

        class FakeGmaps:
            def directions(self, source, destination, mode=None):
                calls["directions"] += 1
                return [{
                    "overview_polyline": {"points": "_p~iF~ps|U_ulLnnqC"},
                    "bounds": {"north": 42.3, "south": 40.7, "east": -71.0, "west": -74.0},
                    "legs": [{
                        "duration": {"value": 100},
                        "distance": {"value": 1000},
                        "start_address": "New York, NY, USA",
                        "end_address": "Boston, MA, USA",
                        "start_location": {"lat": 40.7, "lng": -74.0},
                        "end_location": {"lat": 42.3, "lng": -71.0},
                    }],
                }]

            def reverse_geocode(self, _point):
                return []

        monkeypatch.setattr(app_module, "gmaps", FakeGmaps())
        body = {"source": "Fakeville", "destination": "Fakeburg"}
        resp1 = app_client.post("/api/route", json=body)
        resp2 = app_client.post("/api/route", json=body)
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.get_json() == resp2.get_json()
        assert calls["directions"] == 1


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
    def test_success(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", json={
            "station_id": "test-fm",
            "name": "Test FM",
            "frequency": "99.9",
            "type": "youtube",
            "source": "vid123",
            "description": "A test",
        }, headers=admin_auth)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["station_id"] == "test-fm"
        assert data["name"] == "Test FM"

    def test_missing_required_fields(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", json={"station_id": "x"}, headers=admin_auth)
        assert resp.status_code == 400

    def test_invalid_type(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", json={
            "station_id": "bad", "name": "Bad", "type": "spotify", "source": "x",
        }, headers=admin_auth)
        assert resp.status_code == 400
        assert "type" in resp.get_json()["error"]

    def test_duplicate_station_id(self, app_client, admin_auth, seed_stations):
        resp = app_client.post("/api/stations", json={
            "station_id": "lofi", "name": "Dup", "type": "youtube", "source": "x",
        }, headers=admin_auth)
        assert resp.status_code == 409

    def test_missing_json_body(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", content_type="application/json", data="", headers=admin_auth)
        assert resp.status_code == 400

    def test_trims_whitespace(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", json={
            "station_id": "  trimmed  ",
            "name": "  Trimmed FM  ",
            "type": "mp3",
            "source": "  file.mp3  ",
        }, headers=admin_auth)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["station_id"] == "trimmed"
        assert data["name"] == "Trimmed FM"
        assert data["source"] == "file.mp3"

    def test_sort_order_default_zero(self, app_client, admin_auth):
        resp = app_client.post("/api/stations", json={
            "station_id": "def", "name": "Default", "type": "youtube", "source": "x",
        }, headers=admin_auth)
        assert resp.get_json()["sort_order"] == 0


class TestUpdateStation:
    def test_update_name(self, app_client, admin_auth, seed_stations):
        sid = seed_stations[0]["id"]
        resp = app_client.put(f"/api/stations/{sid}", json={"name": "Renamed"}, headers=admin_auth)
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Renamed"

    def test_not_found(self, app_client, admin_auth):
        resp = app_client.put("/api/stations/99999", json={"name": "x"}, headers=admin_auth)
        assert resp.status_code == 404

    def test_missing_json_body(self, app_client, admin_auth, seed_stations):
        sid = seed_stations[0]["id"]
        resp = app_client.put(f"/api/stations/{sid}", content_type="application/json", data="", headers=admin_auth)
        assert resp.status_code == 400

    def test_invalid_type_on_update(self, app_client, admin_auth, seed_stations):
        sid = seed_stations[0]["id"]
        resp = app_client.put(f"/api/stations/{sid}", json={"type": "invalid"}, headers=admin_auth)
        assert resp.status_code == 400


class TestDeleteStation:
    def test_delete_existing(self, app_client, admin_auth, seed_stations):
        sid = seed_stations[0]["id"]
        resp = app_client.delete(f"/api/stations/{sid}", headers=admin_auth)
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_delete_nonexistent(self, app_client, admin_auth):
        resp = app_client.delete("/api/stations/99999", headers=admin_auth)
        assert resp.status_code == 404


class TestImportStations:
    def test_import_success(self, app_client, admin_auth, monkeypatch):
        monkeypatch.setattr(db, "import_stations_from_json", lambda _path: 2)
        resp = app_client.post("/api/stations/import", headers=admin_auth)
        assert resp.status_code == 200
        assert resp.get_json()["imported"] == 2

    def test_import_file_not_found(self, app_client, admin_auth, monkeypatch):
        monkeypatch.setattr(db, "import_stations_from_json", lambda _path: (_ for _ in ()).throw(FileNotFoundError("not found")))
        resp = app_client.post("/api/stations/import", headers=admin_auth)
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
    def test_success(self, app_client, admin_auth):
        resp = app_client.post("/api/videos", json={
            "city_name": "Toledo",
            "state": "OH",
            "youtube_id": "xyz999",
            "title": "Toledo Tour",
            "duration_seconds": 120,
        }, headers=admin_auth)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["full_name"] == "Toledo, OH"
        assert data["youtube_id"] == "xyz999"

    def test_missing_city_name(self, app_client, admin_auth):
        resp = app_client.post("/api/videos", json={"youtube_id": "abc"}, headers=admin_auth)
        assert resp.status_code == 400

    def test_missing_youtube_id(self, app_client, admin_auth):
        resp = app_client.post("/api/videos", json={"city_name": "Test"}, headers=admin_auth)
        assert resp.status_code == 400

    def test_missing_json_body(self, app_client, admin_auth):
        resp = app_client.post("/api/videos", content_type="application/json", data="", headers=admin_auth)
        assert resp.status_code == 400

    def test_duplicate_full_name(self, app_client, admin_auth, seed_videos):
        resp = app_client.post("/api/videos", json={
            "city_name": "Columbus", "state": "OH", "youtube_id": "different",
        }, headers=admin_auth)
        assert resp.status_code == 409

    def test_optional_fields_omitted(self, app_client, admin_auth):
        resp = app_client.post("/api/videos", json={
            "city_name": "Bare", "state": "OH", "youtube_id": "bare123",
        }, headers=admin_auth)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] is None
        assert data["duration_seconds"] is None

    def test_invalid_duration_becomes_none(self, app_client, admin_auth):
        resp = app_client.post("/api/videos", json={
            "city_name": "Test", "state": "OH", "youtube_id": "t123",
            "duration_seconds": "not_a_number",
        }, headers=admin_auth)
        assert resp.status_code == 201
        assert resp.get_json()["duration_seconds"] is None

    def test_trims_whitespace(self, app_client, admin_auth):
        resp = app_client.post("/api/videos", json={
            "city_name": "  Toledo  ",
            "state": "  OH  ",
            "youtube_id": "  xyz  ",
            "title": "  Toledo Tour  ",
        }, headers=admin_auth)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["city_name"] == "Toledo"


class TestUpdateVideo:
    def test_update_title(self, app_client, admin_auth, seed_videos):
        vid = seed_videos[0]["id"]
        resp = app_client.put(f"/api/videos/{vid}", json={"title": "New Title"}, headers=admin_auth)
        assert resp.status_code == 200
        assert resp.get_json()["title"] == "New Title"

    def test_not_found(self, app_client, admin_auth):
        resp = app_client.put("/api/videos/99999", json={"title": "x"}, headers=admin_auth)
        assert resp.status_code == 404

    def test_missing_json_body(self, app_client, admin_auth, seed_videos):
        vid = seed_videos[0]["id"]
        resp = app_client.put(f"/api/videos/{vid}", content_type="application/json", data="", headers=admin_auth)
        assert resp.status_code == 400


class TestDeleteVideo:
    def test_delete_existing(self, app_client, admin_auth, seed_videos):
        vid = seed_videos[0]["id"]
        resp = app_client.delete(f"/api/videos/{vid}", headers=admin_auth)
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_delete_nonexistent(self, app_client, admin_auth):
        resp = app_client.delete("/api/videos/99999", headers=admin_auth)
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

    def test_lookup_cities_not_a_list(self, app_client):
        resp = app_client.post("/api/videos/lookup", json={"cities": "Columbus, OH"})
        assert resp.status_code == 400

    def test_lookup_too_many_cities(self, app_client):
        import config as config_module

        cities = [f"City {i}" for i in range(config_module.MAX_LOOKUP_CITIES + 1)]
        resp = app_client.post("/api/videos/lookup", json={"cities": cities})
        assert resp.status_code == 400

    def test_lookup_city_name_too_long(self, app_client):
        resp = app_client.post("/api/videos/lookup", json={"cities": ["x" * 500]})
        assert resp.status_code == 400


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
    def test_import_success(self, app_client, admin_auth, monkeypatch):
        monkeypatch.setattr(db, "import_from_json", lambda _path: 3)
        resp = app_client.post("/api/videos/import", headers=admin_auth)
        assert resp.status_code == 200
        assert resp.get_json()["imported"] == 3

    def test_import_file_not_found(self, app_client, admin_auth, monkeypatch):
        monkeypatch.setattr(db, "import_from_json", lambda _path: (_ for _ in ()).throw(FileNotFoundError("not found")))
        resp = app_client.post("/api/videos/import", headers=admin_auth)
        assert resp.status_code == 404
