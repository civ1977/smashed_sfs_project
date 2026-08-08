import calendar
import csv
import io
import math
from datetime import date, datetime

import openpyxl
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse

from students.models import Section, Student
from portal.models import StudentAccount
from grades.models import Grade, SubjectMapping, SchoolCalendarException
from .models import Teacher, TeacherTimeRecord
from .forms import SchoolProfileSelectForm, SchoolProfileForm, SectionForm

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


def register(request):
    account_type = request.POST.get('account_type') or request.GET.get('type')
    if account_type != 'non_teaching':
        account_type = 'teaching'

    if request.method == 'POST':
        username = request.POST.get('username')
        full_name = request.POST.get('full_name')
        position = request.POST.get('position')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')

        if account_type == 'non_teaching':
            role = Teacher.ROLE_NON_TEACHING
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
            user.save()

            Teacher.objects.create(
                user=user,
                username=username,
                password=user.password,
                full_name=full_name,
                position=position,
                email=email,
                role=role,
            )

        login(request, user)
        messages.success(request, f'Registration successful! Welcome {username}!')
        return redirect('complete_profile')

    return render(request, 'accounts/register.html', {'account_type': account_type})


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


def contact_us(request):
    return render(request, 'accounts/public_contact_us.html')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


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
        return render(request, 'accounts/no_dashboard.html', {'teacher': teacher})

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

    school_select_form = SchoolProfileSelectForm(data, prefix='school') if needs_school else None
    school_create_form = SchoolProfileForm(data, prefix='newschool') if needs_school else None
    section_form = SectionForm(data, prefix='section') if needs_section else None

    if request.method == 'POST':
        new_school_needed = False
        school_valid = True
        if needs_school:
            school_valid = school_select_form.is_valid()
            new_school_needed = school_valid and school_select_form.is_new_school()
            if new_school_needed:
                school_valid = school_create_form.is_valid()

        section_valid = section_form.is_valid() if needs_section else True

        if school_valid and section_valid:
            with transaction.atomic():
                if needs_school:
                    if new_school_needed:
                        school_profile = school_create_form.save(commit=False)
                        school_profile.created_by = teacher.teacher_id
                        school_profile.save()
                        profile_id = school_profile.profile_id
                    else:
                        profile_id = int(school_select_form.cleaned_data['school_profile'])
                    teacher.school_profile_id = profile_id
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
        'school_select_form': school_select_form,
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
    is_school_admin = bool(teacher and teacher.role in (Teacher.ROLE_REGISTRAR, Teacher.ROLE_PRINCIPAL))
    return render(request, 'accounts/tools.html', {
        'page_title': 'Tools',
        'is_adviser': is_adviser,
        'is_school_admin': is_school_admin,
    })


DTR_EDITABLE_FIELDS = (
    'am_arrival', 'am_departure', 'pm_arrival', 'pm_departure',
    'undertime_hours', 'undertime_minutes',
)


@login_required
def daily_time_record(request):
    teacher = Teacher.objects.filter(username=request.user.username).first()
    today = date.today()
    year, month = today.year, today.month

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
        records_by_date = {
            r.date: r for r in TeacherTimeRecord.objects.filter(
                teacher_id=teacher.teacher_id, date__year=year, date__month=month
            )
        }

    num_days = calendar.monthrange(year, month)[1]
    days = []
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        is_school_day = exceptions.get(d, d.weekday() < 5)
        if not is_school_day:
            label = 'Saturday' if d.weekday() == 5 else 'Sunday' if d.weekday() == 6 else 'Holiday'
        else:
            label = None
        record = records_by_date.get(d)
        entry = {'day': day, 'date': d.isoformat(), 'label': label}
        for field in DTR_EDITABLE_FIELDS:
            entry[field] = getattr(record, field, '') or '' if record else ''
        days.append(entry)

    return render(request, 'accounts/dtr.html', {
        'teacher': teacher,
        'month_name': today.strftime('%B'),
        'year': today.strftime('%Y'),
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


def _dtr_parse_upload(uploaded_file, teacher_name):
    """Parses a CSV/Excel export from a DTR (biometric time clock) app into
    {date: {'am_arrival': ..., 'am_departure': ..., 'pm_arrival': ...,
    'pm_departure': ...}}. Returns (parsed_dict, error_message) - exactly
    one of the two is set.

    Two export shapes are supported:
    - A punch log: Date + Time columns, one row per scan. Up to 4 punches
      for a day are sorted chronologically and distributed across AM/PM
      Arrival/Departure (2 punches -> AM Arrival + PM Departure, no lunch
      break recorded; 3 -> AM Arrival, AM Departure, PM Departure; 4 -> all
      four slots).
    - A pre-aggregated Date + "Time In" + "Time Out" (single in/out per
      day) - mapped to AM Arrival / PM Departure.

    An optional Name/Employee column, if present, filters to rows matching
    this teacher (case-insensitive substring match), so a whole-school
    export can be uploaded as-is.
    """
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

    date_col = col_index('date')
    name_col = col_index('name', 'employee', 'employee name', 'teacher')
    time_col = col_index('time', 'punch time', 'check time', 'time recorded')
    time_in_col = col_index('time in', 'timein', 'am in')
    time_out_col = col_index('time out', 'timeout', 'pm out')

    if date_col is None:
        return None, 'Could not find a "Date" column in the file.'

    name_needle = (teacher_name or '').strip().lower()
    aggregated = {}
    punches_by_date = {}

    for row in rows[1:]:
        if name_col is not None and name_needle:
            row_name = str(row[name_col] or '').strip().lower() if name_col < len(row) else ''
            if name_needle not in row_name:
                continue

        raw_date = row[date_col] if date_col < len(row) else None
        d = _dtr_parse_date(raw_date)
        if not d:
            continue

        if time_in_col is not None or time_out_col is not None:
            entry = aggregated.setdefault(d, {})
            if time_in_col is not None and time_in_col < len(row):
                t = _dtr_parse_time(row[time_in_col])
                if t:
                    entry['am_arrival'] = t
            if time_out_col is not None and time_out_col < len(row):
                t = _dtr_parse_time(row[time_out_col])
                if t:
                    entry['pm_departure'] = t
        elif time_col is not None and time_col < len(row):
            raw_time = row[time_col]
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
                punches_by_date.setdefault(d, []).append(time_obj)

    for d, punches in punches_by_date.items():
        punches.sort()
        labels = [t.strftime('%I:%M %p').lstrip('0') for t in punches]
        entry = aggregated.setdefault(d, {})
        if len(labels) >= 4:
            entry['am_arrival'], entry['am_departure'], entry['pm_arrival'], entry['pm_departure'] = labels[:4]
        elif len(labels) == 3:
            entry['am_arrival'], entry['am_departure'], entry['pm_departure'] = labels
        elif len(labels) == 2:
            entry['am_arrival'], entry['pm_departure'] = labels
        elif len(labels) == 1:
            entry['am_arrival'] = labels[0]

    if not aggregated:
        return None, 'No matching time records were found in that file.'
    return aggregated, None


@login_required
def upload_dtr(request):
    if request.method != 'POST':
        return redirect('daily_time_record')

    teacher = Teacher.objects.filter(username=request.user.username).first()
    if not teacher:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('daily_time_record')

    uploaded_file = request.FILES.get('dtr_file')
    if not uploaded_file:
        messages.error(request, 'Please choose a CSV or Excel file to upload.')
        return redirect('daily_time_record')

    try:
        parsed, error = _dtr_parse_upload(uploaded_file, teacher.full_name)
    except Exception:
        parsed, error = None, 'Could not read that file. Please upload a valid CSV or Excel export.'

    if error:
        messages.error(request, error)
        return redirect('daily_time_record')

    today = date.today()
    in_month = {d: entry for d, entry in parsed.items() if d.year == today.year and d.month == today.month}
    skipped = len(parsed) - len(in_month)

    for d, entry in in_month.items():
        record, _ = TeacherTimeRecord.objects.get_or_create(teacher_id=teacher.teacher_id, date=d)
        for field in ('am_arrival', 'am_departure', 'pm_arrival', 'pm_departure'):
            if entry.get(field):
                setattr(record, field, entry[field])
        record.save()

    if in_month:
        note = f' ({skipped} outside {today.strftime("%B %Y")} were skipped)' if skipped else ''
        messages.success(request, f'Imported time records for {len(in_month)} day(s){note}.')
    else:
        messages.error(request, f'That file had no records for {today.strftime("%B %Y")}.')
    return redirect('daily_time_record')


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

    value = request.POST.get('value', '').strip()
    record, _ = TeacherTimeRecord.objects.get_or_create(teacher_id=teacher.teacher_id, date=d)
    setattr(record, field, value or None)
    record.save()
    return JsonResponse({'status': 'ok'})