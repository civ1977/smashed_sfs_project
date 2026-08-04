import math

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction

from students.models import Section, Student
from portal.models import StudentAccount
from grades.models import Grade, SubjectMapping
from .models import Teacher
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
            return redirect('portal_dashboard')
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
    """Placeholder - content to be defined later."""
    return render(request, 'accounts/coming_soon.html', {'page_title': 'Tools'
    })