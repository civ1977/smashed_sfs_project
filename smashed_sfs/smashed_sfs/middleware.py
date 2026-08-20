from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from accounts.models import SiteVisit, Teacher
from portal.models import StudentAccount

# How stale last_seen has to be before we bother writing a fresh timestamp -
# avoids an UPDATE on literally every request from every logged-in user.
HEARTBEAT_INTERVAL = timedelta(seconds=30)


class TrackLastSeenMiddleware:
    """Stamps Teacher.last_seen / StudentAccount.last_seen for the logged-in
    user on each request, throttled to once per HEARTBEAT_INTERVAL. This is
    the heartbeat the online-users monitoring page (admin_monitoring.py)
    reads to decide who's currently online."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            now = timezone.now()
            stale = Q(last_seen__isnull=True) | Q(last_seen__lt=now - HEARTBEAT_INTERVAL)
            updated = Teacher.objects.filter(stale, username=user.username).update(last_seen=now)
            if not updated:
                StudentAccount.objects.filter(stale, user_id=user.id).update(last_seen=now)

        return response


def _client_ip(request):
    # nginx.conf sets X-Forwarded-For to the real client IP - the leftmost
    # entry if it's a comma-separated chain. Falls back to REMOTE_ADDR for
    # local runserver, where there's no reverse proxy in front at all.
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


# Substrings (case-insensitive) seen in the User-Agent of mass internet
# scanners/vulnerability probes that constantly hit any public IP - not
# real visitors of this app. Found by inspecting nginx's access log after
# noticing the Online Users country breakdown counted them: e.g. zgrab
# probing /developmentserver/metadatauploader (a SAP NetWeaver exploit
# path) and /nacos/ (an Alibaba Nacos config-server exploit path). A
# missing User-Agent entirely is just as telling - real browsers always
# send one.
BOT_USER_AGENT_MARKERS = (
    'zgrab', 'masscan', 'nmap', 'nikto', 'sqlmap', 'curl/', 'wget/',
    'python-requests', 'go-http-client', 'censys', 'shodan', 'libwww-perl',
    'httpclient', 'scrapy', 'bot', 'spider', 'crawl',
)


def _looks_like_bot(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    if not user_agent:
        return True
    user_agent = user_agent.lower()
    return any(marker in user_agent for marker in BOT_USER_AGENT_MARKERS)


class TrackSiteVisitMiddleware:
    """Records one SiteVisit(ip_address, visited_date) row per unique
    visitor per day, via get_or_create - repeat requests from the same IP
    on the same day never create a duplicate row or add extra write load
    beyond the first hit. Placed after WhiteNoiseMiddleware in MIDDLEWARE,
    so static asset requests (served directly by whitenoise, which returns
    before the rest of the chain runs) never reach this and inflate the
    count.

    Only records requests that both succeeded (status < 400) and don't
    look like a known scanner/bot - a bare public IP with no domain/WAF in
    front gets scanned constantly by tools probing for exploit paths
    (these 404) or just fetching / to check the server's alive (this
    200s, but with a giveaway User-Agent) - neither is a real visitor of
    the app, and both would otherwise inflate the Online Users visit
    counts and country breakdown."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code < 400 and not _looks_like_bot(request):
            ip = _client_ip(request)
            if ip:
                SiteVisit.objects.get_or_create(ip_address=ip, visited_date=timezone.now().date())

        return response
