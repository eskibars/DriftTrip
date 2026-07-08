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
```

`GOOGLE_MAPS_API_KEY` is still supported as a fallback for both Maps keys, but separate keys are recommended so each one can have tighter restrictions.

## Google API Keys

Use two Google Maps Platform keys:

- `GOOGLE_MAPS_FRONTEND_API_KEY`: rendered into the browser and used by the Maps JavaScript API.
- `GOOGLE_MAPS_SERVER_API_KEY`: kept on the server and used for Directions API and reverse geocoding via the Python `googlemaps` client.

Suggested restrictions:

- Frontend key: restrict by HTTP referrer and enable Maps JavaScript API.
- Server key: restrict by server IP address where possible and enable Directions API and Geocoding API.

For local development, make sure your frontend key allows the local origin you use, such as `http://localhost:12398/*`.

## Running the App

```bash
python app.py
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
