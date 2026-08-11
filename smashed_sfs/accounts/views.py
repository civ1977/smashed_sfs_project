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

    selected_role = request.GET.get('role')
    if selected_role not in TEACHING_ROLE_CHOICES:
        selected_role = None

    return render(request, 'accounts/register.html', {
        'account_type': account_type,
        'selected_role': selected_role,
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


def build_dtr_days(year, month, exceptions, records_by_date):
    """Builds the day-by-day grid for one Form 48: one entry per calendar
    day in the month, labeling non-school days (Saturday/Sunday/Holiday per
    `exceptions`) and filling in whatever DTR fields exist in
    `records_by_date` (a {date: TeacherTimeRecord} mapping) for the rest.
    Shared by the single-employee DTR view and the school-wide PDF export so
    both agree on what a day looks like."""
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
    return days


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
    # a query param. Prevents one account from reading or planting records
    # under someone else's name (which used to be possible via a search box
    # and free-text rename here, and would otherwise leak into the
    # registrar's school-wide PDF export).
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
        records_by_date = {
            r.date: r for r in TeacherTimeRecord.objects.filter(
                teacher_id=teacher.teacher_id, employee_name=employee_name, date__year=year, date__month=month
            )
        }

    days = build_dtr_days(year, month, exceptions, records_by_date)

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