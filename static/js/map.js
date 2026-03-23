/**
 * map.js — Google Maps display, route drawing, and car animation.
 *
 * Decodes the overview polyline into a lat/lng path, draws it on the map,
 * and animates a car marker along it using requestAnimationFrame.
 */
const MapController = (function () {
    let map = null;
    let routeLine = null;
    let carMarker = null;
    let originMarker = null;
    let destMarker = null;
    let cityMarkers = [];

    // Animation state
    let pathPoints = [];       // [{lat, lng}, ...]
    let cumDistances = [];     // cumulative distance at each point
    let totalPathDistance = 0;
    let currentDistance = 0;
    let speedMultiplier = 10;
    let totalDurationSec = 0;  // real-world duration of the trip
    let animating = false;
    let paused = false;
    let lastFrameTime = null;
    let onProgressCallback = null;

    function init() {
        map = new google.maps.Map(document.getElementById("map"), {
            center: { lat: 39.5, lng: -82.5 },
            zoom: 7,
            mapId: "VIRTUAL_ROADTRIP",
            disableDefaultUI: false,
            zoomControl: true,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: true,
            styles: [
                { elementType: "geometry", stylers: [{ color: "#1d2c4d" }] },
                { elementType: "labels.text.fill", stylers: [{ color: "#8ec3b9" }] },
                { elementType: "labels.text.stroke", stylers: [{ color: "#1a3646" }] },
                { featureType: "road", elementType: "geometry", stylers: [{ color: "#304a7d" }] },
                { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: "#255763" }] },
                { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#2c6675" }] },
                { featureType: "water", elementType: "geometry", stylers: [{ color: "#0e1626" }] },
            ],
        });
    }

    function decodePolyline(encoded) {
        // Google's polyline encoding algorithm
        const points = [];
        let index = 0, lat = 0, lng = 0;
        while (index < encoded.length) {
            let shift = 0, result = 0, byte;
            do {
                byte = encoded.charCodeAt(index++) - 63;
                result |= (byte & 0x1f) << shift;
                shift += 5;
            } while (byte >= 0x20);
            lat += (result & 1) ? ~(result >> 1) : (result >> 1);

            shift = 0; result = 0;
            do {
                byte = encoded.charCodeAt(index++) - 63;
                result |= (byte & 0x1f) << shift;
                shift += 5;
            } while (byte >= 0x20);
            lng += (result & 1) ? ~(result >> 1) : (result >> 1);

            points.push({ lat: lat / 1e5, lng: lng / 1e5 });
        }
        return points;
    }

    function haversine(p1, p2) {
        const R = 6371000;
        const toRad = (d) => (d * Math.PI) / 180;
        const dLat = toRad(p2.lat - p1.lat);
        const dLng = toRad(p2.lng - p1.lng);
        const a =
            Math.sin(dLat / 2) ** 2 +
            Math.cos(toRad(p1.lat)) * Math.cos(toRad(p2.lat)) * Math.sin(dLng / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function computeCumulativeDistances(points) {
        const dists = [0];
        for (let i = 1; i < points.length; i++) {
            dists.push(dists[i - 1] + haversine(points[i - 1], points[i]));
        }
        return dists;
    }

    function getPositionAtDistance(dist) {
        if (dist <= 0) return pathPoints[0];
        if (dist >= totalPathDistance) return pathPoints[pathPoints.length - 1];

        for (let i = 1; i < cumDistances.length; i++) {
            if (cumDistances[i] >= dist) {
                const segStart = cumDistances[i - 1];
                const segLen = cumDistances[i] - segStart;
                const frac = segLen === 0 ? 0 : (dist - segStart) / segLen;
                return {
                    lat: pathPoints[i - 1].lat + frac * (pathPoints[i].lat - pathPoints[i - 1].lat),
                    lng: pathPoints[i - 1].lng + frac * (pathPoints[i].lng - pathPoints[i - 1].lng),
                };
            }
        }
        return pathPoints[pathPoints.length - 1];
    }

    function drawRoute(routeData) {
        // Clear previous
        clearRoute();

        // Decode polyline
        pathPoints = decodePolyline(routeData.overview_polyline);
        cumDistances = computeCumulativeDistances(pathPoints);
        totalPathDistance = cumDistances[cumDistances.length - 1];
        totalDurationSec = routeData.total_duration_seconds;

        // Draw the route line
        routeLine = new google.maps.Polyline({
            path: pathPoints,
            geodesic: true,
            strokeColor: "#e94560",
            strokeOpacity: 0.8,
            strokeWeight: 4,
            map: map,
        });

        // Origin marker
        const originEl = document.createElement("div");
        originEl.innerHTML = "&#128205;";
        originEl.style.fontSize = "28px";
        originMarker = new google.maps.marker.AdvancedMarkerElement({
            position: routeData.start_location,
            map: map,
            content: originEl,
            title: routeData.start_address,
        });

        // Destination marker
        const destEl = document.createElement("div");
        destEl.innerHTML = "&#127937;";
        destEl.style.fontSize = "28px";
        destMarker = new google.maps.marker.AdvancedMarkerElement({
            position: routeData.end_location,
            map: map,
            content: destEl,
            title: routeData.end_address,
        });

        // City markers
        for (const city of routeData.cities) {
            const cityEl = document.createElement("div");
            cityEl.innerHTML = "&#9679;";
            cityEl.style.cssText = "font-size:12px; color:#ffa502; text-shadow: 0 0 4px rgba(255,165,2,0.6);";
            const marker = new google.maps.marker.AdvancedMarkerElement({
                position: { lat: city.lat, lng: city.lng },
                map: map,
                content: cityEl,
                title: city.full_name,
            });
            cityMarkers.push(marker);
        }

        // Car marker
        const carEl = document.createElement("div");
        carEl.innerHTML = "&#128663;";
        carEl.style.fontSize = "32px";
        carMarker = new google.maps.marker.AdvancedMarkerElement({
            position: pathPoints[0],
            map: map,
            content: carEl,
            title: "Your car",
            zIndex: 999,
        });

        // Fit bounds
        const bounds = new google.maps.LatLngBounds(
            routeData.bounds.southwest,
            routeData.bounds.northeast
        );
        map.fitBounds(bounds, { top: 20, right: 20, bottom: 20, left: 20 });
    }

    function clearRoute() {
        if (routeLine) { routeLine.setMap(null); routeLine = null; }
        if (carMarker) { carMarker.map = null; carMarker = null; }
        if (originMarker) { originMarker.map = null; originMarker = null; }
        if (destMarker) { destMarker.map = null; destMarker = null; }
        for (const m of cityMarkers) { m.map = null; }
        cityMarkers = [];
        pathPoints = [];
        cumDistances = [];
        totalPathDistance = 0;
        currentDistance = 0;
    }

    function startAnimation(onProgress) {
        onProgressCallback = onProgress;
        currentDistance = 0;
        animating = true;
        paused = false;
        lastFrameTime = performance.now();
        requestAnimationFrame(animationLoop);
    }

    function animationLoop(timestamp) {
        if (!animating) return;

        if (paused) {
            lastFrameTime = timestamp;
            requestAnimationFrame(animationLoop);
            return;
        }

        const elapsed = timestamp - lastFrameTime;
        lastFrameTime = timestamp;

        // How fast the car moves: total distance / total real-world duration
        // Then multiplied by speed factor
        const metersPerRealMs = totalPathDistance / (totalDurationSec * 1000);
        const distIncrement = metersPerRealMs * elapsed * speedMultiplier;
        currentDistance += distIncrement;

        if (currentDistance >= totalPathDistance) {
            currentDistance = totalPathDistance;
            animating = false;
        }

        const pos = getPositionAtDistance(currentDistance);
        carMarker.position = new google.maps.LatLng(pos.lat, pos.lng);

        const fraction = currentDistance / totalPathDistance;
        if (onProgressCallback) {
            onProgressCallback(fraction);
        }

        if (animating) {
            requestAnimationFrame(animationLoop);
        }
    }

    function pause() {
        paused = true;
    }

    function resume() {
        paused = false;
    }

    function stop() {
        animating = false;
        paused = false;
    }

    function setSpeed(s) {
        speedMultiplier = s;
    }

    function getMap() {
        return map;
    }

    function isAnimating() {
        return animating;
    }

    return {
        init,
        drawRoute,
        clearRoute,
        startAnimation,
        pause,
        resume,
        stop,
        setSpeed,
        getMap,
        isAnimating,
    };
})();
