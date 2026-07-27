from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from accounts.models import Teacher
from students.models import SchoolProfile, Section, Student


def _get_school_admin_teacher(request):
    """Resolve the requesting Teacher and confirm they're not an adviser.
    Returns (teacher, error_redirect) - error_redirect is None on success."""
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return None, redirect('login')

    if teacher.role == Teacher.ROLE_ADVISER:
        messages.error(request, 'This page is only available to registrar/principal accounts.')
        return None, redirect('dashboard')

    return teacher, None


def _reassign_section_adviser(school_profile_id, section, new_adviser):
    """Point `section`'s adviser_id at `new_adviser` (a Teacher instance or
    None), clearing whatever other section that teacher previously advised
    so no teacher ends up tied to two sections at once."""
    if new_adviser is not None:
        Section.objects.filter(
            school_profile_id=school_profile_id, adviser_id=new_adviser.teacher_id
        ).exclude(section_id=section.section_id).update(adviser_id=None)
        section.adviser_id = new_adviser.teacher_id
    else:
        section.adviser_id = None
    section.save()


@login_required
def school_dashboard(request):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()

    return render(request, 'school/dashboard.html', {
        'teacher': teacher,
        'school_profile': school_profile,
    })


@login_required
def school_student_list(request):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    students = []
    if teacher.school_profile_id:
        section_ids = Section.objects.filter(
            school_profile_id=teacher.school_profile_id
        ).values_list('section_id', flat=True)
        students = Student.objects.filter(section_id__in=section_ids).order_by('surname', 'name')
    else:
        messages.warning(request, 'Your account has no school assigned yet.')

    return render(request, 'school/students.html', {'students': students})


@login_required
def school_sections(request):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    if not teacher.school_profile_id:
        messages.warning(request, 'Your account has no school assigned yet.')
        return render(request, 'school/sections.html', {'section_rows': [], 'unassigned_teachers': []})

    if request.method == 'POST':
        grade_level = request.POST.get('grade_level', '').strip()
        track = request.POST.get('track', '').strip()
        strand = request.POST.get('strand', '').strip()
        section_name = request.POST.get('section_name', '').strip()
        modality = request.POST.get('modality', '').strip()
        adviser_teacher_id = request.POST.get('adviser_teacher_id', '').strip()

        if not (grade_level and section_name):
            messages.error(request, 'Grade level and section name are required.')
            return redirect('school_sections')

        section = Section.objects.create(
            grade_level=grade_level,
            track=track,
            strand=strand,
            section_name=section_name,
            modality=modality,
            adviser_id=None,
            school_profile_id=teacher.school_profile_id,
        )

        if adviser_teacher_id:
            adviser = Teacher.objects.filter(
                teacher_id=adviser_teacher_id, school_profile_id=teacher.school_profile_id
            ).first()
            if adviser:
                _reassign_section_adviser(teacher.school_profile_id, section, adviser)
            else:
                messages.warning(request, 'Selected teacher not found - section created without an adviser.')

        messages.success(request, f'✅ Section {section_name} created.')
        return redirect('school_sections')

    sections = Section.objects.filter(
        school_profile_id=teacher.school_profile_id
    ).order_by('grade_level', 'section_name')

    adviser_ids = [s.adviser_id for s in sections if s.adviser_id]
    advisers_by_id = {t.teacher_id: t for t in Teacher.objects.filter(teacher_id__in=adviser_ids)}
    student_counts = {
        s.section_id: Student.objects.filter(section_id=s.section_id).count() for s in sections
    }

    section_rows = [
        {
            'section': s,
            'adviser': advisers_by_id.get(s.adviser_id),
            'student_count': student_counts.get(s.section_id, 0),
        }
        for s in sections
    ]

    assigned_ids = [s.adviser_id for s in sections if s.adviser_id]
    unassigned_teachers = Teacher.objects.filter(
        school_profile_id=teacher.school_profile_id, role=Teacher.ROLE_ADVISER
    ).exclude(teacher_id__in=assigned_ids).order_by('full_name')

    all_teachers = Teacher.objects.filter(
        school_profile_id=teacher.school_profile_id, role=Teacher.ROLE_ADVISER
    ).order_by('full_name')

    return render(request, 'school/sections.html', {
        'section_rows': section_rows,
        'unassigned_teachers': unassigned_teachers,
        'all_teachers': all_teachers,
    })


@login_required
def reassign_section_adviser(request, section_id):
    if request.method != 'POST':
        return redirect('school_sections')

    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    section = Section.objects.filter(
        section_id=section_id, school_profile_id=teacher.school_profile_id
    ).first()
    if not section:
        messages.error(request, 'Section not found.')
        return redirect('school_sections')

    adviser_teacher_id = request.POST.get('adviser_teacher_id', '').strip()
    if not adviser_teacher_id:
        _reassign_section_adviser(teacher.school_profile_id, section, None)
        messages.success(request, f'{section.section_name} is now unassigned.')
    else:
        adviser = Teacher.objects.filter(
            teacher_id=adviser_teacher_id, school_profile_id=teacher.school_profile_id
        ).first()
        if not adviser:
            messages.error(request, 'Teacher not found in this school.')
        else:
            _reassign_section_adviser(teacher.school_profile_id, section, adviser)
            messages.success(request, f'✅ {section.section_name} adviser reassigned to {adviser.full_name}.')

    return redirect('school_sections')


@login_required
def school_accounts(request):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    if not teacher.school_profile_id:
        messages.warning(request, 'Your account has no school assigned yet.')
        return render(request, 'school/accounts.html', {'account_rows': [], 'sections': []})

    teachers = Teacher.objects.filter(school_profile_id=teacher.school_profile_id).order_by('full_name')
    sections = Section.objects.filter(school_profile_id=teacher.school_profile_id).order_by('grade_level', 'section_name')
    sections_by_adviser = {s.adviser_id: s for s in sections if s.adviser_id}

    account_rows = [
        {'teacher': t, 'section': sections_by_adviser.get(t.teacher_id)}
        for t in teachers
    ]

    return render(request, 'school/accounts.html', {
        'account_rows': account_rows,
        'sections': sections,
    })


@login_required
def toggle_teacher_active(request, teacher_id):
    if request.method != 'POST':
        return redirect('school_accounts')

    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    target = Teacher.objects.filter(
        teacher_id=teacher_id, school_profile_id=teacher.school_profile_id
    ).first()
    if not target:
        messages.error(request, 'Teacher not found in this school.')
        return redirect('school_accounts')

    target.is_active = not target.is_active
    target.save()

    # Teacher.is_active is this app's own record of standing; the linked
    # auth.User.is_active is what Django's authenticate() actually checks,
    # so keep them in sync - that's what blocks (or restores) future login.
    # This never touches Student/Grade rows, so historical data the teacher
    # already entered stays intact either way.
    if target.user_id:
        target.user.is_active = target.is_active
        target.user.save()

    status = 'activated' if target.is_active else 'deactivated'
    messages.success(request, f'✅ {target.full_name} {status}.')
    return redirect('school_accounts')


@login_required
def reassign_teacher_section(request, teacher_id):
    if request.method != 'POST':
        return redirect('school_accounts')

    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    target = Teacher.objects.filter(
        teacher_id=teacher_id, school_profile_id=teacher.school_profile_id
    ).first()
    if not target:
        messages.error(request, 'Teacher not found in this school.')
        return redirect('school_accounts')

    section_id = request.POST.get('section_id', '').strip()
    if not section_id:
        Section.objects.filter(
            school_profile_id=teacher.school_profile_id, adviser_id=target.teacher_id
        ).update(adviser_id=None)
        messages.success(request, f'{target.full_name} unassigned from their section.')
        return redirect('school_accounts')

    section = Section.objects.filter(
        section_id=section_id, school_profile_id=teacher.school_profile_id
    ).first()
    if not section:
        messages.error(request, 'Section not found.')
        return redirect('school_accounts')

    _reassign_section_adviser(teacher.school_profile_id, section, target)
    messages.success(request, f'✅ {target.full_name} is now adviser of {section.section_name}.')
    return redirect('school_accounts')
