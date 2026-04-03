/**
 * app.js — Entry point. Wires together map, radio, video, and trip controller.
 *
 * Both Google Maps and YouTube IFrame API load async. We gate on both being
 * ready before enabling the UI, so there's no race condition on slow connections.
 */

let _mapsReady = false;
let _ytReady = false;
let _appInitialized = false;

// Google Maps ready callback (called by the Maps script tag)
function onGoogleMapsReady() {
    _mapsReady = true;
    MapController.init();
    console.log("Google Maps initialized");
    maybeInitApp();
}

// YouTube IFrame API ready callback (called automatically by the API script)
function onYouTubeIframeAPIReady() {
    _ytReady = true;
    console.log("YouTube IFrame API ready");
    maybeInitApp();
}

function maybeInitApp() {
    if (_mapsReady && _ytReady && !_appInitialized) {
        _appInitialized = true;
        initApp();
    }
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

    // Radio pause/resume button
    document.getElementById("radio-pause-btn").addEventListener("click", () => {
        RadioPlayer.toggle();
    });

    // Volume slider
    document.getElementById("volume-slider").addEventListener("input", (e) => {
        RadioPlayer.setVolume(parseInt(e.target.value, 10));
    });

    // Enable the start button now that both APIs are loaded
    const startBtn = document.getElementById("start-btn");
    startBtn.disabled = false;
    startBtn.textContent = "Start Road Trip";

    // Start button
    startBtn.addEventListener("click", () => {
        const source = document.getElementById("source").value.trim();
        const destination = document.getElementById("destination").value.trim();
        const speed = parseFloat(document.getElementById("speed").value);

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
