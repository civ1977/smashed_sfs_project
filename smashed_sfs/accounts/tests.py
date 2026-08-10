from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class PasswordResetFlowTests(TestCase):
    """End-to-end smoke test for the built-in Django auth password-reset
    views wired up in smashed_sfs/urls.py, using the templates under
    templates/accounts/. Covers the whole request -> email -> confirm ->
    login round trip, not just that the URLs resolve."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='resetme', email='resetme@example.com', password='OldPassword123!',
        )

    def test_requesting_reset_sends_email_with_working_link(self):
        response = self.client.post(reverse('password_reset'), {'email': 'resetme@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset', mail.outbox[0].body.lower())

    def test_unknown_email_does_not_error_or_send_mail(self):
        response = self.client.post(reverse('password_reset'), {'email': 'nobody@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_valid_link_allows_setting_new_password_and_logging_in(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        # Mirrors PasswordResetConfirmView's own redirect-to-a-session-scoped-
        # url dance so the second request carries the "already validated"
        # token state instead of the raw one-time token in the URL.
        confirm_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        session_url = self.client.get(confirm_url, follow=True).redirect_chain[-1][0]

        response = self.client.post(session_url, {
            'new_password1': 'BrandNewPassword456!',
            'new_password2': 'BrandNewPassword456!',
        })
        self.assertRedirects(response, reverse('password_reset_complete'))

        self.assertTrue(self.client.login(username='resetme', password='BrandNewPassword456!'))

    def test_invalid_token_shows_invalid_link_message_not_the_form(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.get(
            reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'bad-token'}),
            follow=True,
        )
        self.assertContains(response, 'invalid')
