import hmac
import math
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from werkzeug.exceptions import HTTPException
from flask import Flask, render_template, request, jsonify, send_from_directory
import googlemaps
import requests as http_requests
import polyline as polyline_codec
import config
import db

app = Flask(__name__)

# Refuse absurdly large request bodies before Werkzeug buffers them.
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

gmaps = None
if config.GOOGLE_MAPS_SERVER_API_KEY:
    gmaps = googlemaps.Client(key=config.GOOGLE_MAPS_SERVER_API_KEY, timeout=10)

# Initialize database on startup
db.init_db()


# ── Authentication ───────────────────────────────────────────────────────────
#
# /admin and every mutating /api endpoint require HTTP Basic auth with the
# ADMIN_USERNAME / ADMIN_PASSWORD credentials. The two public write endpoints
# used by the frontend (/api/route, /api/videos/lookup) stay open but are
# rate limited below. Failed auth attempts are throttled per IP to slow
# credential brute-forcing.
#
# The app fails closed: with no ADMIN_PASSWORD configured, protected
# endpoints return 503 instead of serving anonymously.

_PUBLIC_API_WRITES = {"/api/route", "/api/videos/lookup"}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_rate_lock = threading.Lock()
_rate_buckets = defaultdict(deque)
_RATE_WINDOW_SECONDS = 60.0
_MAX_RATE_BUCKETS = 10_000


def _rate_limit_hit(key, limit_per_minute):
    """Record a hit for key and return True if it is within the limit."""
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets[key]
        cutoff = now - _RATE_WINDOW_SECONDS
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(_rate_buckets) > _MAX_RATE_BUCKETS:
            for stale in [k for k, b in _rate_buckets.items() if not b or b[0] <= cutoff]:
                del _rate_buckets[stale]
        if limit_per_minute and len(bucket) >= limit_per_minute:
            return False
        bucket.append(now)
        return True


def _clear_rate_buckets():
    """Test helper: reset all rate-limit counters."""
    with _rate_lock:
        _rate_buckets.clear()


def _check_admin_credentials():
    auth = request.authorization
    if auth is None or (auth.type or "").lower() != "basic":
        return False
    username = (auth.username or "").encode("utf-8")
    password = (auth.password or "").encode("utf-8")
    return hmac.compare_digest(username, config.ADMIN_USERNAME.encode("utf-8")) and \
        hmac.compare_digest(password, config.ADMIN_PASSWORD.encode("utf-8"))


def _unauthorized_response():
    return jsonify({"error": "Authentication required"}), 401, {
        "WWW-Authenticate": 'Basic realm="DriftTrip admin", charset="UTF-8"'
    }


@app.before_request
def enforce_access_control():
    path = request.path
    is_public_write = path in _PUBLIC_API_WRITES

    # Throttle the unauthenticated write endpoints the public frontend uses,
    # so they cannot be abused to burn Google Maps quota or hammer SQLite.
    if is_public_write:
        limit = (
            config.RATE_LIMIT_ROUTE_PER_MINUTE
            if path == "/api/route"
            else config.RATE_LIMIT_LOOKUP_PER_MINUTE
        )
        bucket_key = f"public:{request.remote_addr}:{path}"
        if not _rate_limit_hit(bucket_key, limit):
            return jsonify({"error": "Rate limit exceeded. Try again later."}), 429

    is_admin_area = path == "/admin" or path.startswith("/admin/")
    needs_auth = is_admin_area or (
        path.startswith("/api/") and request.method in _WRITE_METHODS and not is_public_write
    )
    if not needs_auth:
        return None

    if not config.ADMIN_PASSWORD:
        app.logger.error(
            "Refusing request to %s: admin authentication is not configured "
            "(set ADMIN_USERNAME and ADMIN_PASSWORD).", path
        )
        return jsonify({
            "error": "Admin authentication is not configured. "
                     "Set ADMIN_USERNAME and ADMIN_PASSWORD."
        }), 503

    if _check_admin_credentials():
        return None

    client_ip = request.remote_addr or "unknown"
    if not _rate_limit_hit(f"authfail:{client_ip}", config.RATE_LIMIT_AUTH_FAILURES_PER_MINUTE):
        return jsonify({"error": "Too many failed login attempts. Try again later."}), 429
    return _unauthorized_response()


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    if isinstance(e, HTTPException):
        return e
    app.logger.exception("Unhandled error on %s %s", request.method, request.path)
    return jsonify({"error": "Internal server error"}), 500


# ── Request validation helpers ───────────────────────────────────────────────

def _json_body():
    """Parse the request body as a JSON object. Returns None for anything else."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _clean_str(value, field, max_length, required=False):
    """Validate an optional string field. Returns (cleaned, error)."""
    if value is None:
        if required:
            return None, f"{field} is required"
        return None, None
    if not isinstance(value, str):
        return None, f"{field} must be a string"
    cleaned = value.strip()
    if required and not cleaned:
        return None, f"{field} is required"
    if len(cleaned) > max_length:
        return None, f"{field} must be at most {max_length} characters"
    return cleaned or None, None


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


# ── Route response cache ─────────────────────────────────────────────────────
#
# Identical source/destination pairs repeat a lot (users retry, share links,
# scripts loop). Caching successful responses keeps the billable Google Maps
# calls at one-per-unique-route instead of one-per-request.

_route_cache = {}
_route_cache_lock = threading.Lock()


def _route_cache_get(key):
    now = time.monotonic()
    with _route_cache_lock:
        entry = _route_cache.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if expires_at <= now:
            del _route_cache[key]
            return None
        return payload


def _route_cache_put(key, payload):
    now = time.monotonic()
    with _route_cache_lock:
        if len(_route_cache) >= config.ROUTE_CACHE_MAX_ENTRIES:
            for stale in [k for k, (exp, _) in _route_cache.items() if exp <= now]:
                del _route_cache[stale]
            if len(_route_cache) >= config.ROUTE_CACHE_MAX_ENTRIES:
                _route_cache.pop(next(iter(_route_cache)))
        _route_cache[key] = (now + config.ROUTE_CACHE_TTL_SECONDS, payload)


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
        google_maps_api_key=config.GOOGLE_MAPS_FRONTEND_API_KEY,
        speed_options=config.SPEED_OPTIONS,
    )


@app.route("/admin")
def admin():
    return render_template("admin.html")


# ── Trip API ─────────────────────────────────────────────────────────────────

@app.route("/api/route", methods=["POST"])
def get_route():
    data = _json_body()
    if data is None:
        return jsonify({"error": "JSON object body required"}), 400

    source, err = _clean_str(data.get("source"), "source", config.ROUTE_FIELD_LIMIT, required=True)
    if err:
        return jsonify({"error": err}), 400
    destination, err = _clean_str(data.get("destination"), "destination", config.ROUTE_FIELD_LIMIT, required=True)
    if err:
        return jsonify({"error": err}), 400

    if not gmaps:
        return jsonify({"error": "Google Maps API key not configured"}), 500

    cache_key = (source, destination)
    cached = _route_cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        directions = gmaps.directions(source, destination, mode="driving")
    except Exception:
        # Never echo exception text to clients: transport errors from the
        # googlemaps client embed the full request URL, including the key.
        app.logger.exception("Directions API request failed")
        return jsonify({"error": "Directions request failed"}), 500

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

    payload = {
        "overview_polyline": overview_polyline,
        "total_duration_seconds": total_duration,
        "total_distance_meters": total_distance,
        "bounds": bounds,
        "start_address": leg["start_address"],
        "end_address": leg["end_address"],
        "start_location": leg["start_location"],
        "end_location": leg["end_location"],
        "cities": cities,
    }
    _route_cache_put(cache_key, payload)
    return jsonify(payload)


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
    data = _json_body()
    if data is None:
        return jsonify({"error": "JSON object body required"}), 400

    fields = {}
    for key in ("station_id", "name", "frequency", "type", "source", "description"):
        value, err = _clean_str(data.get(key), key, config.FIELD_LENGTH_LIMITS[key])
        if err:
            return jsonify({"error": err}), 400
        fields[key] = value

    station_id = fields["station_id"]
    name = fields["name"]
    frequency = fields["frequency"]
    stype = fields["type"]
    source = fields["source"]
    description = fields["description"]
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
    except sqlite3.IntegrityError:
        return jsonify({"error": "Could not create station: it already exists"}), 409
    except Exception:
        app.logger.exception("Failed to create station")
        return jsonify({"error": "Failed to create station"}), 500


@app.route("/api/stations/<int:row_id>", methods=["PUT"])
def update_station(row_id):
    data = _json_body()
    if not data:
        return jsonify({"error": "JSON object body required"}), 400

    fields = {}
    for key in ("station_id", "name", "frequency", "type", "source", "description"):
        if key in data:
            value, err = _clean_str(data[key], key, config.FIELD_LENGTH_LIMITS[key])
            if err:
                return jsonify({"error": err}), 400
            fields[key] = value
    if "sort_order" in data:
        try:
            fields["sort_order"] = int(data["sort_order"])
        except (ValueError, TypeError):
            pass

    if "type" in fields and fields["type"] not in ("youtube", "mp3", None):
        return jsonify({"error": "type must be 'youtube' or 'mp3'"}), 400

    try:
        station = db.update_station(row_id, **fields)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Update conflicts with existing station data"}), 409
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
    except Exception:
        app.logger.exception("Station import failed")
        return jsonify({"error": "Station import failed"}), 500


# ── Videos CRUD API ──────────────────────────────────────────────────────────

@app.route("/api/videos/lookup", methods=["POST"])
def lookup_videos():
    """Look up videos for a list of city full_names. Used by the frontend
    to refresh video data for cities along the current route mid-trip."""
    data = _json_body()
    if data is None:
        return jsonify({"error": "JSON object body required"}), 400

    city_names = data.get("cities", [])
    if not isinstance(city_names, list) or len(city_names) > config.MAX_LOOKUP_CITIES:
        return jsonify({"error": f"cities must be a list of at most {config.MAX_LOOKUP_CITIES} names"}), 400

    result = {}
    for name in city_names:
        if not isinstance(name, str) or len(name) > config.ROUTE_FIELD_LIMIT:
            return jsonify({"error": "each city name must be a string of at most "
                                     f"{config.ROUTE_FIELD_LIMIT} characters"}), 400
        name = name.strip()
        if not name:
            continue
        video = db.get_video_for_city(name)
        if video:
            result[name] = video
    return jsonify(result)


@app.route("/api/videos", methods=["GET"])
def list_videos():
    return jsonify(db.get_all_videos())


@app.route("/api/videos", methods=["POST"])
def create_video():
    data = _json_body()
    if data is None:
        return jsonify({"error": "JSON object body required"}), 400

    fields = {}
    for key in ("city_name", "state", "youtube_id", "title"):
        value, err = _clean_str(data.get(key), key, config.FIELD_LENGTH_LIMITS[key])
        if err:
            return jsonify({"error": err}), 400
        fields[key] = value

    city_name = fields["city_name"]
    state = fields["state"]
    youtube_id = fields["youtube_id"]
    title = fields["title"]
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
    except sqlite3.IntegrityError:
        return jsonify({"error": "Could not create video: it already exists"}), 409
    except Exception:
        app.logger.exception("Failed to create video")
        return jsonify({"error": "Failed to create video"}), 500


@app.route("/api/videos/<int:video_id>", methods=["PUT"])
def update_video(video_id):
    data = _json_body()
    if not data:
        return jsonify({"error": "JSON object body required"}), 400

    fields = {}
    for key in ("city_name", "state", "youtube_id", "title"):
        if key in data:
            value, err = _clean_str(data[key], key, config.FIELD_LENGTH_LIMITS[key])
            if err:
                return jsonify({"error": err}), 400
            fields[key] = value
    if "duration_seconds" in data:
        try:
            fields["duration_seconds"] = int(data["duration_seconds"]) if data["duration_seconds"] else None
        except (ValueError, TypeError):
            pass

    try:
        video = db.update_video(video_id, **fields)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Update conflicts with existing video data"}), 409
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
    except Exception:
        app.logger.exception("Video import failed")
        return jsonify({"error": "Video import failed"}), 500


# ── Cities Checklist API ─────────────────────────────────────────────────────

@app.route("/api/cities", methods=["GET"])
def list_cities():
    return jsonify(db.get_cities_with_status())


@app.route("/api/cities/stats", methods=["GET"])
def cities_stats():
    return jsonify(db.get_cities_count())


@app.route("/api/cities/populate", methods=["POST"])
def populate_cities():
    """Fetch the top-1000 US cities CSV and populate the cities table."""
    try:
        resp = http_requests.get(db.CITIES_CSV_URL, timeout=30)
        resp.raise_for_status()
    except Exception:
        app.logger.exception("Failed to fetch cities CSV")
        return jsonify({"error": "Failed to fetch cities CSV"}), 502

    count = db.populate_cities(resp.text)
    return jsonify({"imported": count})


if __name__ == "__main__":
    # Never run the Werkzeug interactive debugger in production: it exposes
    # source code and (with the PIN) a live Python console to the network.
    # Use FLASK_DEBUG=1 only for local development. Bind to localhost by
    # default; set HOST=0.0.0.0 only behind a reverse proxy or firewall.
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "12398")),
        debug=os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes"),
    )
