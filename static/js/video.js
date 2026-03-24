/**
 * video.js — YouTube tourism video player.
 *
 * Plays tourism videos in the side panel when the car arrives at a city.
 * Uses the YouTube IFrame API for state callbacks (ended, error, etc.).
 */
const VideoPlayer = (function () {
    let player = null;
    let playerReady = false;
    let onVideoEndCallback = null;
    let pendingVideoId = null;

    const sectionEl = () => document.getElementById("video-section");
    const titleEl = () => document.getElementById("video-title");
    const cityArrivalEl = () => document.getElementById("city-arrival");
    const cityNameEl = () => document.getElementById("city-name");

    function init(onVideoEnd) {
        onVideoEndCallback = onVideoEnd;

        document.getElementById("skip-video-btn").addEventListener("click", skip);
    }

    function createPlayer(videoId) {
        player = new YT.Player("youtube-player", {
            height: "100%",
            width: "100%",
            videoId: videoId,
            playerVars: {
                autoplay: 1,
                modestbranding: 1,
                rel: 0,
            },
            events: {
                onReady: function () {
                    playerReady = true;
                    if (pendingVideoId) {
                        player.loadVideoById(pendingVideoId);
                        pendingVideoId = null;
                    }
                },
                onStateChange: function (event) {
                    if (event.data === YT.PlayerState.ENDED) {
                        hide();
                        if (onVideoEndCallback) onVideoEndCallback();
                    }
                },
                onError: function () {
                    console.warn("Tourism video playback error");
                    hide();
                    if (onVideoEndCallback) onVideoEndCallback();
                },
            },
        });
    }

    function show(city) {
        // Show city arrival banner
        cityNameEl().textContent = city.full_name;
        cityArrivalEl().classList.remove("hidden");

        if (!city.video) {
            // No video for this city — show banner briefly, then continue
            // Do NOT show the video section (it would display the last played video)
            setTimeout(() => {
                cityArrivalEl().classList.add("hidden");
                if (onVideoEndCallback) onVideoEndCallback();
            }, 3000);
            return;
        }

        // Show video section
        titleEl().textContent = city.video.title || "";
        sectionEl().classList.remove("hidden");

        // Load the video
        if (player && playerReady) {
            player.loadVideoById(city.video.youtube_id);
        } else if (!player) {
            createPlayer(city.video.youtube_id);
        } else {
            pendingVideoId = city.video.youtube_id;
        }
    }

    function hide() {
        sectionEl().classList.add("hidden");
        cityArrivalEl().classList.add("hidden");
        if (player && playerReady) {
            try { player.stopVideo(); } catch (e) {}
        }
    }

    function skip() {
        hide();
        if (onVideoEndCallback) onVideoEndCallback();
    }

    return {
        init,
        show,
        hide,
        skip,
    };
})();
