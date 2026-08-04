from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from accounts.models import Teacher
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
