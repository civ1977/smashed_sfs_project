from datetime import date

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from students.models import SchoolProfile
from .models import Teacher, TeacherTimeRecord
from .views import _dtr_names_match


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


class DtrNamesMatchTests(TestCase):
    """_dtr_names_match tolerates the "Lastname, Givenname" / "Givenname
    Surname" / "Givenname Middle Surname" format differences between a
    teacher's own registered full_name and whatever a biometric DTR export's
    name column used - see accounts.views.daily_time_record."""

    def test_comma_format_matches_natural_order(self):
        self.assertTrue(_dtr_names_match('Juan Dela Cruz', 'Dela Cruz, Juan'))

    def test_middle_initial_and_period_are_tolerated(self):
        self.assertTrue(_dtr_names_match('Juan Dela Cruz', 'Juan A. Dela Cruz'))

    def test_exact_match(self):
        self.assertTrue(_dtr_names_match('Juan Dela Cruz', 'Juan Dela Cruz'))

    def test_case_insensitive(self):
        self.assertTrue(_dtr_names_match('Juan Dela Cruz', 'JUAN DELA CRUZ'))

    def test_shared_compound_surname_with_different_given_name_does_not_match(self):
        # The exact false-positive this rule exists to avoid: two different
        # people sharing a two-word surname would satisfy a plain "2 shared
        # words" rule on the surname alone.
        self.assertFalse(_dtr_names_match('Juan Dela Cruz', 'Maria Dela Cruz'))

    def test_unrelated_name_does_not_match(self):
        self.assertFalse(_dtr_names_match('Juan Dela Cruz', 'Pedro Santos'))

    def test_given_name_alone_is_not_enough(self):
        # Given name matches but nothing else does - below min_common.
        self.assertFalse(_dtr_names_match('Juan Dela Cruz', 'Juan Reyes'))


class DailyTimeRecordFuzzyMatchTests(TestCase):
    """daily_time_record (the /tools/dtr/ page) should surface a DTR record
    a registrar bulk-uploaded (school.views.school_dtr_upload ->
    accounts.views.upload_dtr) under the registrar's own teacher_id and
    whatever name format the biometric export used - not just records this
    exact account created under its own teacher_id and exact full_name."""

    def setUp(self):
        self.school_profile = SchoolProfile.objects.create(
            school_year='2025-2026', region='R', division='D', district='Dist',
            municipality='M', school_name='Test SHS', school_id='000001',
            registrar_name='R', registrar_designation='RD', guidance_counselor='GC',
            principal_name='P', principal_designation='PD', sds_name='SDS',
        )
        self.user = User.objects.create_user(username='juanteacher', password='irrelevant')
        self.teacher = Teacher.objects.create(
            user=self.user, username='juanteacher', password='hash', full_name='Juan Dela Cruz',
            position='Teacher', school_profile_id=self.school_profile.profile_id,
        )
        registrar_user = User.objects.create_user(username='registrar1', password='irrelevant')
        self.registrar = Teacher.objects.create(
            user=registrar_user, username='registrar1', password='hash', full_name='Registrar One',
            position='Registrar', role=Teacher.ROLE_REGISTRAR,
            school_profile_id=self.school_profile.profile_id,
        )
        self.client.force_login(self.user)

    def test_shows_record_uploaded_by_registrar_under_different_name_format(self):
        TeacherTimeRecord.objects.create(
            teacher_id=self.registrar.teacher_id, employee_name='Dela Cruz, Juan',
            date=date(2026, 7, 6), am_arrival='7:45 AM',
        )

        response = self.client.get(reverse('daily_time_record'), {'year': 2026, 'month': 7})

        self.assertContains(response, '7:45')

    def test_does_not_show_a_different_employees_record(self):
        other_user = User.objects.create_user(username='mariateacher', password='irrelevant')
        Teacher.objects.create(
            user=other_user, username='mariateacher', password='hash', full_name='Maria Dela Cruz',
            position='Teacher', school_profile_id=self.school_profile.profile_id,
        )
        TeacherTimeRecord.objects.create(
            teacher_id=self.registrar.teacher_id, employee_name='Dela Cruz, Maria',
            date=date(2026, 7, 6), am_arrival='8:15 AM',
        )

        response = self.client.get(reverse('daily_time_record'), {'year': 2026, 'month': 7})

        self.assertNotContains(response, '8:15')

    def test_self_edited_record_takes_priority_over_uploaded_one_for_same_date(self):
        TeacherTimeRecord.objects.create(
            teacher_id=self.registrar.teacher_id, employee_name='Dela Cruz, Juan',
            date=date(2026, 7, 6), am_arrival='7:45 AM',
        )
        TeacherTimeRecord.objects.create(
            teacher_id=self.teacher.teacher_id, employee_name='Juan Dela Cruz',
            date=date(2026, 7, 6), am_arrival='7:50 AM',
        )

        response = self.client.get(reverse('daily_time_record'), {'year': 2026, 'month': 7})

        self.assertContains(response, '7:50')
        self.assertNotContains(response, '7:45')
