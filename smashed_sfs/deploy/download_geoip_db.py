"""(Re-)downloads the MaxMind GeoLite2-City database used by the Online
Users admin page's country + per-province breakdown. Run manually, or via
deploy.sh on every deploy so the data doesn't go too stale (MaxMind
republishes it roughly weekly). Requires MAXMIND_LICENSE_KEY in .env - get
one free at https://www.maxmind.com/en/geolite2/signup, then
Account > License Keys.

Safe to skip: if GEOIP_LICENSE_KEY isn't set, or the download fails (e.g.
no network on this host), this just leaves the breakdown showing
everything as "Unknown / Local" rather than breaking anything else.
"""
import io
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smashed_sfs.settings')

import django

django.setup()

from django.conf import settings

EDITION_ID = 'GeoLite2-City'
DOWNLOAD_URL = (
    'https://download.maxmind.com/app/geoip_download'
    f'?edition_id={EDITION_ID}&license_key={{key}}&suffix=tar.gz'
)


def main():
    license_key = settings.GEOIP_LICENSE_KEY
    if not license_key:
        print('MAXMIND_LICENSE_KEY not set in .env - skipping GeoIP database download.')
        return

    dest_path = Path(settings.GEOIP_DB_PATH)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    url = DOWNLOAD_URL.format(key=license_key)
    print(f'Downloading {EDITION_ID} database...')
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            archive_bytes = resp.read()
    except Exception as exc:
        print(f'GeoIP database download failed ({exc}) - leaving any existing database in place.')
        return

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith(f'{EDITION_ID}.mmdb'))
        extracted = tar.extractfile(member)
        dest_path.write_bytes(extracted.read())

    print(f'{EDITION_ID} database written to {dest_path} ({dest_path.stat().st_size} bytes).')


if __name__ == '__main__':
    main()
