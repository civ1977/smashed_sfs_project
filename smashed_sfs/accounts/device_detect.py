"""Best-effort User-Agent classification for ActiveDeviceSession's 3-device
cap (accounts/signals.py). Heuristic, not authoritative - a determined user
can spoof their User-Agent to dodge the cap, and iPadOS 13+ Safari reports
itself as a Mac (no reliable UA marker distinguishes it from a real desktop),
so this is a soft "discourage casual account-sharing" limit, not a hard
security boundary.
"""

from .models import ActiveDeviceSession

_TABLET_MARKERS = (
    'ipad', 'tablet', 'kindle', 'playbook', 'nexus 7', 'nexus 9', 'nexus 10', 'sm-t',
)


def classify_device(user_agent):
    ua = (user_agent or '').lower()

    if any(marker in ua for marker in _TABLET_MARKERS):
        return ActiveDeviceSession.DEVICE_TABLET

    if 'android' in ua:
        # Android's own UA convention: phone UAs include the "Mobile" token,
        # tablet UAs omit it.
        return ActiveDeviceSession.DEVICE_SMARTPHONE if 'mobile' in ua else ActiveDeviceSession.DEVICE_TABLET

    if any(marker in ua for marker in ('iphone', 'ipod', 'windows phone', 'blackberry', 'mobile')):
        return ActiveDeviceSession.DEVICE_SMARTPHONE

    return ActiveDeviceSession.DEVICE_DESKTOP
