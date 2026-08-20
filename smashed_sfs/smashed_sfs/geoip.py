"""Thin wrapper around the local MaxMind GeoLite2-City database (see
geoip_data/, gitignored - download it with deploy/download_geoip_db.py).
Lookups are purely local/offline: no visitor IP is ever sent anywhere.

City-level accuracy varies a lot by region - many ISPs route traffic
through a handful of hubs, so a visitor can resolve to the ISP's hub city
rather than their actual one. Treat the subdivision (province/region) as a
rough signal, not a precise location."""
import geoip2.database
from geoip2.errors import AddressNotFoundError

from django.conf import settings

UNKNOWN_COUNTRY = 'Unknown / Local'
UNKNOWN_SUBDIVISION = 'Unspecified'

_reader = None
_reader_load_failed = False


def _get_reader():
    global _reader, _reader_load_failed
    if _reader is not None or _reader_load_failed:
        return _reader
    try:
        _reader = geoip2.database.Reader(str(settings.GEOIP_DB_PATH))
    except (FileNotFoundError, OSError):
        _reader_load_failed = True
    return _reader


def location_for_ip(ip_address):
    """Returns (country_name, subdivision_name) for an IP - subdivision is
    the most specific one MaxMind has (typically province/region), or
    UNKNOWN_SUBDIVISION if the country resolved but no subdivision did.
    Returns (UNKNOWN_COUNTRY, UNKNOWN_SUBDIVISION) for anything
    unresolvable (private/loopback IPs, database missing, address not
    found)."""
    reader = _get_reader()
    if reader is None:
        return UNKNOWN_COUNTRY, UNKNOWN_SUBDIVISION
    try:
        response = reader.city(ip_address)
    except (AddressNotFoundError, ValueError):
        return UNKNOWN_COUNTRY, UNKNOWN_SUBDIVISION
    country = response.country.name or UNKNOWN_COUNTRY
    subdivision = response.subdivisions.most_specific.name or UNKNOWN_SUBDIVISION
    return country, subdivision


def geoip_db_available():
    return _get_reader() is not None
