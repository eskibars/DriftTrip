"""
Unit tests for db.py — city_videos and radio_stations CRUD.
"""

import sqlite3

import pytest

import db


# ── City Videos ──────────────────────────────────────────────────────────────


class TestGetAllVideos:
    def test_empty_database(self):
        assert db.get_all_videos() == []

    def test_returns_all_records(self, seed_videos):
        result = db.get_all_videos()
        assert len(result) == 4

    def test_ordered_by_full_name(self, seed_videos):
        result = db.get_all_videos()
        names = [v["full_name"] for v in result]
        assert names == sorted(names)

    def test_has_expected_fields(self, seed_videos):
        result = db.get_all_videos()[0]
        expected_keys = {"id", "city_name", "state", "full_name", "youtube_id", "title", "duration_seconds", "created_at"}
        assert set(result.keys()) == expected_keys


class TestGetVideoForCity:
    def test_found(self, seed_videos):
        result = db.get_video_for_city("Columbus, OH")
        assert result is not None
        assert result["youtube_id"] == "abc123"
        assert result["title"] == "Visit Columbus"
        assert result["duration_seconds"] == 300

    def test_not_found(self, seed_videos):
        assert db.get_video_for_city("Nonexistent, XX") is None

    def test_returns_only_video_fields(self, seed_videos):
        result = db.get_video_for_city("Columbus, OH")
        assert set(result.keys()) == {"youtube_id", "title", "duration_seconds"}

    def test_case_sensitive(self, seed_videos):
        assert db.get_video_for_city("columbus, oh") is None

    def test_empty_string(self):
        assert db.get_video_for_city("") is None


class TestAddVideo:
    def test_basic_add(self):
        v = db.add_video("Toledo", "OH", "xyz999", "Toledo Tour", 120)
        assert v["city_name"] == "Toledo"
        assert v["state"] == "OH"
        assert v["full_name"] == "Toledo, OH"
        assert v["youtube_id"] == "xyz999"
        assert v["id"] is not None

    def test_full_name_construction_with_state(self):
        v = db.add_video("Chicago", "IL", "vid1")
        assert v["full_name"] == "Chicago, IL"

    def test_full_name_construction_without_state(self):
        v = db.add_video("London", None, "vid2")
        assert v["full_name"] == "London"

    def test_full_name_construction_empty_state(self):
        v = db.add_video("London", "", "vid3")
        assert v["full_name"] == "London"

    def test_optional_fields_none(self):
        v = db.add_video("Test", "TX", "vid4")
        assert v["title"] is None
        assert v["duration_seconds"] is None

    def test_duplicate_full_name_raises(self):
        db.add_video("Toledo", "OH", "xyz999")
        with pytest.raises(Exception):
            db.add_video("Toledo", "OH", "different")

    def test_auto_increments_id(self):
        v1 = db.add_video("City1", "S1", "vid1")
        v2 = db.add_video("City2", "S2", "vid2")
        assert v2["id"] > v1["id"]


class TestUpdateVideo:
    def test_update_title(self, seed_videos):
        vid = seed_videos[0]
        updated = db.update_video(vid["id"], title="New Title")
        assert updated["title"] == "New Title"
        assert updated["city_name"] == vid["city_name"]  # unchanged

    def test_update_youtube_id(self, seed_videos):
        vid = seed_videos[0]
        updated = db.update_video(vid["id"], youtube_id="new_id")
        assert updated["youtube_id"] == "new_id"

    def test_update_city_name_recomputes_full_name(self, seed_videos):
        vid = seed_videos[0]
        updated = db.update_video(vid["id"], city_name="Springfield")
        assert updated["full_name"] == "Springfield, OH"

    def test_update_state_recomputes_full_name(self, seed_videos):
        vid = seed_videos[0]
        updated = db.update_video(vid["id"], state="TX")
        assert updated["full_name"] == "Columbus, TX"

    def test_update_both_city_and_state(self, seed_videos):
        vid = seed_videos[0]
        updated = db.update_video(vid["id"], city_name="Austin", state="TX")
        assert updated["full_name"] == "Austin, TX"

    def test_nonexistent_id_returns_none(self):
        assert db.update_video(99999, title="x") is None

    def test_empty_fields_returns_none(self, seed_videos):
        assert db.update_video(seed_videos[0]["id"]) is None

    def test_ignores_unknown_fields(self, seed_videos):
        vid = seed_videos[0]
        updated = db.update_video(vid["id"], title="New", bogus_field="ignored")
        assert updated["title"] == "New"

    def test_partial_update_preserves_other_fields(self, seed_videos):
        vid = seed_videos[0]
        updated = db.update_video(vid["id"], title="Changed")
        assert updated["youtube_id"] == vid["youtube_id"]
        assert updated["duration_seconds"] == vid["duration_seconds"]


class TestDeleteVideo:
    def test_delete_existing(self, seed_videos):
        assert db.delete_video(seed_videos[0]["id"]) is True
        assert db.get_video_for_city(seed_videos[0]["full_name"]) is None

    def test_delete_nonexistent(self):
        assert db.delete_video(99999) is False

    def test_delete_reduces_count(self, seed_videos):
        before = len(db.get_all_videos())
        db.delete_video(seed_videos[0]["id"])
        after = len(db.get_all_videos())
        assert after == before - 1


class TestImportFromJson:
    def test_import_all_records(self, sample_videos_json):
        count = db.import_from_json(sample_videos_json)
        assert count == 3
        all_vids = db.get_all_videos()
        assert len(all_vids) == 3

    def test_splits_full_name_correctly(self, sample_videos_json):
        db.import_from_json(sample_videos_json)
        v = db.get_video_for_city("Columbus, OH")
        assert v is not None
        assert v["youtube_id"] == "abc123"

    def test_city_without_state(self, sample_videos_json):
        db.import_from_json(sample_videos_json)
        # "Portland" has no ", STATE" component
        all_vids = db.get_all_videos()
        portland = [v for v in all_vids if v["city_name"] == "Portland"]
        assert len(portland) == 1
        assert portland[0]["state"] is None

    def test_idempotent_import(self, sample_videos_json):
        count1 = db.import_from_json(sample_videos_json)
        count2 = db.import_from_json(sample_videos_json)
        # INSERT OR IGNORE should skip duplicates
        assert len(db.get_all_videos()) == 3

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            db.import_from_json("/nonexistent/path.json")


# ── Radio Stations ───────────────────────────────────────────────────────────


class TestGetAllStations:
    def test_empty_database(self):
        assert db.get_all_stations() == []

    def test_returns_all_records(self, seed_stations):
        assert len(db.get_all_stations()) == 3

    def test_ordered_by_sort_order(self, seed_stations):
        result = db.get_all_stations()
        orders = [s["sort_order"] for s in result]
        assert orders == sorted(orders)

    def test_has_expected_fields(self, seed_stations):
        result = db.get_all_stations()[0]
        expected = {"id", "station_id", "name", "frequency", "type", "source", "description", "sort_order", "created_at"}
        assert set(result.keys()) == expected


class TestGetStationsForFrontend:
    def test_empty_database(self):
        assert db.get_stations_for_frontend() == []

    def test_renames_station_id_to_id(self, seed_stations):
        result = db.get_stations_for_frontend()
        assert "id" in result[0]
        assert "station_id" not in result[0]
        assert result[0]["id"] == "lofi"

    def test_excludes_internal_fields(self, seed_stations):
        result = db.get_stations_for_frontend()[0]
        assert "sort_order" not in result
        assert "created_at" not in result

    def test_has_frontend_fields(self, seed_stations):
        result = db.get_stations_for_frontend()[0]
        expected = {"id", "name", "frequency", "type", "source", "description"}
        assert set(result.keys()) == expected


class TestAddStation:
    def test_basic_add(self):
        s = db.add_station("new-fm", "New FM", "101.1", "youtube", "vid123", "A new station", 5)
        assert s["station_id"] == "new-fm"
        assert s["name"] == "New FM"
        assert s["type"] == "youtube"
        assert s["sort_order"] == 5

    def test_optional_fields(self):
        s = db.add_station("bare-min", "Bare Minimum", None, "mp3", "file.mp3")
        assert s["frequency"] is None
        assert s["description"] is None
        assert s["sort_order"] == 0

    def test_duplicate_station_id_raises(self):
        db.add_station("dup", "Dup 1", None, "youtube", "vid1")
        with pytest.raises(Exception):
            db.add_station("dup", "Dup 2", None, "youtube", "vid2")

    def test_invalid_type_raises(self):
        with pytest.raises(sqlite3.IntegrityError):
            db.add_station("bad-type", "Bad", None, "spotify", "x")


class TestUpdateStation:
    def test_update_name(self, seed_stations):
        s = seed_stations[0]
        updated = db.update_station(s["id"], name="Renamed")
        assert updated["name"] == "Renamed"

    def test_update_sort_order(self, seed_stations):
        s = seed_stations[2]
        updated = db.update_station(s["id"], sort_order=99)
        assert updated["sort_order"] == 99

    def test_nonexistent_returns_none(self):
        assert db.update_station(99999, name="x") is None

    def test_empty_fields_returns_none(self, seed_stations):
        assert db.update_station(seed_stations[0]["id"]) is None

    def test_ignores_unknown_fields(self, seed_stations):
        s = seed_stations[0]
        updated = db.update_station(s["id"], name="New", fake_field="ignored")
        assert updated["name"] == "New"

    def test_partial_update_preserves_other_fields(self, seed_stations):
        s = seed_stations[0]
        updated = db.update_station(s["id"], description="Changed")
        assert updated["name"] == s["name"]
        assert updated["source"] == s["source"]


class TestDeleteStation:
    def test_delete_existing(self, seed_stations):
        assert db.delete_station(seed_stations[0]["id"]) is True
        assert len(db.get_all_stations()) == 2

    def test_delete_nonexistent(self):
        assert db.delete_station(99999) is False


class TestImportStationsFromJson:
    def test_import_all_records(self, sample_stations_json):
        count = db.import_stations_from_json(sample_stations_json)
        assert count == 2
        assert len(db.get_all_stations()) == 2

    def test_assigns_sort_order_from_index(self, sample_stations_json):
        db.import_stations_from_json(sample_stations_json)
        stations = db.get_all_stations()
        lofi = [s for s in stations if s["station_id"] == "lofi-beats"][0]
        rock = [s for s in stations if s["station_id"] == "rock-fm"][0]
        assert lofi["sort_order"] == 0
        assert rock["sort_order"] == 1

    def test_idempotent(self, sample_stations_json):
        db.import_stations_from_json(sample_stations_json)
        db.import_stations_from_json(sample_stations_json)
        assert len(db.get_all_stations()) == 2

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            db.import_stations_from_json("/nonexistent/path.json")
