"""Calculs de position (pointage par téléphone limité au lieu de travail)."""
import math

RAYON_TERRE_M = 6_371_000
# Au-delà de cette imprécision du GPS, la position n'est pas fiable : on demande de réessayer
PRECISION_MAX_M = 50


def distance_m(lat1, lon1, lat2, lon2):
    """Distance en mètres entre deux points (formule de haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAYON_TERRE_M * math.asin(math.sqrt(a))


def lire_position(lat, lon, precision):
    """Retourne (lat, lon, précision) en nombres, ou None si les valeurs sont absentes ou invalides."""
    try:
        lat, lon, precision = float(lat), float(lon), float(precision or 0)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not math.isfinite(precision) or precision < 0:
        return None
    return lat, lon, precision


def lieu_le_plus_proche(lat, lon, lieux):
    """Retourne (lieu, distance) du lieu actif le plus proche."""
    meilleur, d_min = None, float("inf")
    for lieu in lieux:
        d = distance_m(lat, lon, lieu.latitude, lieu.longitude)
        if d < d_min:
            meilleur, d_min = lieu, d
    return meilleur, d_min
