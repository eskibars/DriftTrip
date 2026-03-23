import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
YOUTUBE_DATA_API_KEY = os.getenv("YOUTUBE_DATA_API_KEY", "")

SPEED_OPTIONS = [2, 5, 10, 20, 50, 100]

# How many points to sample along route for city detection
ROUTE_SAMPLE_COUNT = 15

# Minimum distance between sampled cities (meters) to avoid duplicates
MIN_CITY_DISTANCE = 20000
