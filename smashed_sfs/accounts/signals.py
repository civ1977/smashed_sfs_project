from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.dispatch import receiver

from .device_detect import classify_device
from .models import ActiveDeviceSession


@receiver(user_logged_in)
def enforce_device_session_limit(sender, request, user, **kwargs):
    """Caps each account at one active session per device category (3 total:
    smartphone/tablet/desktop). login() already calls cycle_key()/create()
    before sending this signal, so session_key is populated by now for a
    brand-new login - the explicit save() below is just a defensive
    fallback, not the normal path."""
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key
    device_category = classify_device(request.META.get('HTTP_USER_AGENT', ''))

    displaced = ActiveDeviceSession.objects.filter(
        user=user, device_category=device_category,
    ).exclude(session_key=session_key).first()
    if displaced:
        # Deletes the Django Session row outright, not just this table's
        # bookkeeping row - the older device's next request finds no
        # matching session and is treated as logged out immediately.
        Session.objects.filter(session_key=displaced.session_key).delete()
        displaced.delete()

    ActiveDeviceSession.objects.update_or_create(
        user=user, device_category=device_category,
        defaults={
            'session_key': session_key,
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:512],
        },
    )


@receiver(user_logged_out)
def release_device_session(sender, request, user, **kwargs):
    """Frees the category slot immediately on explicit logout, rather than
    leaving it occupied until the session naturally expires or gets
    overwritten by the next login of that category. logout() sends this
    signal before it flushes the session, so session_key is still readable
    here."""
    if user is not None and request.session.session_key:
        ActiveDeviceSession.objects.filter(user=user, session_key=request.session.session_key).delete()
