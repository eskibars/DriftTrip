"""
Unit tests for app.py helper functions: haversine, decode_and_sample_route, attach_videos.
"""

import math

import pytest

from app import haversine, decode_and_sample_route, attach_videos
import db


class TestHaversine:
    def test_same_point_returns_zero(self):
        assert haversine(40.0, -83.0, 40.0, -83.0) == 0.0

    def test_known_distance_nyc_to_la(self):
        # NYC (40.7128, -74.0060) to LA (34.0522, -118.2437) ≈ 3,944 km
        dist = haversine(40.7128, -74.0060, 34.0522, -118.2437)
        assert 3_900_000 < dist < 4_000_000

    def test_known_distance_short(self):
        # Cincinnati (39.1031, -84.5120) to Dayton (39.7589, -84.1916) ≈ 78 km
        dist = haversine(39.1031, -84.5120, 39.7589, -84.1916)
        assert 70_000 < dist < 90_000

    def test_symmetry(self):
        d1 = haversine(40.0, -83.0, 41.0, -82.0)
        d2 = haversine(41.0, -82.0, 40.0, -83.0)
        assert abs(d1 - d2) < 0.01

    def test_equator_one_degree_longitude(self):
        # 1 degree of longitude at equator ≈ 111.32 km
        dist = haversine(0.0, 0.0, 0.0, 1.0)
        assert 110_000 < dist < 112_000

    def test_poles(self):
        # North pole to south pole ≈ half earth circumference ≈ 20,015 km
        dist = haversine(90.0, 0.0, -90.0, 0.0)
        assert 20_000_000 < dist < 20_100_000


class TestDecodeAndSampleRoute:
    # A simple encoded polyline for a straight-ish line (manually crafted or from real data)
    # This encodes roughly: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
    SAMPLE_POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"

    def test_returns_samples_and_distance(self):
        result = decode_and_sample_route(self.SAMPLE_POLYLINE, 3)
        assert isinstance(result, tuple)
        samples, total_dist = result
        assert len(samples) == 3
        assert total_dist > 0

    def test_sample_count_matches(self):
        samples, _ = decode_and_sample_route(self.SAMPLE_POLYLINE, 5)
        assert len(samples) == 5

    def test_single_sample(self):
        samples, _ = decode_and_sample_route(self.SAMPLE_POLYLINE, 1)
        assert len(samples) == 1
        # Midpoint fraction should be ~0.5
        assert 0.3 < samples[0]["fraction"] < 0.7

    def test_samples_are_ordered_by_distance(self):
        samples, _ = decode_and_sample_route(self.SAMPLE_POLYLINE, 5)
        distances = [s["distance_from_start"] for s in samples]
        assert distances == sorted(distances)

    def test_fractions_between_zero_and_one(self):
        samples, _ = decode_and_sample_route(self.SAMPLE_POLYLINE, 5)
        for s in samples:
            assert 0.0 < s["fraction"] < 1.0

    def test_sample_has_required_fields(self):
        samples, _ = decode_and_sample_route(self.SAMPLE_POLYLINE, 1)
        s = samples[0]
        assert "lat" in s
        assert "lng" in s
        assert "distance_from_start" in s
        assert "fraction" in s

    def test_too_few_points_returns_empty(self):
        # A polyline encoding a single point has no segments
        # Encoding for a single point (0,0): "??"
        result = decode_and_sample_route("??", 3)
        assert result == []

    def test_empty_polyline(self):
        result = decode_and_sample_route("", 3)
        assert result == []


class TestAttachVideos:
    def test_attaches_existing_video(self, seed_videos):
        cities = [{"full_name": "Columbus, OH"}]
        result = attach_videos(cities)
        assert result[0]["video"] is not None
        assert result[0]["video"]["youtube_id"] == "abc123"

    def test_none_for_missing_video(self, seed_videos):
        cities = [{"full_name": "Nonexistent, XX"}]
        result = attach_videos(cities)
        assert result[0]["video"] is None

    def test_mixed_found_and_not_found(self, seed_videos):
        cities = [
            {"full_name": "Columbus, OH"},
            {"full_name": "Unknown, ZZ"},
            {"full_name": "Dayton, OH"},
        ]
        result = attach_videos(cities)
        assert result[0]["video"] is not None
        assert result[1]["video"] is None
        assert result[2]["video"] is not None

    def test_empty_cities_list(self):
        assert attach_videos([]) == []

    def test_preserves_existing_city_fields(self, seed_videos):
        cities = [{"full_name": "Columbus, OH", "lat": 39.96, "lng": -82.99}]
        result = attach_videos(cities)
        assert result[0]["lat"] == 39.96
        assert result[0]["lng"] == -82.99
        assert "video" in result[0]
