# fichajes/utils.py
import requests

def reverse_geocode(lat, lng) -> str:
    """
    Convierte lat/lng en una descripción corta usando Nominatim (OpenStreetMap).
    Pensado para pocas peticiones (uso interno, no masivo).
    """
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lng,
        "format": "jsonv2",
        "zoom": 16,
        "addressdetails": 0,
    }
    headers = {
        "User-Agent": "PortalIntasa/1.0 (admin@tu-dominio.com)"
    }
    resp = requests.get(url, params=params, headers=headers, timeout=3)
    resp.raise_for_status()
    data = resp.json()
    return data.get("display_name", "")
