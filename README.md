# DriftTrip

DriftTrip is a Flask-powered virtual road trip app. Enter a start and destination, then watch an animated car follow a Google Maps driving route while road-trip radio plays and tourism videos appear at sampled cities along the way.

The app includes:

- A Google Maps frontend with animated route playback.
- Server-side Google Directions and reverse geocoding calls.
- YouTube tourism videos attached to cities along the route.
- Road trip radio stations backed by SQLite.
- An admin page for managing videos, radio stations, and city coverage.

## Project Structure

```text
app.py                  Flask routes and API endpoints
config.py               Environment-driven app configuration
db.py                   SQLite schema, CRUD helpers, and import utilities
templates/index.html    Main trip UI
templates/admin.html    Admin UI
static/js/              Map, trip, video, and radio controllers
static/css/style.css    App styling
tests/                  Pytest test suite
```

Runtime data is stored in `data/city_videos.db`. The database is created automatically when the app starts.

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
pip install pytest
```

Create a `.env` file:

```bash
GOOGLE_MAPS_FRONTEND_API_KEY=your_browser_key
GOOGLE_MAPS_SERVER_API_KEY=your_server_key
YOUTUBE_DATA_API_KEY=

# Required: credentials for the admin page and all data-modifying API calls
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose-a-strong-password
```

`GOOGLE_MAPS_API_KEY` is still supported as a fallback for both Maps keys, but separate keys are strongly recommended: sharing one key means the server key is rendered into public page HTML. The app logs a loud warning at startup if both keys are set to the same value.

## Google API Keys

Use two Google Maps Platform keys:

- `GOOGLE_MAPS_FRONTEND_API_KEY`: rendered into the browser and used by the Maps JavaScript API.
- `GOOGLE_MAPS_SERVER_API_KEY`: kept on the server and used for Directions API and reverse geocoding via the Python `googlemaps` client.

Suggested restrictions (set in the Google Cloud Console — the referrer/IP restrictions are the actual controls; browser keys are public by design):

- Frontend key: restrict by HTTP referrer to your own origins and enable only the Maps JavaScript API. Without a referrer restriction, any third-party website can embed the key and run billable map loads against your project.
- Server key: restrict by server IP address where possible and enable only the Directions API and Geocoding API.

For local development, make sure your frontend key allows the local origin you use, such as `http://localhost:12398/*`.

## Admin Authentication & Security

The admin page (`/admin`) and every data-modifying API call (create/update/delete/import for videos, stations, and cities) are protected with HTTP Basic auth using `ADMIN_USERNAME` / `ADMIN_PASSWORD`. When the browser prompts for credentials on `/admin`, enter those values; the admin UI's API calls then work unchanged. If `ADMIN_PASSWORD` is not set, these endpoints refuse to serve (HTTP 503) — the app fails closed rather than running open.

Two endpoints used by the public trip page stay open but are rate limited per client IP:

- `POST /api/route` — capped at `RATE_LIMIT_ROUTE_PER_MINUTE` requests/minute (default 10); identical source/destination pairs are served from a short-lived cache so repeats don't burn Google Maps quota.
- `POST /api/videos/lookup` — capped at `RATE_LIMIT_LOOKUP_PER_MINUTE` requests/minute (default 60).

Failed login attempts are throttled at `RATE_LIMIT_AUTH_FAILURES_PER_MINUTE` per IP (default 10). Set any of these env vars to `0` to disable a limit. Request bodies larger than 64 KB are rejected, and all write endpoints validate field types and maximum lengths.

## Running the App

Development:

```bash
python app.py
```

This binds to `127.0.0.1:12398` by default (override with `HOST` / `PORT` env vars). Debug mode is off by default; `FLASK_DEBUG=1` enables the interactive Werkzeug debugger for local development only — never run it on a publicly reachable interface, since the debugger exposes source code and a Python console.

Production:

```bash
gunicorn -w 2 -b 0.0.0.0:12398 app:app
```

Then open:

- Main app: `http://localhost:12398/`
- Admin page: `http://localhost:12398/admin`

## Data Management

The admin UI uses these API-backed resources:

- Videos: `/api/videos`
- Radio stations: `/api/stations`
- City checklist: `/api/cities`

There are also one-time import endpoints for older JSON data:

- `POST /api/videos/import` imports from `data/city_videos.json`.
- `POST /api/stations/import` imports from `radio_stations.json`.
- `POST /api/cities/populate` fetches and imports the top-1000 US cities CSV used by the coverage checklist.

Radio stations can be either:

- `youtube`: `source` is a YouTube video or stream ID.
- `mp3`: `source` is a filename served from `/static/audio/`.

## Testing

Run the test suite with:

```bash
pytest -q
```

The tests redirect SQLite to temporary databases and clear Google Maps key environment variables so route validation does not depend on local secrets.

## Development Notes

- The frontend waits for both Google Maps and the YouTube IFrame API before enabling trip start.
- Route planning happens on the server through `/api/route`.
- Intermediate cities are detected by sampling the route polyline and reverse geocoding those sampled points.
- Tourism videos are looked up by city full name, for example `Columbus, OH`.
- During a trip, the frontend periodically refreshes video metadata from the server so admin changes can appear without restarting the trip.
