/**
 * trip.js — Trip state machine.
 *
 * States: IDLE → LOADING → DRIVING → AT_CITY → DRIVING → ... → ARRIVED
 * Coordinates map animation, radio playback, and tourism video playback.
 */
const TripController = (function () {
    // States
    const IDLE = "IDLE";
    const LOADING = "LOADING";
    const DRIVING = "DRIVING";
    const AT_CITY = "AT_CITY";
    const ARRIVED = "ARRIVED";

    let state = IDLE;
    let routeData = null;
    let cities = [];
    let speedMultiplier = 10;
    let tripStartTime = null;
    let citiesVisited = 0;
    let videoRefreshTimer = null;

    // City proximity threshold (fraction of total route)
    const CITY_THRESHOLD = 0.008;

    // How often to refresh video data from the server (ms)
    const VIDEO_REFRESH_INTERVAL = 60000;

    function getState() {
        return state;
    }

    function setState(newState) {
        state = newState;
        console.log(`Trip state: ${state}`);
    }

    function setSpeed(s) {
        speedMultiplier = s;
        MapController.setSpeed(s);
        updateSpeedUI();
    }

    async function start(source, destination, speed) {
        if (state !== IDLE) return;

        setState(LOADING);
        speedMultiplier = speed;
        MapController.setSpeed(speed);
        citiesVisited = 0;

        updateStatusText("Planning your route...");
        document.getElementById("start-btn").disabled = true;

        try {
            const resp = await fetch("/api/route", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ source, destination }),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.error || "Failed to get route");
            }

            routeData = await resp.json();
            cities = (routeData.cities || []).map((c) => ({ ...c, visited: false }));

            // Draw route on map
            MapController.drawRoute(routeData);

            // Populate UI
            renderCitiesList();
            showTripUI();

            updateStatusText("On the road!");

            // Start radio (first station)
            const station = RadioPlayer.getCurrentStation();
            if (station) {
                RadioPlayer.play();
            }

            // Start periodic video refresh
            startVideoRefresh();

            // Start car animation
            setState(DRIVING);
            tripStartTime = Date.now();
            MapController.startAnimation(onProgress);
        } catch (err) {
            alert("Error: " + err.message);
            setState(IDLE);
            document.getElementById("start-btn").disabled = false;
        }
    }

    function onProgress(fraction) {
        // Update progress bar
        const pct = Math.min(100, Math.round(fraction * 100));
        document.getElementById("progress-fill").style.width = pct + "%";
        document.getElementById("progress-percent").textContent = pct + "%";

        // ETA
        if (routeData && speedMultiplier > 0) {
            const remaining = routeData.total_duration_seconds * (1 - fraction) / speedMultiplier;
            document.getElementById("eta-text").textContent = formatDuration(remaining) + " remaining";
        }

        // Check for city proximity
        if (state === DRIVING) {
            checkCityProximity(fraction);
        }

        // Check for arrival
        if (fraction >= 1) {
            arrive();
        }
    }

    function checkCityProximity(currentFraction) {
        for (const city of cities) {
            if (city.visited) continue;
            if (Math.abs(currentFraction - city.fraction_along_route) < CITY_THRESHOLD) {
                city.visited = true;
                citiesVisited++;
                enterCity(city);
                return;
            }
        }
    }

    function enterCity(city) {
        setState(AT_CITY);

        // Pause driving
        MapController.pause();
        RadioPlayer.pause();

        // Update cities list UI
        renderCitiesList();

        updateStatusText(`Exploring ${city.full_name}`);

        // Show video
        VideoPlayer.show(city);
    }

    function onVideoEnd() {
        // Called by VideoPlayer when video ends or is skipped
        if (state !== AT_CITY) return;

        setState(DRIVING);
        updateStatusText("On the road!");

        // Resume
        RadioPlayer.play();
        MapController.resume();
    }

    function arrive() {
        setState(ARRIVED);
        stopVideoRefresh();
        MapController.stop();
        RadioPlayer.pause();

        updateStatusText("You've arrived!");

        // Show arrival overlay
        const overlay = document.getElementById("arrival-overlay");
        document.getElementById("arrival-destination").textContent = routeData.end_address;

        const elapsed = (Date.now() - tripStartTime) / 1000;
        const distKm = (routeData.total_distance_meters / 1000).toFixed(0);
        const distMi = (routeData.total_distance_meters / 1609.34).toFixed(0);

        document.getElementById("trip-summary").innerHTML =
            `Distance: ${distMi} miles (${distKm} km)<br>` +
            `Real time: ${formatDuration(elapsed)}<br>` +
            `Speed: ${speedMultiplier}x<br>` +
            `Cities visited: ${citiesVisited}`;

        overlay.classList.remove("hidden");
    }

    function reset() {
        setState(IDLE);
        stopVideoRefresh();
        MapController.stop();
        MapController.clearRoute();
        RadioPlayer.pause();
        VideoPlayer.hide();
        routeData = null;
        cities = [];
        citiesVisited = 0;

        document.getElementById("start-btn").disabled = false;
        document.getElementById("arrival-overlay").classList.add("hidden");
        document.getElementById("progress-fill").style.width = "0%";
        document.getElementById("progress-percent").textContent = "0%";
        document.getElementById("eta-text").textContent = "";

        hideTripUI();
        updateStatusText("Enter your route and hit Start!");
    }

    // --- Video refresh polling ---

    function startVideoRefresh() {
        stopVideoRefresh();
        videoRefreshTimer = setInterval(refreshCityVideos, VIDEO_REFRESH_INTERVAL);
    }

    function stopVideoRefresh() {
        if (videoRefreshTimer) {
            clearInterval(videoRefreshTimer);
            videoRefreshTimer = null;
        }
    }

    async function refreshCityVideos() {
        // Only refresh for cities we haven't visited yet
        const unvisited = cities.filter(c => !c.visited);
        if (unvisited.length === 0) return;

        const cityNames = unvisited.map(c => c.full_name);
        try {
            const resp = await fetch("/api/videos/lookup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cities: cityNames }),
            });
            if (!resp.ok) return;

            const videoMap = await resp.json();
            let changed = false;

            for (const city of cities) {
                if (city.visited) continue;
                const freshVideo = videoMap[city.full_name] || null;
                const hadVideo = city.video ? city.video.youtube_id : null;
                const hasVideo = freshVideo ? freshVideo.youtube_id : null;

                if (hadVideo !== hasVideo || (freshVideo && city.video && freshVideo.title !== city.video.title)) {
                    city.video = freshVideo;
                    changed = true;
                }
            }

            if (changed) {
                renderCitiesList();
                console.log("City videos refreshed from server");
            }
        } catch (e) {
            // Silent fail — will retry next interval
        }
    }

    // --- UI helpers ---

    function updateStatusText(text) {
        document.getElementById("status-text").textContent = text;
    }

    function showTripUI() {
        document.getElementById("progress-container").classList.remove("hidden");
        document.getElementById("speed-control").classList.remove("hidden");
        document.getElementById("cities-section").classList.remove("hidden");
        renderSpeedButtons();
    }

    function hideTripUI() {
        document.getElementById("progress-container").classList.add("hidden");
        document.getElementById("speed-control").classList.add("hidden");
        document.getElementById("cities-section").classList.add("hidden");
        document.getElementById("video-section").classList.add("hidden");
        document.getElementById("city-arrival").classList.add("hidden");
    }

    function renderCitiesList() {
        const ul = document.getElementById("cities-list");
        ul.innerHTML = "";
        for (const city of cities) {
            const li = document.createElement("li");
            li.className = city.visited ? "visited" : "";
            li.innerHTML = `<span class="city-dot"></span> ${city.full_name}`;
            if (city.video) {
                li.innerHTML += ` <span style="font-size:10px; color:var(--text-dim);">&#127909;</span>`;
            }
            ul.appendChild(li);
        }
    }

    function renderSpeedButtons() {
        const container = document.getElementById("speed-buttons");
        container.innerHTML = "";
        for (const s of window.SPEED_OPTIONS) {
            const btn = document.createElement("button");
            btn.className = "speed-btn" + (s === speedMultiplier ? " active" : "");
            btn.textContent = s + "x";
            btn.addEventListener("click", () => setSpeed(s));
            container.appendChild(btn);
        }
    }

    function updateSpeedUI() {
        document.querySelectorAll(".speed-btn").forEach((btn) => {
            btn.classList.toggle("active", btn.textContent === speedMultiplier + "x");
        });
    }

    function formatDuration(seconds) {
        seconds = Math.max(0, Math.round(seconds));
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) return `${h}h ${m}m`;
        if (m > 0) return `${m}m ${s}s`;
        return `${s}s`;
    }

    return {
        start,
        reset,
        setSpeed,
        getState,
        onVideoEnd,
    };
})();
