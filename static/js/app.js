/**
 * app.js — Entry point. Wires together map, radio, video, and trip controller.
 */

// Google Maps ready callback (called by the Maps script)
function onGoogleMapsReady() {
    MapController.init();
    console.log("Google Maps initialized");
}

// YouTube IFrame API ready callback (called automatically by the API)
function onYouTubeIframeAPIReady() {
    console.log("YouTube IFrame API ready");
    initApp();
}

function initApp() {
    // Initialize modules
    RadioPlayer.init();
    VideoPlayer.init(() => TripController.onVideoEnd());

    // Load radio stations
    fetch("/api/radio-stations")
        .then((r) => r.json())
        .then((data) => {
            RadioPlayer.loadStations(data.stations || []);
            // Auto-select first station
            if (data.stations && data.stations.length > 0) {
                RadioPlayer.switchStation(data.stations[0].id);
                // Don't auto-play yet — wait for trip start
                RadioPlayer.pause();
            }
        })
        .catch((err) => console.warn("Failed to load radio stations:", err));

    // Volume slider
    document.getElementById("volume-slider").addEventListener("input", (e) => {
        RadioPlayer.setVolume(parseInt(e.target.value, 10));
    });

    // Start button
    document.getElementById("start-btn").addEventListener("click", () => {
        const source = document.getElementById("source").value.trim();
        const destination = document.getElementById("destination").value.trim();
        const speed = parseInt(document.getElementById("speed").value, 10);

        if (!source || !destination) {
            alert("Please enter a source and destination");
            return;
        }

        TripController.start(source, destination, speed);
    });

    // New trip button (on arrival overlay)
    document.getElementById("new-trip-btn").addEventListener("click", () => {
        TripController.reset();
    });

    // Enter key on inputs triggers start
    document.getElementById("source").addEventListener("keydown", (e) => {
        if (e.key === "Enter") document.getElementById("start-btn").click();
    });
    document.getElementById("destination").addEventListener("keydown", (e) => {
        if (e.key === "Enter") document.getElementById("start-btn").click();
    });
}

// If YouTube API loads before Maps, wait; if Maps loads first, initApp runs on YT ready.
// If both loaded, initApp has guards against double-init via module patterns.
