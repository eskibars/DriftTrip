"""
Unit tests for the cities checklist feature (db functions + API endpoints).
"""

import pytest

import db


# ── DB layer ─────────────────────────────────────────────────────────────────


class TestPopulateCities:
    def test_populates_from_csv(self, sample_cities_csv):
        count = db.populate_cities(sample_cities_csv)
        assert count == 5

    def test_converts_state_names_to_abbreviations(self, sample_cities_csv):
        db.populate_cities(sample_cities_csv)
        cities = db.get_cities_with_status()
        states = {c["state"] for c in cities}
        assert "NY" in states
        assert "CA" in states
        assert "New York" not in states

    def test_full_name_format(self, sample_cities_csv):
        db.populate_cities(sample_cities_csv)
        cities = db.get_cities_with_status()
        ny = [c for c in cities if c["city"] == "New York"][0]
        assert ny["full_name"] == "New York, NY"

    def test_population_parsed(self, sample_cities_csv):
        db.populate_cities(sample_cities_csv)
        cities = db.get_cities_with_status()
        ny = [c for c in cities if c["city"] == "New York"][0]
        assert ny["population"] == 8405837

    def test_idempotent(self, sample_cities_csv):
        db.populate_cities(sample_cities_csv)
        db.populate_cities(sample_cities_csv)
        cities = db.get_cities_with_status()
        assert len(cities) == 5

    def test_empty_csv(self):
        count = db.populate_cities("rank,city,state,population,2000-2013 growth\n")
        assert count == 0


class TestGetCitiesWithStatus:
    def test_empty_db(self):
        assert db.get_cities_with_status() == []

    def test_no_video_by_default(self, seed_cities):
        for c in seed_cities:
            assert c["has_video"] == 0

    def test_cross_references_video(self, seed_cities):
        # Columbus, OH is in both seed_cities and this video
        db.add_video("Columbus", "OH", "vid123", "Columbus Tour", 300)
        cities = db.get_cities_with_status()
        columbus = [c for c in cities if c["city"] == "Columbus"][0]
        assert columbus["has_video"] == 1
        assert columbus["video_title"] == "Columbus Tour"
        assert columbus["youtube_id"] == "vid123"

    def test_ordered_by_rank(self, seed_cities):
        cities = db.get_cities_with_status()
        ranks = [c["rank"] for c in cities]
        assert ranks == sorted(ranks)

    def test_has_expected_fields(self, seed_cities):
        c = seed_cities[0]
        expected = {"id", "rank", "city", "state", "full_name", "population",
                    "growth", "has_video", "youtube_id", "video_title"}
        assert set(c.keys()) == expected


class TestGetCitiesCount:
    def test_empty_db(self):
        stats = db.get_cities_count()
        assert stats == {"total": 0, "with_video": 0}

    def test_counts_total(self, seed_cities):
        stats = db.get_cities_count()
        assert stats["total"] == 5
        assert stats["with_video"] == 0

    def test_counts_with_video(self, seed_cities):
        db.add_video("Columbus", "OH", "vid123", "Columbus Tour")
        db.add_video("Houston", "TX", "vid456", "Houston Tour")
        stats = db.get_cities_count()
        assert stats["total"] == 5
        assert stats["with_video"] == 2


# ── API endpoints ────────────────────────────────────────────────────────────


class TestCitiesAPI:
    def test_list_empty(self, app_client):
        resp = app_client.get("/api/cities")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_with_data(self, app_client, seed_cities):
        resp = app_client.get("/api/cities")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 5

    def test_stats_empty(self, app_client):
        resp = app_client.get("/api/cities/stats")
        assert resp.status_code == 200
        assert resp.get_json() == {"total": 0, "with_video": 0}

    def test_stats_with_data(self, app_client, seed_cities, seed_videos):
        # seed_videos includes Columbus, OH which matches seed_cities
        resp = app_client.get("/api/cities/stats")
        data = resp.get_json()
        assert data["total"] == 5
        assert data["with_video"] == 1  # Columbus, OH

    def test_populate_success(self, app_client, monkeypatch):
        monkeypatch.setattr(db, "populate_cities", lambda _csv: 1000)
        # Mock the HTTP request
        import app as app_module
        class FakeResp:
            text = "fake"
            def raise_for_status(self): pass
        monkeypatch.setattr(app_module.http_requests, "get", lambda *a, **kw: FakeResp())
        resp = app_client.post("/api/cities/populate")
        assert resp.status_code == 200
        assert resp.get_json()["imported"] == 1000

    def test_populate_network_error(self, app_client, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module.http_requests, "get", lambda *a, **kw: (_ for _ in ()).throw(Exception("timeout")))
        resp = app_client.post("/api/cities/populate")
        assert resp.status_code == 502
