import math

EARTH_RADIUS_KM = 6371.0

# Placeholder heuristic (fixed prep buffer + fixed average speed) until a
# real routing/distance-matrix provider is integrated.
_PREP_BUFFER_MINUTES = 10.0
_AVERAGE_SPEED_KMH = 25.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_eta_minutes(distance_km: float) -> int:
    return round(_PREP_BUFFER_MINUTES + (distance_km / _AVERAGE_SPEED_KMH) * 60)
