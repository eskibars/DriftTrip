/**
 * radio.js — Dual-mode radio player (YouTube streams + HTML5 Audio for MP3).
 *
 * Manages multiple "radio stations" the user can switch between.
 * Each station is either a YouTube video/stream or a local MP3 file.
 */
const RadioPlayer = (function () {
    let stations = [];
    let currentStation = null;
    let volume = 70; // 0-100

    // YouTube player (hidden, audio only)
    let ytPlayer = null;
    let ytReady = false;
    let ytPendingPlay = false;

    // HTML5 audio element for MP3
    let audioEl = null;

    let statusEl = null;

    function init() {
        statusEl = document.getElementById("radio-status");
        // Create a hidden container for YouTube radio
        const ytContainer = document.createElement("div");
        ytContainer.id = "yt-radio-player";
        ytContainer.style.cssText = "position:absolute; width:1px; height:1px; overflow:hidden; left:-9999px;";
        document.body.appendChild(ytContainer);

        // Create audio element for MP3 playback
        audioEl = document.createElement("audio");
        audioEl.loop = true;
        audioEl.volume = volume / 100;
        document.body.appendChild(audioEl);
    }

    function loadStations(stationList) {
        stations = stationList;
        renderStationUI();
    }

    function renderStationUI() {
        const container = document.getElementById("station-list");
        container.innerHTML = "";
        for (const station of stations) {
            const btn = document.createElement("button");
            btn.className = "station-btn";
            btn.textContent = station.frequency ? `${station.frequency} FM` : station.name;
            btn.title = station.description || station.name;
            btn.dataset.stationId = station.id;
            btn.addEventListener("click", () => switchStation(station.id));
            container.appendChild(btn);
        }
    }

    function switchStation(stationId) {
        const station = stations.find((s) => s.id === stationId);
        if (!station) return;

        // Stop current playback
        stopCurrent();

        currentStation = station;

        // Update UI
        document.querySelectorAll(".station-btn").forEach((btn) => {
            btn.classList.toggle("active", btn.dataset.stationId === stationId);
        });

        // Start new station
        if (station.type === "youtube") {
            playYouTube(station.source);
        } else if (station.type === "mp3") {
            playMP3(station.source);
        }

        updateStatus("playing");
    }

    function playYouTube(videoId) {
        if (ytPlayer && ytReady) {
            ytPlayer.loadVideoById(videoId);
            ytPlayer.setVolume(volume);
        } else {
            // Create YouTube player
            ytPlayer = new YT.Player("yt-radio-player", {
                height: "1",
                width: "1",
                videoId: videoId,
                playerVars: {
                    autoplay: 1,
                    loop: 1,
                    playlist: videoId, // needed for loop to work
                },
                events: {
                    onReady: function (event) {
                        ytReady = true;
                        event.target.setVolume(volume);
                        if (ytPendingPlay) {
                            event.target.playVideo();
                            ytPendingPlay = false;
                        }
                    },
                    onError: function () {
                        console.warn("YouTube radio stream error, trying next station");
                    },
                },
            });
            ytPendingPlay = true;
        }
    }

    function playMP3(filename) {
        audioEl.src = `/static/audio/${filename}`;
        audioEl.volume = volume / 100;
        audioEl.play().catch(() => {
            console.warn("MP3 autoplay blocked");
        });
    }

    function stopCurrent() {
        if (ytPlayer && ytReady) {
            try { ytPlayer.stopVideo(); } catch (e) {}
        }
        audioEl.pause();
        audioEl.src = "";
    }

    function play() {
        if (!currentStation) return;
        if (currentStation.type === "youtube" && ytPlayer && ytReady) {
            ytPlayer.playVideo();
        } else if (currentStation.type === "mp3") {
            audioEl.play().catch(() => {});
        }
        updateStatus("playing");
    }

    function pause() {
        if (currentStation && currentStation.type === "youtube" && ytPlayer && ytReady) {
            ytPlayer.pauseVideo();
        }
        if (currentStation && currentStation.type === "mp3") {
            audioEl.pause();
        }
        updateStatus("paused");
    }

    function setVolume(v) {
        volume = Math.max(0, Math.min(100, v));
        if (ytPlayer && ytReady) {
            ytPlayer.setVolume(volume);
        }
        audioEl.volume = volume / 100;
    }

    function updateStatus(state) {
        if (!statusEl) return;
        if (state === "playing") {
            statusEl.textContent = currentStation ? `Playing: ${currentStation.name}` : "Playing";
            statusEl.className = "playing";
        } else if (state === "paused") {
            statusEl.textContent = "Paused";
            statusEl.className = "";
        } else {
            statusEl.textContent = "Off";
            statusEl.className = "";
        }
    }

    function getCurrentStation() {
        return currentStation;
    }

    return {
        init,
        loadStations,
        switchStation,
        play,
        pause,
        setVolume,
        getCurrentStation,
    };
})();
