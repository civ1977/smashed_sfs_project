"""django-allauth hooks - see SOCIALACCOUNT_ADAPTER/ACCOUNT_ADAPTER in
settings.py. This app's own Teacher model needs a row to do anything at
all (every view looks one up by username), which allauth has no concept
of, so these two adapters bridge that gap: SocialAccountAdapter creates a
placeholder Teacher row right alongside the User allauth creates, and
AccountAdapter detects that placeholder (empty position) on the next
login and routes to finish_social_signup instead of the dashboard, so a
first-time Google/Facebook sign-in still ends up picking a role/position
the same way a manual registration does."""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from django.urls import reverse
from django.utils import timezone

from .models import Teacher


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        if not Teacher.objects.filter(user=user).exists():
            full_name = f'{user.first_name} {user.last_name}'.strip().upper() or user.username.upper()
            Teacher.objects.create(
                user=user,
                username=user.username[:50],
                password=user.password,
                full_name=full_name[:100],
                # Blank position is the signal AccountAdapter below checks
                # for - finish_social_signup fills this in along with role.
                position='',
                email=user.email,
                role=Teacher.ROLE_ADVISER,
                # Google/Facebook already verified this address themselves
                # (see SOCIALACCOUNT_EMAIL_VERIFICATION='none' in
                # settings.py) - no need to re-verify it ourselves too.
                email_verified_at=timezone.now(),
            )
        return user


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        teacher = Teacher.objects.filter(user=request.user).first()
        if teacher and not teacher.position:
            return reverse('finish_social_signup')
        return super().get_login_redirect_url(request)
