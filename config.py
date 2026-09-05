import os
import sys
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
GOOGLE_MAPS_FRONTEND_API_KEY = os.getenv("GOOGLE_MAPS_FRONTEND_API_KEY", GOOGLE_MAPS_API_KEY)
GOOGLE_MAPS_SERVER_API_KEY = os.getenv("GOOGLE_MAPS_SERVER_API_KEY", GOOGLE_MAPS_API_KEY)
YOUTUBE_DATA_API_KEY = os.getenv("YOUTUBE_DATA_API_KEY", "")

# The frontend key is embedded in public HTML, so it must be a separate,
# HTTP-referrer-restricted browser key. Sharing the server key would leak it.
if GOOGLE_MAPS_SERVER_API_KEY and GOOGLE_MAPS_SERVER_API_KEY == GOOGLE_MAPS_FRONTEND_API_KEY:
    print(
        "WARNING: GOOGLE_MAPS_FRONTEND_API_KEY and GOOGLE_MAPS_SERVER_API_KEY are the same key. "
        "The frontend key is exposed in public page HTML; configure a separate, "
        "referrer-restricted browser key via GOOGLE_MAPS_FRONTEND_API_KEY.",
        file=sys.stderr,
    )

# ── Admin authentication ─────────────────────────────────────────────────────
# Protects /admin and every mutating /api endpoint with HTTP Basic auth.
# The app fails closed: until ADMIN_PASSWORD is set, those endpoints refuse
# to serve with a 503 telling the operator what to configure.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# ── Request limits ───────────────────────────────────────────────────────────
# Reject request bodies larger than this (bytes) before they are buffered.
MAX_CONTENT_LENGTH = 64 * 1024

# Per-field max lengths for API-created records.
FIELD_LENGTH_LIMITS = {
    "station_id": 100,
    "name": 200,
    "frequency": 20,
    "type": 10,
    "source": 500,
    "description": 2000,
    "city_name": 200,
    "state": 50,
    "youtube_id": 100,
    "title": 300,
}

# /api/route inputs and /api/videos/lookup list are also capped.
ROUTE_FIELD_LIMIT = 200
MAX_LOOKUP_CITIES = 100

# ── Rate limiting (per client IP, sliding one-minute window) ────────────────
# Applies to the unauthenticated endpoints the public frontend uses.
# Set an env var to 0 to disable that limit.
RATE_LIMIT_ROUTE_PER_MINUTE = int(os.getenv("RATE_LIMIT_ROUTE_PER_MINUTE", "10"))
RATE_LIMIT_LOOKUP_PER_MINUTE = int(os.getenv("RATE_LIMIT_LOOKUP_PER_MINUTE", "60"))
RATE_LIMIT_AUTH_FAILURES_PER_MINUTE = int(os.getenv("RATE_LIMIT_AUTH_FAILURES_PER_MINUTE", "10"))

# ── Route cache ──────────────────────────────────────────────────────────────
# Successful /api/route responses are cached so repeated identical requests
# do not burn billable Google Maps quota.
ROUTE_CACHE_TTL_SECONDS = 600
ROUTE_CACHE_MAX_ENTRIES = 256

SPEED_OPTIONS = [0.5, 1, 2, 5, 10, 20, 50, 100]

# How many points to sample along route for city detection
ROUTE_SAMPLE_COUNT = 15

# Minimum distance between sampled cities (meters) to avoid duplicates
MIN_CITY_DISTANCE = 20000
