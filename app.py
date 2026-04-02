import json
import math
import os
from flask import Flask, render_template, request, jsonify, send_from_directory
import googlemaps
import polyline as polyline_codec
import config
import db

app = Flask(__name__)

gmaps = None
if config.GOOGLE_MAPS_API_KEY:
    gmaps = googlemaps.Client(key=config.GOOGLE_MAPS_API_KEY)

# Initialize database on startup
db.init_db()


def load_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def haversine(lat1, lng1, lat2, lng2):
    """Distance in meters between two lat/lng points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def decode_and_sample_route(encoded_polyline, num_samples):
    """Decode a polyline and sample evenly-spaced points along it."""
    points = polyline_codec.decode(encoded_polyline)
    if len(points) < 2:
        return []

    # Compute cumulative distances
    cumulative = [0.0]
    for i in range(1, len(points)):
        d = haversine(points[i - 1][0], points[i - 1][1], points[i][0], points[i][1])
        cumulative.append(cumulative[-1] + d)

    total_distance = cumulative[-1]
    if total_distance == 0:
        return []

    # Sample at evenly spaced distances (skip start and end)
    samples = []
    for s in range(1, num_samples + 1):
        target_dist = total_distance * s / (num_samples + 1)
        # Find the segment this distance falls on
        for i in range(1, len(cumulative)):
            if cumulative[i] >= target_dist:
                # Interpolate within this segment
                seg_start = cumulative[i - 1]
                seg_len = cumulative[i] - cumulative[i - 1]
                if seg_len == 0:
                    frac = 0
                else:
                    frac = (target_dist - seg_start) / seg_len
                lat = points[i - 1][0] + frac * (points[i][0] - points[i - 1][0])
                lng = points[i - 1][1] + frac * (points[i][1] - points[i - 1][1])
                samples.append({
                    "lat": lat,
                    "lng": lng,
                    "distance_from_start": target_dist,
                    "fraction": target_dist / total_distance,
                })
                break

    return samples, total_distance


def identify_cities(samples, source_city, dest_city):
    """Reverse-geocode sampled points to find intermediate cities."""
    if not gmaps:
        return []

    cities = []
    seen = set()
    seen.add(source_city.lower() if source_city else "")
    seen.add(dest_city.lower() if dest_city else "")

    for sample in samples:
        try:
            results = gmaps.reverse_geocode((sample["lat"], sample["lng"]))
            city_name = None
            state_short = None
            for result in results:
                for comp in result.get("address_components", []):
                    types = comp.get("types", [])
                    if "locality" in types:
                        city_name = comp["long_name"]
                    if "administrative_area_level_1" in types:
                        state_short = comp["short_name"]
                if city_name:
                    break

            if city_name and city_name.lower() not in seen:
                seen.add(city_name.lower())
                full_name = f"{city_name}, {state_short}" if state_short else city_name
                cities.append({
                    "name": city_name,
                    "full_name": full_name,
                    "state": state_short,
                    "lat": sample["lat"],
                    "lng": sample["lng"],
                    "distance_from_start": sample["distance_from_start"],
                    "fraction_along_route": sample["fraction"],
                })
        except Exception:
            continue

    return cities


def attach_videos(cities):
    """Look up tourism videos for each city from the SQLite database."""
    for city in cities:
        video = db.get_video_for_city(city["full_name"])
        city["video"] = video
    return cities


# ── Page routes ──────────────────────────────────────────────────────────────

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static", "img"),
        "favicon.ico",
        mimetype="image/x-icon",
    )


@app.route("/")
def index():
    return render_template(
        "index.html",
        google_maps_api_key=config.GOOGLE_MAPS_API_KEY,
        speed_options=config.SPEED_OPTIONS,
    )


@app.route("/admin")
def admin():
    return render_template("admin.html")


# ── Trip API ─────────────────────────────────────────────────────────────────

@app.route("/api/route", methods=["POST"])
def get_route():
    data = request.get_json()
    source = data.get("source", "").strip()
    destination = data.get("destination", "").strip()

    if not source or not destination:
        return jsonify({"error": "Source and destination are required"}), 400

    if not gmaps:
        return jsonify({"error": "Google Maps API key not configured"}), 500

    try:
        directions = gmaps.directions(source, destination, mode="driving")
    except Exception as e:
        return jsonify({"error": f"Directions API error: {str(e)}"}), 500

    if not directions:
        return jsonify({"error": "No route found"}), 404

    route = directions[0]
    leg = route["legs"][0]

    overview_polyline = route["overview_polyline"]["points"]
    total_duration = leg["duration"]["value"]
    total_distance = leg["distance"]["value"]

    bounds = route["bounds"]

    # Extract source/destination city names for filtering
    source_city = ""
    dest_city = ""
    for comp in leg.get("start_address", "").split(","):
        source_city = comp.strip()
        break
    for comp in leg.get("end_address", "").split(","):
        dest_city = comp.strip()
        break

    # Sample points and identify cities
    sample_result = decode_and_sample_route(overview_polyline, config.ROUTE_SAMPLE_COUNT)
    if sample_result:
        samples, _ = sample_result
        cities = identify_cities(samples, source_city, dest_city)
        cities = attach_videos(cities)
    else:
        cities = []

    return jsonify({
        "overview_polyline": overview_polyline,
        "total_duration_seconds": total_duration,
        "total_distance_meters": total_distance,
        "bounds": bounds,
        "start_address": leg["start_address"],
        "end_address": leg["end_address"],
        "start_location": leg["start_location"],
        "end_location": leg["end_location"],
        "cities": cities,
    })


@app.route("/api/radio-stations")
def get_radio_stations():
    stations = db.get_stations_for_frontend()
    return jsonify({"stations": stations})


# ── Radio Stations CRUD API ──────────────────────────────────────────────────

@app.route("/api/stations", methods=["GET"])
def list_stations():
    return jsonify(db.get_all_stations())


@app.route("/api/stations", methods=["POST"])
def create_station():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    station_id = (data.get("station_id") or "").strip()
    name = (data.get("name") or "").strip()
    frequency = (data.get("frequency") or "").strip() or None
    stype = (data.get("type") or "").strip()
    source = (data.get("source") or "").strip()
    description = (data.get("description") or "").strip() or None
    sort_order = data.get("sort_order", 0)

    if not station_id or not name or not stype or not source:
        return jsonify({"error": "station_id, name, type, and source are required"}), 400

    if stype not in ("youtube", "mp3"):
        return jsonify({"error": "type must be 'youtube' or 'mp3'"}), 400

    try:
        sort_order = int(sort_order)
    except (ValueError, TypeError):
        sort_order = 0

    try:
        station = db.add_station(station_id, name, frequency, stype, source, description, sort_order)
        return jsonify(station), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 409


@app.route("/api/stations/<int:row_id>", methods=["PUT"])
def update_station(row_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    fields = {}
    for key in ("station_id", "name", "frequency", "type", "source", "description"):
        if key in data:
            fields[key] = (data[key] or "").strip() or None
    if "sort_order" in data:
        try:
            fields["sort_order"] = int(data["sort_order"])
        except (ValueError, TypeError):
            pass

    if "type" in fields and fields["type"] not in ("youtube", "mp3", None):
        return jsonify({"error": "type must be 'youtube' or 'mp3'"}), 400

    station = db.update_station(row_id, **fields)
    if station is None:
        return jsonify({"error": "Station not found"}), 404
    return jsonify(station)


@app.route("/api/stations/<int:row_id>", methods=["DELETE"])
def delete_station(row_id):
    if db.delete_station(row_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Station not found"}), 404


@app.route("/api/stations/import", methods=["POST"])
def import_stations():
    """One-time import from the legacy radio_stations.json file."""
    try:
        count = db.import_stations_from_json("radio_stations.json")
        return jsonify({"imported": count})
    except FileNotFoundError:
        return jsonify({"error": "radio_stations.json not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Videos CRUD API ──────────────────────────────────────────────────────────

@app.route("/api/videos/lookup", methods=["POST"])
def lookup_videos():
    """Look up videos for a list of city full_names. Used by the frontend
    to refresh video data for cities along the current route mid-trip."""
    data = request.get_json()
    city_names = data.get("cities", []) if data else []
    result = {}
    for name in city_names:
        video = db.get_video_for_city(name)
        if video:
            result[name] = video
    return jsonify(result)


@app.route("/api/videos", methods=["GET"])
def list_videos():
    return jsonify(db.get_all_videos())


@app.route("/api/videos", methods=["POST"])
def create_video():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    city_name = (data.get("city_name") or "").strip()
    state = (data.get("state") or "").strip()
    youtube_id = (data.get("youtube_id") or "").strip()
    title = (data.get("title") or "").strip() or None
    duration_seconds = data.get("duration_seconds")

    if not city_name or not youtube_id:
        return jsonify({"error": "city_name and youtube_id are required"}), 400

    if duration_seconds is not None:
        try:
            duration_seconds = int(duration_seconds)
        except (ValueError, TypeError):
            duration_seconds = None

    try:
        video = db.add_video(city_name, state, youtube_id, title, duration_seconds)
        return jsonify(video), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 409


@app.route("/api/videos/<int:video_id>", methods=["PUT"])
def update_video(video_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    fields = {}
    for key in ("city_name", "state", "youtube_id", "title"):
        if key in data:
            fields[key] = (data[key] or "").strip() or None
    if "duration_seconds" in data:
        try:
            fields["duration_seconds"] = int(data["duration_seconds"]) if data["duration_seconds"] else None
        except (ValueError, TypeError):
            pass

    video = db.update_video(video_id, **fields)
    if video is None:
        return jsonify({"error": "Video not found"}), 404
    return jsonify(video)


@app.route("/api/videos/<int:video_id>", methods=["DELETE"])
def delete_video(video_id):
    if db.delete_video(video_id):
        return jsonify({"ok": True})
    return jsonify({"error": "Video not found"}), 404


@app.route("/api/videos/import", methods=["POST"])
def import_videos():
    """One-time import from the legacy city_videos.json file."""
    try:
        count = db.import_from_json("data/city_videos.json")
        return jsonify({"imported": count})
    except FileNotFoundError:
        return jsonify({"error": "city_videos.json not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=12398)
