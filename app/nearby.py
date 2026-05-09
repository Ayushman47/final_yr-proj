import math
import os
from typing import Any

import requests

GOOGLE_PLACES_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SEARCH_RADIUS_METERS = 20000  # 20 km

DOCTOR_SEARCH_TERMS = [
    "doctor",
    "hospital",
    "clinic",
    "specialist",
    "near me",
    "nearby",
]


def is_doctor_search_intent(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in DOCTOR_SEARCH_TERMS)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def _google_places_search(lat: float, lon: float, query: str) -> list[dict[str, Any]]:
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return []

    params = {
        "key": api_key,
        "location": f"{lat},{lon}",
        "radius": SEARCH_RADIUS_METERS,
        "keyword": query,
    }

    response = requests.get(GOOGLE_PLACES_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()

    items = []
    for place in payload.get("results", [])[:5]:
        p_lat = place.get("geometry", {}).get("location", {}).get("lat")
        p_lon = place.get("geometry", {}).get("location", {}).get("lng")
        distance_km = (
            haversine_distance_km(lat, lon, p_lat, p_lon)
            if p_lat is not None and p_lon is not None
            else None
        )

        items.append(
            {
                "name": place.get("name", "Unknown"),
                "address": place.get("vicinity") or place.get("formatted_address", "Address unavailable"),
                "rating": place.get("rating"),
                "distance": f"{distance_km:.1f} km" if distance_km is not None else "Unknown",
                "lat": p_lat,
                "lon": p_lon,
                "maps_url": (
                    f"https://www.google.com/maps/search/?api=1&query={p_lat},{p_lon}"
                    if p_lat and p_lon
                    else None
                ),
            }
        )
    return items


def _overpass_search(lat: float, lon: float) -> list[dict[str, Any]]:
    overpass_query = f"""
    [out:json][timeout:30];
    (
      node(around:{SEARCH_RADIUS_METERS},{lat},{lon})["amenity"~"hospital|clinic|doctors"];
      way(around:{SEARCH_RADIUS_METERS},{lat},{lon})["amenity"~"hospital|clinic|doctors"];
      relation(around:{SEARCH_RADIUS_METERS},{lat},{lon})["amenity"~"hospital|clinic|doctors"];
      node(around:{SEARCH_RADIUS_METERS},{lat},{lon})["healthcare"];
      way(around:{SEARCH_RADIUS_METERS},{lat},{lon})["healthcare"];
      relation(around:{SEARCH_RADIUS_METERS},{lat},{lon})["healthcare"];
    );
    out center;
    """

    response = requests.post(OVERPASS_URL, data=overpass_query, timeout=20)
    response.raise_for_status()
    data = response.json()

    items = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        p_lat = element.get("lat", element.get("center", {}).get("lat"))
        p_lon = element.get("lon", element.get("center", {}).get("lon"))
        if p_lat is None or p_lon is None:
            continue

        distance_km = haversine_distance_km(lat, lon, p_lat, p_lon)
        items.append(
            {
                "name": tags.get("name", "Unnamed healthcare facility"),
                "address": tags.get("addr:full")
                or ", ".join(
                    part
                    for part in [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")]
                    if part
                )
                or "Address unavailable",
                "rating": None,
                "distance": f"{distance_km:.1f} km",
                "lat": p_lat,
                "lon": p_lon,
                "maps_url": f"https://www.openstreetmap.org/?mlat={p_lat}&mlon={p_lon}#map=16/{p_lat}/{p_lon}",
            }
        )

    items.sort(key=lambda item: float(item["distance"].split()[0]))
    return items[:5]


def find_nearby_doctors(lat: float, lon: float, query: str = "doctor hospital clinic chemist pharmacy") -> list[dict[str, Any]]:
    try:
        results = _google_places_search(lat, lon, query)
        if results:
            return results
    except Exception as e:
        print(f"Google Places lookup failed: {e}")

    try:
        return _overpass_search(lat, lon)
    except Exception as e:
        print(f"Overpass lookup failed: {e}")
        return []