import calendar
import csv
import io
import math
import re
from datetime import date, datetime

import openpyxl
from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.db import transaction
from django.http import JsonResponse

from students.models import Section, Student
from portal.models import StudentAccount
from grades.models import Grade, SubjectMapping, SchoolCalendarException
from smashed_sfs import upload_utils
from .models import Teacher, TeacherTimeRecord, DTRCalendarException, SchoolMasterlistEntry
from .forms import NewSchoolProfileForm, SectionForm

# Score bands for the dashboard's Term Ratings chart - DepEd-style grade
# brackets, widest-to-narrowest. A student lands in a term's band by their
# average across whatever subjects they have a grade recorded for that
# term (not gated on having every subject filled in, unlike the rankings
# page's completeness rule - this chart is just a rough distribution).
TERM_RATING_BANDS = ['98-100', '95-97', '90-94', '85-89', '80-84', '75-79', 'Below 75']


def _term_rating_band(average):
    if average >= 98:
        return '98-100'
    if average >= 95:
        return '95-97'
    if average >= 90:
        return '90-94'
    if average >= 85:
        return '85-89'
    if average >= 80:
        return '80-84'
    if average >= 75:
        return '75-79'
    return 'Below 75'


def _nice_axis_ticks(max_value, target_ticks=4):
    """Round, evenly-spaced axis ticks from 0 up to a bound at/above
    max_value, e.g. max_value=23 -> [0, 10, 20, 30]. These axes are always
    whole-number student/rating counts, so the step is never below 1."""
    max_value = max(int(max_value), 1)
    raw_step = max_value / target_ticks
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step >= 1 else 1
    step = magnitude
    for multiple in (1, 2, 5, 10):
        step = multiple * magnitude
        if step >= raw_step:
            break
    step = max(int(step), 1)
    top = step * math.ceil(max_value / step)
    return list(range(0, top + 1, step))


TEACHING_ROLE_CHOICES = (Teacher.ROLE_ADVISER, Teacher.ROLE_SUBJECT_TEACHER)

# Same rate-limit shape as LOGIN_ATTEMPT_LIMIT below - keyed per email
# rather than username, so a resend-verification form can't be used to
# spam an arbitrary inbox with confirmation emails.
RESEND_VERIFICATION_LIMIT = 3
RESEND_VERIFICATION_LOCKOUT_SECONDS = 300


def _send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = request.build_absolute_uri(reverse('verify_email', kwargs={'uidb64': uid, 'token': token}))
    message = render_to_string('accounts/verification_email.txt', {'user': user, 'link': link})
    send_mail(
        'Confirm your SMASHED-SFs account',
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True,
    )


def register(request):
    account_type = request.POST.get('account_type') or request.GET.get('type')
    if account_type != 'non_teaching':
        account_type = 'teaching'

    if request.method == 'POST':
        username = request.POST.get('username')
        # Upper case, matching how DepEd forms render names/positions
        # everywhere else in the app.
        full_name = (request.POST.get('full_name') or '').strip().upper()
        position = (request.POST.get('position') or '').strip().upper()
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')

        is_officer = False
        if account_type == 'non_teaching':
            role = Teacher.ROLE_NON_TEACHING
            is_officer = request.POST.get('non_teaching_role') == 'officer'
        else:
            role = request.POST.get('role')
            if role not in TEACHING_ROLE_CHOICES:
                role = Teacher.ROLE_ADVISER

        if password != password_confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/register.html', {'account_type': account_type})

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'accounts/register.html', {'account_type': account_type})

        if request.POST.get('agree_terms') != 'on':
            messages.error(request, "Please check the box confirming you agree to the User's Agreement and Privacy Policy.")
            return render(request, 'accounts/register.html', {'account_type': account_type})

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'accounts/register.html', {'account_type': account_type})

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'accounts/register.html', {'account_type': account_type})

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            user.first_name = full_name.split()[0] if full_name else ''
            user.last_name = full_name.split()[-1] if len(full_name.split()) > 1 else ''
            # Inactive until the confirmation email is clicked (verify_email
            # below flips this back on) - Django's own authenticate() already
            # refuses to log in an inactive user, so this alone is enough to
            # block access without any extra checks at the login view.
            user.is_active = False
            user.save()

            Teacher.objects.create(
                user=user,
                username=username,
                password=user.password,
                full_name=full_name,
                position=position,
                email=email,
                role=role,
                is_officer=is_officer,
                terms_accepted_at=timezone.now(),
            )

        _send_verification_email(request, user)
        return redirect('registration_pending')

    selected_role = request.GET.get('role')
    if selected_role not in TEACHING_ROLE_CHOICES:
        selected_role = None

    return render(request, 'accounts/register.html', {
        'account_type': account_type,
        'selected_role': selected_role,
    })


def registration_pending(request):
    return render(request, 'accounts/registration_pending.html')


def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token):
        return render(request, 'accounts/verify_email_invalid.html')

    user.is_active = True
    user.save()
    Teacher.objects.filter(user=user).update(email_verified_at=timezone.now())

    login(request, user)
    messages.success(request, f'Email confirmed! Welcome {user.username}!')
    return redirect('complete_profile')


def resend_verification(request):
    """Re-sends the confirmation email for an account stuck at is_active=False
    - the original link may have expired (default_token_generator tokens are
    time-limited via PASSWORD_RESET_TIMEOUT) or the email may never have
    arrived. Deliberately shows the same generic message whether or not a
    matching unverified account exists, so this can't be used to probe which
    emails are registered."""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        cache_key = f'resend_verification:{email.lower()}'
        attempts = cache.get(cache_key, 0)
        if email and attempts < RESEND_VERIFICATION_LIMIT:
            cache.set(cache_key, attempts + 1, RESEND_VERIFICATION_LOCKOUT_SECONDS)
            user = User.objects.filter(email=email, is_active=False).first()
            if user:
                _send_verification_email(request, user)

        messages.success(
            request,
            "If that email belongs to an account awaiting confirmation, we've sent a new link.",
        )
        return redirect('resend_verification')

    return render(request, 'accounts/resend_verification.html')


@login_required
def finish_social_signup(request):
    """A first-time Google/Facebook sign-in only supplies a name and email
    (see accounts/adapters.py SocialAccountAdapter) - nothing about role or
    position, which every other part of this app assumes a Teacher row
    already has. AccountAdapter.get_login_redirect_url routes here whenever
    that's still blank; once filled in, this is a dead end for that account
    (redirects straight to complete_profile like nothing happened)."""
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    if teacher.position:
        return redirect('complete_profile')

    account_type = request.POST.get('account_type') or request.GET.get('type')
    if account_type != 'non_teaching':
        account_type = 'teaching'

    if request.method == 'POST':
        position = (request.POST.get('position') or '').strip().upper()
        is_officer = False
        if account_type == 'non_teaching':
            role = Teacher.ROLE_NON_TEACHING
            is_officer = request.POST.get('non_teaching_role') == 'officer'
        else:
            role = request.POST.get('role')
            if role not in TEACHING_ROLE_CHOICES:
                role = Teacher.ROLE_ADVISER

        if not position:
            messages.error(request, 'Position is required.')
            return render(request, 'accounts/finish_social_signup.html', {'account_type': account_type, 'teacher': teacher})

        if request.POST.get('agree_terms') != 'on':
            messages.error(request, "Please check the box confirming you agree to the User's Agreement and Privacy Policy.")
            return render(request, 'accounts/finish_social_signup.html', {'account_type': account_type, 'teacher': teacher})

        teacher.position = position
        teacher.role = role
        teacher.is_officer = is_officer
        teacher.terms_accepted_at = timezone.now()
        teacher.save()

        messages.success(request, f'Welcome {teacher.full_name}!')
        return redirect('complete_profile')

    return render(request, 'accounts/finish_social_signup.html', {
        'account_type': account_type,
        'teacher': teacher,
    })


def landing_page(request):
    return render(request, 'accounts/landing.html')


def about(request):
    return render(request, 'accounts/public_about.html')


def how_it_works(request):
    return render(request, 'accounts/public_how_it_works.html')


def tutorials(request):
    return render(request, 'accounts/public_tutorials.html')


def pricing(request):
    return render(request, 'accounts/public_pricing.html')


def privacy_policy(request):
    return render(request, 'accounts/public_privacy_policy.html')


def user_agreement(request):
    return render(request, 'accounts/public_user_agreement.html')


@xframe_options_sameorigin
def user_agreement_embed(request):
    """Chrome-less version of the User's Agreement (no nav/footer) for the
    registration pages' popup <iframe> - see templates/partials/terms_modal.html.
    Django's default X-Frame-Options: DENY (XFrameOptionsMiddleware) blocks
    this from rendering inside an <iframe> at all, even same-origin, unless
    explicitly relaxed here - SAMEORIGIN rather than fully exempt, so only
    this site can frame it."""
    return render(request, 'accounts/public_user_agreement_embed.html')


def contact_us(request):
    return render(request, 'accounts/public_contact_us.html')


LOGIN_ATTEMPT_LIMIT = 5
LOGIN_LOCKOUT_SECONDS = 300


def login_view(request):
    """Cache-based throttle on repeated failed logins, keyed per username -
    not a full django-axes-style setup (no per-IP tracking, and with
    Django's default LocMemCache this is per-worker-process rather than
    shared across gunicorn's workers), but enough to stop a naive scripted
    brute-force against a single account, which is the gap this closes."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password')

        cache_key = f'login_attempts:{username.lower()}'
        attempts = cache.get(cache_key, 0)
        if attempts >= LOGIN_ATTEMPT_LIMIT:
            messages.error(request, 'Too many failed login attempts. Please try again in a few minutes.')
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            cache.delete(cache_key)
            login(request, user)
            messages.success(request, f'Welcome back, {username}!')
            return redirect('dashboard')
        else:
            # authenticate() returns None for a correct password on an
            # inactive account too (Django's ModelBackend refuses those
            # outright) - re-check the password directly so an unverified
            # registrant gets pointed at resend_verification instead of a
            # generic "wrong password" that gives them nothing to act on.
            candidate = User.objects.filter(username__iexact=username, is_active=False).first()
            if candidate and candidate.check_password(password):
                messages.error(
                    request,
                    'Please confirm your email before logging in - check your inbox, '
                    'or resend the confirmation email below.',
                )
            else:
                cache.set(cache_key, attempts + 1, LOGIN_LOCKOUT_SECONDS)
                messages.error(request, 'Invalid username or password.')

    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def account_settings(request):
    teacher = Teacher.objects.filter(username=request.user.username).first()
    password_form = PasswordChangeForm(user=request.user)

    if request.method == 'POST' and request.POST.get('form_type') == 'profile':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip()

        if not email:
            messages.error(request, 'Email is required.')
        elif User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
            messages.error(request, 'That email is already in use by another account.')
        else:
            request.user.email = email
            request.user.save()
            if teacher:
                if full_name:
                    teacher.full_name = full_name
                teacher.email = email
                teacher.save()
            messages.success(request, 'Profile updated.')
            return redirect('account_settings')

    elif request.method == 'POST' and request.POST.get('form_type') == 'password':
        password_form = PasswordChangeForm(user=request.user, data=request.POST)
        if password_form.is_valid():
            user = password_form.save()
            # Keeps last_seen/re-login intact - otherwise Django would log
            # the user out immediately, since changing the password
            # invalidates the session hash it's checked against.
            update_session_auth_hash(request, user)
            if teacher:
                # Mirrors accounts.register()'s Teacher.password = user.password
                # convention - see CLAUDE.md's architecture notes. Not used
                # for auth (that's always via the linked User), but kept in
                # sync so it doesn't look stale to anyone inspecting the DB.
                teacher.password = user.password
                teacher.save()
            messages.success(request, 'Password changed.')
            return redirect('account_settings')
        else:
            messages.error(request, 'Please correct the errors below.')

    return render(request, 'accounts/account_settings.html', {
        'teacher': teacher,
        'password_form': password_form,
    })


@login_required
def dashboard(request):
    student_account = StudentAccount.objects.filter(user=request.user).first()
    if student_account:
        if student_account.status == StudentAccount.STATUS_APPROVED:
            return redirect('portal_grades')
        return redirect('portal_pending')

    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile. Please contact the administrator.')
        return render(request, 'accounts/dashboard.html', {'teacher': None, 'profile_incomplete': False})

    if teacher.role == Teacher.ROLE_NON_TEACHING:
        if not teacher.school_profile_id:
            return redirect('complete_profile')
        if teacher.is_officer:
            return redirect('school_dashboard')
        return redirect('tools')

    if teacher.role == Teacher.ROLE_SUBJECT_TEACHER:
        if not teacher.school_profile_id:
            return redirect('complete_profile')
        return redirect('my_subject_teaching')

    if teacher.role != Teacher.ROLE_ADVISER:
        return redirect('school_dashboard')

    profile_incomplete = not teacher.school_profile_id or not Section.objects.filter(adviser_id=teacher.teacher_id).exists()

    # teacher.full_name is a single string (often stored all-caps, e.g.
    # "VICTORINO PINAWIN") with no separate first-name field - pull just
    # the first word here rather than in the template, since Django
    # templates aren't suited to this kind of string parsing.
    full_name = (teacher.full_name or '').strip()
    first_name = full_name.split()[0].title() if full_name else request.user.username

    section_students = list(Student.objects.filter(adviser_id=teacher.teacher_id))
    male_count = sum(1 for s in section_students if s.sex in ('MALE', 'M'))
    female_count = sum(1 for s in section_students if s.sex in ('FEMALE', 'F'))

    # Same grade-level scoping as the class gradesheet/rankings pages, so a
    # subject only counts toward a student's term average if it's mapped
    # for this teacher's own grade level.
    teacher_section = Section.objects.filter(adviser_id=teacher.teacher_id).first()
    subjects = SubjectMapping.objects.filter(school_profile_id=teacher.school_profile_id)
    if teacher_section:
        subjects = subjects.filter(grade_level=teacher_section.grade_level)
    required_subject_ids = set(subjects.values_list('mapping_id', flat=True))

    grades_by_student_term = {}
    term_grades = Grade.objects.filter(
        lrn__in=[s.lrn for s in section_students], mapping_id__in=required_subject_ids
    ).values('lrn', 'term', 'grade')
    for row in term_grades:
        grades_by_student_term.setdefault((row['lrn'], row['term']), []).append(row['grade'])

    term_band_counts = {band: {1: 0, 2: 0, 3: 0} for band in TERM_RATING_BANDS}
    for student in section_students:
        for term in (1, 2, 3):
            values = grades_by_student_term.get((student.lrn, term))
            if not values:
                continue
            average = sum(values) / len(values)
            term_band_counts[_term_rating_band(average)][term] += 1

    term_rating_rows = [
        {
            'band': band,
            'terms': [
                {'term': term, 'count': term_band_counts[band][term]}
                for term in (1, 2, 3)
            ],
        }
        for band in TERM_RATING_BANDS
    ]
    term_rating_max = max(
        [cell['count'] for row in term_rating_rows for cell in row['terms']] or [0]
    )
    term_rating_max = max(term_rating_max, 1)

    # Axis ticks also double as the "100%"/max reference for the bars
    # themselves, so a bar's length is plotted against the same scale as
    # its chart's gridlines instead of always stretching to fill the track.
    enrolment_axis_ticks = _nice_axis_ticks(max(male_count, female_count, 1))
    enrolment_max = enrolment_axis_ticks[-1]

    term_rating_axis_ticks = _nice_axis_ticks(term_rating_max)
    term_rating_max = term_rating_axis_ticks[-1]

    return render(request, 'accounts/dashboard.html', {
        'teacher': teacher,
        'profile_incomplete': profile_incomplete,
        'first_name': first_name,
        'male_count': male_count,
        'female_count': female_count,
        'enrolment_max': enrolment_max,
        'enrolment_axis_ticks': enrolment_axis_ticks,
        'term_rating_rows': term_rating_rows,
        'term_rating_max': term_rating_max,
        'term_rating_axis_ticks': term_rating_axis_ticks,
    })


# ---------------------------------------------------------------------------
# Masterlist lookups - AJAX endpoints backing the cascading Region/Division/
# Municipality/District/School picker on Complete Your Profile's "New school
# details" section (NewSchoolProfileForm, below, and its use in
# complete_profile). Each level is queried live rather than shipping the
# whole ~60k-row masterlist to the browser up front.
# ---------------------------------------------------------------------------

@login_required
def masterlist_divisions(request):
    region = request.GET.get('region', '')
    divisions = SchoolMasterlistEntry.objects.filter(region=region) \
        .order_by('division').values_list('division', flat=True).distinct()
    return JsonResponse({'divisions': list(divisions)})


@login_required
def masterlist_municipalities(request):
    region = request.GET.get('region', '')
    division = request.GET.get('division', '')
    municipalities = SchoolMasterlistEntry.objects.filter(region=region, division=division) \
        .order_by('municipality').values_list('municipality', flat=True).distinct()
    return JsonResponse({'municipalities': list(municipalities)})


@login_required
def masterlist_districts(request):
    region = request.GET.get('region', '')
    division = request.GET.get('division', '')
    municipality = request.GET.get('municipality', '')
    districts = SchoolMasterlistEntry.objects.filter(region=region, division=division, municipality=municipality) \
        .order_by('district').values_list('district', flat=True).distinct()
    return JsonResponse({'districts': list(districts)})


@login_required
def masterlist_schools(request):
    region = request.GET.get('region', '')
    division = request.GET.get('division', '')
    municipality = request.GET.get('municipality', '')
    district = request.GET.get('district', '')
    schools = SchoolMasterlistEntry.objects.filter(
        region=region, division=division, municipality=municipality, district=district,
    ).order_by('school_name').values('school_id', 'school_name')
    return JsonResponse({'schools': list(schools)})


@login_required
def complete_profile(request):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile. Please contact the administrator.')
        return redirect('dashboard')

    needs_school = not teacher.school_profile_id
    needs_section = (
        teacher.role not in (Teacher.ROLE_NON_TEACHING, Teacher.ROLE_SUBJECT_TEACHER)
        and not Section.objects.filter(adviser_id=teacher.teacher_id).exists()
    )

    if not needs_school and not needs_section:
        messages.info(request, 'Your profile is already complete.')
        return redirect('dashboard')

    data = request.POST if request.method == 'POST' else None

    # Always goes through the Region/Division/.../School masterlist picker -
    # there's no "attach to a school someone else already created" option
    # here, so two teachers at the same physical school each get their own
    # SchoolProfile row rather than sharing one. That's a deliberate
    # tradeoff, not an oversight.
    school_create_form = NewSchoolProfileForm(data, prefix='newschool') if needs_school else None
    section_form = SectionForm(data, prefix='section') if needs_section else None

    if request.method == 'POST':
        school_valid = school_create_form.is_valid() if needs_school else True
        section_valid = section_form.is_valid() if needs_section else True

        if school_valid and section_valid:
            with transaction.atomic():
                if needs_school:
                    school_profile = school_create_form.save(commit=False)
                    school_profile.created_by = teacher.teacher_id
                    school_profile.save()
                    teacher.school_profile_id = school_profile.profile_id
                    teacher.save()

                if needs_section:
                    section = section_form.save(commit=False)
                    section.adviser_id = teacher.teacher_id
                    section.school_profile_id = teacher.school_profile_id
                    section.save()

            messages.success(request, '✅ Profile setup complete! You can now upload students and grades.')
            return redirect('dashboard')

        messages.error(request, 'Please fix the errors below.')

    return render(request, 'accounts/complete_profile.html', {
        'needs_school': needs_school,
        'needs_section': needs_section,
        'school_create_form': school_create_form,
        'section_form': section_form,
    })


@login_required
def ancillary(request):
    return render(request, 'accounts/ancillary.html')


@login_required
def tools(request):
    teacher = Teacher.objects.filter(username=request.user.username).first()
    is_adviser = bool(teacher and teacher.role == Teacher.ROLE_ADVISER)
    is_subject_teacher = bool(teacher and teacher.role == Teacher.ROLE_SUBJECT_TEACHER)
    is_non_teaching_staff = bool(
        teacher and teacher.role == Teacher.ROLE_NON_TEACHING and not teacher.is_officer
    )
    is_school_admin = bool(teacher and (
        teacher.role in (Teacher.ROLE_REGISTRAR, Teacher.ROLE_PRINCIPAL)
        or (teacher.role == Teacher.ROLE_NON_TEACHING and teacher.is_officer)
    ))
    return render(request, 'accounts/tools.html', {
        'page_title': 'Tools',
        'is_adviser': is_adviser,
        'is_subject_teacher': is_subject_teacher,
        'is_non_teaching_staff': is_non_teaching_staff,
        'is_school_admin': is_school_admin,
    })


DTR_EDITABLE_FIELDS = (
    'am_arrival', 'am_departure', 'pm_arrival', 'pm_departure',
    'undertime_hours', 'undertime_minutes',
)

def build_dtr_days(year, month, exceptions, records_by_date, dtr_exceptions=None):
    """Builds the day-by-day grid for one Form 48: one entry per calendar
    day in the month, labeling non-school days (Saturday/Sunday/Holiday per
    `exceptions`) and filling in whatever DTR fields exist in
    `records_by_date` (a {date: TeacherTimeRecord} mapping) for the rest.
    Shared by the single-employee DTR view and the school-wide PDF export so
    both agree on what a day looks like.

    `dtr_exceptions` (a {date: (label, session)} mapping from
    DTRCalendarException, DTR-only and separate from `exceptions`/
    SchoolCalendarException which SF2/attendance also reads) takes priority
    over `exceptions` when both cover the same date. A whole-day exception
    (Holiday, or a Class Suspension left as Whole Day) makes the entire row
    a single label, same as before. A half-day Class Suspension only
    blanks its own session's two columns (am_label/pm_label) - the other
    session's time fields stay real and editable, since work still
    happened that half of the day."""
    dtr_exceptions = dtr_exceptions or {}
    num_days = calendar.monthrange(year, month)[1]
    days = []
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        dtr_exception = dtr_exceptions.get(d)
        label = am_label = pm_label = None
        if dtr_exception:
            exc_label, exc_session = dtr_exception
            if exc_session == DTRCalendarException.SESSION_AM:
                is_school_day = True
                am_label = exc_label
            elif exc_session == DTRCalendarException.SESSION_PM:
                is_school_day = True
                pm_label = exc_label
            else:
                is_school_day = False
                label = exc_label
        else:
            is_school_day = exceptions.get(d, d.weekday() < 5)
            if not is_school_day:
                label = 'Saturday' if d.weekday() == 5 else 'Sunday' if d.weekday() == 6 else 'Holiday'
        record = records_by_date.get(d)
        entry = {'day': day, 'date': d.isoformat(), 'label': label, 'am_label': am_label, 'pm_label': pm_label}
        for field in DTR_EDITABLE_FIELDS:
            entry[field] = getattr(record, field, '') or '' if record else ''
        if am_label:
            entry['am_arrival'] = entry['am_departure'] = ''
        if pm_label:
            entry['pm_arrival'] = entry['pm_departure'] = ''
        days.append(entry)
    return days


def _dtr_calendar_exceptions(school_profile_id, year, month):
    """{date: (label, session)} for this school/month, from the DTR-only
    calendar (school.views.add_dtr_calendar_exception) - shared by the
    single-employee DTR view and the school-wide PDF export, same as
    `exceptions`/SchoolCalendarException is."""
    if not school_profile_id:
        return {}
    return {
        e.date: (e.get_reason_display(), e.session)
        for e in DTRCalendarException.objects.filter(
            school_profile_id=school_profile_id, date__year=year, date__month=month
        )
    }


def _dtr_name_tokens(name):
    """Splits a name into lowercase word tokens regardless of format -
    "Dela Cruz, Juan A." and "Juan Dela Cruz" both become
    {'dela', 'cruz', 'juan', 'a'} - so format/comma/order/middle-initial
    differences between a biometric export's name column and a teacher's
    own registered full_name don't block a match."""
    normalized = name.replace(',', ' ').replace('.', ' ')
    return [w.lower() for w in normalized.split() if w]


def _dtr_names_match(own_full_name, other_name, min_common=2):
    """True if `other_name` is plausibly the same person as `own_full_name`,
    tolerating "Lastname, Givenname" / "Givenname Surname" /
    "Givenname Middle Surname" format differences and word order.

    Requires the FIRST word of own_full_name (assumed to be the given name,
    since that's how the registration form's free-text "Full Name" field is
    conventionally filled in) to appear in other_name, in addition to at
    least `min_common` shared words overall. The given-name anchor matters:
    plain "at least 2 shared words" alone is unsafe with common Filipino
    multi-word surnames - "Juan Dela Cruz" and "Maria Dela Cruz" already
    share 2 words ("dela", "cruz") without it, which would wrongly match two
    different people."""
    own_tokens = _dtr_name_tokens(own_full_name)
    if not own_tokens:
        return False
    given_name = own_tokens[0]
    other_tokens = set(_dtr_name_tokens(other_name))
    if given_name not in other_tokens:
        return False
    return len(set(own_tokens) & other_tokens) >= min_common


def _dtr_record_for_date(employee_name, teacher, school_teacher_ids, d):
    """Same fuzzy-match + 'own teacher_id wins' tie-break as
    daily_time_record's per-month merge below, but for a single date - so
    code that fills in a blank field writes into the exact record the page
    would display for that date, instead of creating a second, competing
    record. Without this, a new own-teacher_id record would silently win
    display priority over a registrar's bulk-uploaded one (same tie-break,
    own teacher_id always wins), making that day's other fields look like
    they'd vanished even though the original record is untouched."""
    existing = None
    for r in TeacherTimeRecord.objects.filter(teacher_id__in=school_teacher_ids, date=d):
        if not _dtr_names_match(employee_name, r.employee_name):
            continue
        if existing is None or (existing.teacher_id != teacher.teacher_id and r.teacher_id == teacher.teacher_id):
            existing = r
    return existing


_AM_PM_SUFFIX_RE = re.compile(r'\s*[AaPp]\.?[Mm]\.?\s*$')

DTR_TIME_FIELDS = ('am_arrival', 'am_departure', 'pm_arrival', 'pm_departure')


def _strip_am_pm(value):
    """Drops a trailing AM/PM marker from a DTR time cell for this page's
    on-screen table only - its A. M. / P. M. column headers already say
    which half of the day each cell belongs to, so repeating it inside
    every cell is redundant here. The printable PDF export (school/views.py's
    download_dtr_pdf, a separate template) is untouched and keeps it."""
    return _AM_PM_SUFFIX_RE.sub('', value) if value else value


@login_required
def daily_time_record(request):
    teacher = Teacher.objects.filter(username=request.user.username).first()
    today = date.today()
    try:
        year = int(request.GET.get('year', today.year))
    except ValueError:
        year = today.year
    try:
        month = int(request.GET.get('month', today.month))
    except ValueError:
        month = today.month
    if month < 1 or month > 12:
        month = today.month

    # Each account only ever sees/edits its own name's DTR - no override via
    # a query param, and no browsing another employee's records by typing a
    # different name (which used to be possible via a search box and
    # free-text rename here, and would otherwise leak into the registrar's
    # school-wide PDF export). What counts as "its own name" is now a fuzzy
    # match (_dtr_names_match) rather than an exact string, and looks across
    # every teacher_id at this school rather than only this account's own -
    # a registrar's bulk DTR upload (school.views.school_dtr_upload) stamps
    # every imported record with the *uploader's* teacher_id and whatever
    # name format the biometric export used, so without this a teacher would
    # never see DTR data a registrar prepared for them.
    employee_name = teacher.full_name if teacher else ''

    # SF2's own school-day convention (grades/views.py's _school_days_in_month):
    # Mon-Fri are school days and Sat/Sun are not, unless a
    # SchoolCalendarException for this school flips a specific date the
    # other way (a declared holiday on a weekday, or a Saturday make-up
    # class). Same source of truth here, so the DTR and SF2 never disagree
    # about which dates are Saturday/Sunday/Holiday for a given school.
    exceptions = {}
    if teacher and teacher.school_profile_id:
        exceptions = {
            e.date: e.is_school_day
            for e in SchoolCalendarException.objects.filter(
                school_profile_id=teacher.school_profile_id, date__year=year, date__month=month
            )
        }

    records_by_date = {}
    if teacher:
        if teacher.school_profile_id:
            school_teacher_ids = Teacher.objects.filter(
                school_profile_id=teacher.school_profile_id
            ).values_list('teacher_id', flat=True)
        else:
            school_teacher_ids = [teacher.teacher_id]

        candidates = TeacherTimeRecord.objects.filter(
            teacher_id__in=school_teacher_ids, date__year=year, date__month=month
        )
        for r in candidates:
            if not _dtr_names_match(employee_name, r.employee_name):
                continue
            existing = records_by_date.get(r.date)
            # A record this account entered/edited itself (save_dtr_cell
            # always writes under the viewing account's own teacher_id and
            # exact full_name) is the more trustworthy source for that date
            # over a registrar's bulk-uploaded, fuzzy-matched one.
            if existing is None or (existing.teacher_id != teacher.teacher_id and r.teacher_id == teacher.teacher_id):
                records_by_date[r.date] = r

    dtr_exceptions = _dtr_calendar_exceptions(teacher.school_profile_id if teacher else None, year, month)
    days = build_dtr_days(year, month, exceptions, records_by_date, dtr_exceptions)
    for entry in days:
        for field in DTR_TIME_FIELDS:
            entry[field] = _strip_am_pm(entry[field])

    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)

    return render(request, 'accounts/dtr.html', {
        'teacher': teacher,
        'employee_name': employee_name,
        'month': month,
        'month_name': date(year, month, 1).strftime('%B'),
        'year': year,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'prev_month_name': date(prev_year, prev_month, 1).strftime('%B'),
        'next_year': next_year,
        'next_month': next_month,
        'next_month_name': date(next_year, next_month, 1).strftime('%B'),
        'days': days,
    })


def _dtr_parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
        return value
    text = str(value).strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _dtr_parse_time(value):
    """Returns a 12-hour "H:MM AM/PM" label for a cell value from a DTR
    app's export, or None if it's blank/unparseable. Accepts an actual
    time/datetime object (openpyxl gives these for real Excel time cells)
    or common text formats (24-hour "HH:MM[:SS]" or 12-hour "H:MM AM/PM",
    as plain punch-log exports tend to use)."""
    if value in (None, ''):
        return None
    if hasattr(value, 'strftime') and hasattr(value, 'hour') and not hasattr(value, 'year'):
        t = value
    elif hasattr(value, 'time') and hasattr(value, 'year'):
        t = value.time()
    else:
        text = str(value).strip()
        t = None
        for fmt in ('%H:%M:%S', '%H:%M', '%I:%M %p', '%I:%M:%S %p'):
            try:
                t = datetime.strptime(text, fmt).time()
                break
            except ValueError:
                continue
        if t is None:
            return None
    return t.strftime('%I:%M %p').lstrip('0')


def _dtr_parse_upload_bulk(uploaded_file):
    """Parses a whole-school CSV/Excel export from a DTR (biometric time
    clock) app into {employee_name: {date: {'am_arrival': ...,
    'am_departure': ..., 'pm_arrival': ..., 'pm_departure': ...}}}. Returns
    (parsed_dict, error_message) - exactly one of the two is set. Every
    employee found in the file's Name/Employee column is included - this is
    a bulk, all-employees import, not scoped to any one person.

    Three export shapes are supported, tried in this order:
    - Separate "Arrival Date"/"Arrival Time" and "Departure Date"/
      "Departure Time" columns (the actual shape of the school's DTR app
      export - a "Total" column, if present, is ignored). Arrival and
      departure are logged as independent events under their own date
      column, since a real export can have a lone arrival or departure
      with the other side blank, or a departure dated the day after its
      arrival.
    - A pre-aggregated single Date + "Time In" + "Time Out" (one in/out
      pair per day) - mapped to AM Arrival / PM Departure.
    - A raw punch log: Date + Time, one row per scan. Up to 4 punches for
      a day are sorted chronologically and distributed across AM/PM
      Arrival/Departure (2 punches -> AM Arrival + PM Departure, no lunch
      break recorded; 3 -> AM Arrival, AM Departure, PM Departure; 4 -> all
      four slots).
    """
    if uploaded_file.size > upload_utils.MAX_UPLOAD_BYTES:
        return None, (
            f'That file is too large ({uploaded_file.size // (1024 * 1024)} MB) - '
            f'the limit is {upload_utils.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'
        )

    filename = uploaded_file.name.lower()
    if filename.endswith('.csv'):
        text = uploaded_file.read().decode('utf-8-sig', errors='ignore')
        rows = list(csv.reader(io.StringIO(text)))
    elif filename.endswith(('.xlsx', '.xlsm')):
        wb = openpyxl.load_workbook(uploaded_file, data_only=True)
        rows = [list(row) for row in wb.active.iter_rows(values_only=True)]
    else:
        return None, 'Please upload a .csv or .xlsx file.'

    rows = [row for row in rows if row and any(c not in (None, '') for c in row)]
    if not rows:
        return None, 'The file is empty.'

    header = [str(h or '').strip().lower() for h in rows[0]]

    def col_index(*names):
        for name in names:
            if name in header:
                return header.index(name)
        return None

    def cell(row, idx):
        return row[idx] if idx is not None and idx < len(row) else None

    name_col = col_index('name', 'employee', 'employee name', 'teacher')
    arrival_date_col = col_index('arrival date')
    arrival_time_col = col_index('arrival time')
    departure_date_col = col_index('departure date')
    departure_time_col = col_index('departure time')
    date_col = col_index('date')
    time_col = col_index('time', 'punch time', 'check time', 'time recorded')
    time_in_col = col_index('time in', 'timein', 'am in')
    time_out_col = col_index('time out', 'timeout', 'pm out')

    if name_col is None:
        return None, 'Could not find a "Name" (or "Employee") column in the file - a bulk upload needs one to know whose record each row is.'
    if arrival_date_col is None and departure_date_col is None and date_col is None:
        return None, 'Could not find a "Date" (or "Arrival Date"/"Departure Date") column in the file.'

    def row_name(row):
        return str(cell(row, name_col) or '').strip()

    aggregated = {}
    punches_by_key = {}

    if arrival_date_col is not None or departure_date_col is not None:
        for row in rows[1:]:
            name = row_name(row)
            if not name:
                continue
            # Every named row claims this employee, even if this particular
            # row's date/time can't be parsed - so they still get a (blank)
            # Form 48 for the month instead of being silently dropped.
            aggregated.setdefault(name, {})
            raw_arrival_date = cell(row, arrival_date_col)
            if raw_arrival_date not in (None, ''):
                d = _dtr_parse_date(raw_arrival_date)
                t = _dtr_parse_time(cell(row, arrival_time_col))
                if d and t:
                    aggregated.setdefault(name, {}).setdefault(d, {})['am_arrival'] = t
            raw_departure_date = cell(row, departure_date_col)
            if raw_departure_date not in (None, ''):
                d = _dtr_parse_date(raw_departure_date)
                t = _dtr_parse_time(cell(row, departure_time_col))
                if d and t:
                    aggregated.setdefault(name, {}).setdefault(d, {})['pm_departure'] = t
    else:
        for row in rows[1:]:
            name = row_name(row)
            if not name:
                continue
            aggregated.setdefault(name, {})
            d = _dtr_parse_date(cell(row, date_col))
            if not d:
                continue

            if time_in_col is not None or time_out_col is not None:
                entry = aggregated.setdefault(name, {}).setdefault(d, {})
                t_in = _dtr_parse_time(cell(row, time_in_col))
                if t_in:
                    entry['am_arrival'] = t_in
                t_out = _dtr_parse_time(cell(row, time_out_col))
                if t_out:
                    entry['pm_departure'] = t_out
            elif time_col is not None:
                raw_time = cell(row, time_col)
                if hasattr(raw_time, 'time') and hasattr(raw_time, 'year'):
                    time_obj = raw_time.time()
                elif hasattr(raw_time, 'hour') and not hasattr(raw_time, 'year'):
                    time_obj = raw_time
                else:
                    time_obj = None
                    for fmt in ('%H:%M:%S', '%H:%M', '%I:%M %p', '%I:%M:%S %p'):
                        try:
                            time_obj = datetime.strptime(str(raw_time).strip(), fmt).time()
                            break
                        except ValueError:
                            continue
                if time_obj is not None:
                    punches_by_key.setdefault((name, d), []).append(time_obj)

    for (name, d), punches in punches_by_key.items():
        punches.sort()
        labels = [t.strftime('%I:%M %p').lstrip('0') for t in punches]
        entry = aggregated.setdefault(name, {}).setdefault(d, {})
        if len(labels) >= 4:
            entry['am_arrival'], entry['am_departure'], entry['pm_arrival'], entry['pm_departure'] = labels[:4]
        elif len(labels) == 3:
            entry['am_arrival'], entry['am_departure'], entry['pm_departure'] = labels
        elif len(labels) == 2:
            entry['am_arrival'], entry['pm_departure'] = labels
        elif len(labels) == 1:
            entry['am_arrival'] = labels[0]

    if not aggregated:
        return None, 'No named rows were found in that file.'
    return aggregated, None


@login_required
def upload_dtr(request):
    if request.method != 'POST':
        return redirect('daily_time_record')

    teacher = Teacher.objects.filter(username=request.user.username).first()
    if not teacher:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('school_dtr_upload')

    uploaded_file = request.FILES.get('dtr_file')
    if not uploaded_file:
        messages.error(request, 'Please choose a CSV or Excel file to upload.')
        return redirect('school_dtr_upload')

    today = date.today()
    try:
        target_year = int(request.POST.get('year', today.year))
        target_month = int(request.POST.get('month', today.month))
    except ValueError:
        target_year, target_month = today.year, today.month

    try:
        parsed_by_employee, error = _dtr_parse_upload_bulk(uploaded_file)
    except Exception:
        parsed_by_employee, error = None, 'Could not read that file. Please upload a valid CSV or Excel export.'

    if error:
        messages.error(request, error)
        return redirect('school_dtr_upload')

    # This upload is bound to whichever month/year was selected on the
    # form - only rows for that exact month get saved per employee;
    # anything else in the file is reported as skipped. Every named
    # employee is registered for the month even with zero parseable rows
    # (a placeholder record with blank fields), so their Form 48 still
    # shows up - just blank - rather than being silently dropped.
    employees_imported = 0
    days_imported = 0
    days_skipped = 0

    for employee_name, parsed in parsed_by_employee.items():
        in_month = {d: entry for d, entry in parsed.items() if d.year == target_year and d.month == target_month}
        days_skipped += len(parsed) - len(in_month)

        employees_imported += 1
        for d, entry in in_month.items():
            record, _ = TeacherTimeRecord.objects.get_or_create(
                teacher_id=teacher.teacher_id, employee_name=employee_name, date=d
            )
            for field in ('am_arrival', 'am_departure', 'pm_arrival', 'pm_departure'):
                if entry.get(field):
                    setattr(record, field, entry[field])
            record.save()
        days_imported += len(in_month)

        if not in_month:
            TeacherTimeRecord.objects.get_or_create(
                teacher_id=teacher.teacher_id, employee_name=employee_name, date=date(target_year, target_month, 1)
            )

    target_label = date(target_year, target_month, 1).strftime('%B %Y')
    if employees_imported:
        note = f' ({days_skipped} day(s) fell outside {target_label} and were skipped)' if days_skipped else ''
        messages.success(
            request,
            f'Imported time records for {employees_imported} employee(s) - {days_imported} day(s) total in {target_label}{note}.'
        )
    else:
        messages.error(request, f'That file had no records for {target_label}.')
    return redirect('school_dtr_upload')


@login_required
def save_dtr_cell(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    teacher = Teacher.objects.filter(username=request.user.username).first()
    if not teacher:
        return JsonResponse({'error': 'Not linked to a Teacher profile.'}, status=403)

    field = request.POST.get('field')
    if field not in DTR_EDITABLE_FIELDS:
        return JsonResponse({'error': 'Invalid field.'}, status=400)

    try:
        d = datetime.strptime(request.POST.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date.'}, status=400)

    # Always this account's own name, never a client-submitted one - stops
    # an account from planting a stray record under someone else's name
    # that would otherwise leak into the registrar's school-wide PDF export.
    employee_name = teacher.full_name
    value = request.POST.get('value', '').strip()
    record, _ = TeacherTimeRecord.objects.get_or_create(
        teacher_id=teacher.teacher_id, employee_name=employee_name, date=d
    )
    setattr(record, field, value or None)
    record.save()
    return JsonResponse({'status': 'ok'})


@login_required
def bulk_fill_dtr_lunch(request):
    """One-click fill for the AM Departure / PM Arrival columns (the lunch
    break punches) across a whole month - the same two times every school
    day for most teachers, so typing them in one day at a time is pure
    busywork. Only fills currently-blank cells (never overwrites a day the
    teacher already entered something different for), and only touches
    actual school days - weekends, holidays, and class-suspension dates
    (all represented the same way by SchoolCalendarException, same as the
    Saturday/Sunday/Holiday labels build_dtr_days already shows) are
    skipped entirely, matching the rows that have no editable cells at all
    on the page."""
    if request.method != 'POST':
        return redirect('daily_time_record')

    teacher = Teacher.objects.filter(username=request.user.username).first()
    if not teacher:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('daily_time_record')

    today = date.today()
    try:
        year = int(request.POST.get('year', today.year))
    except ValueError:
        year = today.year
    try:
        month = int(request.POST.get('month', today.month))
    except ValueError:
        month = today.month

    redirect_url = f"{reverse('daily_time_record')}?year={year}&month={month}"

    # <input type="time"> submits 24-hour "HH:MM" - normalized through the
    # same parser the bulk upload uses, so a filled cell reads the same
    # "H:MM AM/PM" (displayed here with the AM/PM stripped, same as any
    # other cell on this page) as every other entry path into this table.
    am_departure = _dtr_parse_time(request.POST.get('am_departure', '').strip())
    pm_arrival = _dtr_parse_time(request.POST.get('pm_arrival', '').strip())
    if not am_departure and not pm_arrival:
        messages.error(request, 'Enter an AM Departure and/or PM Arrival time to fill.')
        return redirect(redirect_url)

    exceptions = {}
    if teacher.school_profile_id:
        exceptions = {
            e.date: e.is_school_day
            for e in SchoolCalendarException.objects.filter(
                school_profile_id=teacher.school_profile_id, date__year=year, date__month=month
            )
        }

    employee_name = teacher.full_name
    if teacher.school_profile_id:
        school_teacher_ids = list(Teacher.objects.filter(
            school_profile_id=teacher.school_profile_id
        ).values_list('teacher_id', flat=True))
    else:
        school_teacher_ids = [teacher.teacher_id]

    num_days = calendar.monthrange(year, month)[1]
    filled = 0
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        is_school_day = exceptions.get(d, d.weekday() < 5)
        if not is_school_day:
            continue

        record = _dtr_record_for_date(employee_name, teacher, school_teacher_ids, d)
        if record is None:
            record = TeacherTimeRecord(teacher_id=teacher.teacher_id, employee_name=employee_name, date=d)

        changed = False
        if am_departure and not record.am_departure:
            record.am_departure = am_departure
            changed = True
        if pm_arrival and not record.pm_arrival:
            record.pm_arrival = pm_arrival
            changed = True
        if changed:
            record.save()
            filled += 1

    messages.success(request, f'⚡ Filled lunch break times for {filled} school day(s).')
    return redirect(redirect_url)


@login_required
def save_dtr_signature(request):
    """Saves (or clears, on an empty value) the on-screen-drawn signature
    used under the certification statement on the DTR card - one per
    teacher, reused on every month's card rather than re-drawn each time."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    teacher = Teacher.objects.filter(username=request.user.username).first()
    if not teacher:
        return JsonResponse({'error': 'Not linked to a Teacher profile.'}, status=403)

    signature = request.POST.get('signature', '').strip()
    if signature:
        if not signature.startswith('data:image/png;base64,'):
            return JsonResponse({'error': 'Invalid signature format.'}, status=400)
        if len(signature) > 200_000:
            return JsonResponse({'error': 'Signature image is too large.'}, status=400)
        teacher.signature_image = signature
    else:
        teacher.signature_image = None
    teacher.save()
    return JsonResponse({'status': 'ok', 'signature': teacher.signature_image})