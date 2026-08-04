from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q

from accounts.models import Teacher
from students.models import SchoolProfile, Section, Student
from portal.models import StudentAccount
from grades.models import SubjectMapping, TeacherSubjectAssignment


def _get_school_admin_teacher(request):
    """Resolve the requesting Teacher and confirm they're not an adviser.
    Returns (teacher, error_redirect) - error_redirect is None on success."""
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return None, redirect('login')

    if teacher.role not in (Teacher.ROLE_REGISTRAR, Teacher.ROLE_PRINCIPAL):
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
        return render(request, 'school/accounts.html', {'account_rows': [], 'sections': [], 'student_account_rows': []})

    teachers = Teacher.objects.filter(school_profile_id=teacher.school_profile_id).order_by('full_name')
    sections = Section.objects.filter(school_profile_id=teacher.school_profile_id).order_by('grade_level', 'section_name')
    sections_by_adviser = {s.adviser_id: s for s in sections if s.adviser_id}

    account_rows = [
        {'teacher': t, 'section': sections_by_adviser.get(t.teacher_id)}
        for t in teachers
    ]

    section_ids = [s.section_id for s in sections]
    students_by_lrn = {
        s.lrn: s for s in Student.objects.filter(section_id__in=section_ids)
    }
    student_accounts = StudentAccount.objects.filter(lrn__in=students_by_lrn.keys()).order_by('lrn')

    student_account_rows = [
        {'account': a, 'student': students_by_lrn.get(a.lrn)}
        for a in student_accounts
    ]

    return render(request, 'school/accounts.html', {
        'account_rows': account_rows,
        'sections': sections,
        'student_account_rows': student_account_rows,
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
def toggle_student_account_active(request, account_id):
    if request.method != 'POST':
        return redirect('school_accounts')

    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    target = StudentAccount.objects.filter(account_id=account_id).first()
    if not target:
        messages.error(request, 'Student account not found.')
        return redirect('school_accounts')

    # Same scoping discipline as everywhere else: only students whose section
    # sits in this registrar/principal's own school - never another school's.
    section_ids = Section.objects.filter(
        school_profile_id=teacher.school_profile_id
    ).values_list('section_id', flat=True)
    student = Student.objects.filter(lrn=target.lrn, section_id__in=section_ids).first()
    if not student:
        messages.error(request, 'Student account not found in this school.')
        return redirect('school_accounts')

    target.is_active = not target.is_active
    target.save()

    # StudentAccount.is_active is this app's own record of standing; the
    # linked auth.User.is_active is what Django's authenticate() actually
    # checks, so keep them in sync - that's what blocks (or restores) future
    # login. This never touches Grade/Attendance/Student rows, so historical
    # data stays intact either way.
    target.user.is_active = target.is_active
    target.user.save()

    status = 'activated' if target.is_active else 'deactivated'
    messages.success(request, f'✅ {student.surname}, {student.name} account {status}.')
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


@login_required
def school_assignments(request):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    if not teacher.school_profile_id:
        messages.warning(request, 'Your account has no school assigned yet.')
        return render(request, 'school/assignments.html', {
            'teacher_rows': [], 'subject_teachers': [], 'sections': [], 'mappings': [],
        })

    if request.method == 'POST':
        subject_teacher_id = request.POST.get('teacher_id', '').strip()
        section_id = request.POST.get('section_id', '').strip()
        mapping_id = request.POST.get('mapping_id', '').strip()

        if not (subject_teacher_id and section_id and mapping_id):
            messages.error(request, 'Select a subject teacher, section, and subject.')
            return redirect('school_assignments')

        subject_teacher = Teacher.objects.filter(
            teacher_id=subject_teacher_id,
            school_profile_id=teacher.school_profile_id,
            role__in=(Teacher.ROLE_SUBJECT_TEACHER, Teacher.ROLE_ADVISER),
        ).first()
        section = Section.objects.filter(
            section_id=section_id, school_profile_id=teacher.school_profile_id
        ).first()
        mapping = SubjectMapping.objects.filter(
            mapping_id=mapping_id, school_profile_id=teacher.school_profile_id
        ).first()

        if not (subject_teacher and section and mapping):
            messages.error(request, 'Selected teacher, section, or subject not found in this school.')
            return redirect('school_assignments')

        # A subject only makes sense against a section studying the same
        # grade level (and, when the subject specifies one, the same
        # strand) - otherwise a Grade 11 STEM subject could end up
        # assigned against a Grade 12 ABM section.
        strand_mismatch = mapping.strand and mapping.strand != section.strand
        if mapping.grade_level != section.grade_level or strand_mismatch:
            messages.error(
                request,
                f'{mapping.subject_name} (Grade {mapping.grade_level} {mapping.strand}) '
                f'doesn\'t match {section.grade_level}-{section.strand}-{section.section_name}.'
            )
            return redirect('school_assignments')

        TeacherSubjectAssignment.objects.create(
            teacher_id=subject_teacher.teacher_id,
            section_id=section.section_id,
            mapping_id=mapping.mapping_id,
        )
        messages.success(
            request,
            f'✅ {subject_teacher.full_name} assigned to {mapping.subject_name} in {section.section_name}.'
        )
        return redirect('school_assignments')

    subject_teachers = Teacher.objects.filter(
        school_profile_id=teacher.school_profile_id,
        role__in=(Teacher.ROLE_SUBJECT_TEACHER, Teacher.ROLE_ADVISER),
    ).order_by('full_name')

    sections = Section.objects.filter(
        school_profile_id=teacher.school_profile_id
    ).order_by('grade_level', 'strand', 'section_name')

    mappings = SubjectMapping.objects.filter(
        school_profile_id=teacher.school_profile_id, is_active=True
    ).order_by('grade_level', 'strand', 'subject_name')

    sections_by_id = {s.section_id: s for s in sections}
    mappings_by_id = {m.mapping_id: m for m in mappings}

    assignments = TeacherSubjectAssignment.objects.filter(
        teacher_id__in=[t.teacher_id for t in subject_teachers]
    ).order_by('assignment_id')

    assignments_by_teacher = {}
    for a in assignments:
        assignments_by_teacher.setdefault(a.teacher_id, []).append({
            'assignment': a,
            'section': sections_by_id.get(a.section_id),
            'mapping': mappings_by_id.get(a.mapping_id),
        })

    teacher_rows = [
        {'teacher': t, 'assignments': assignments_by_teacher.get(t.teacher_id, [])}
        for t in subject_teachers
    ]

    return render(request, 'school/assignments.html', {
        'teacher_rows': teacher_rows,
        'subject_teachers': subject_teachers,
        'sections': sections,
        'mappings': mappings,
    })


@login_required
def remove_teacher_subject_assignment(request, assignment_id):
    if request.method != 'POST':
        return redirect('school_assignments')

    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    assignment = TeacherSubjectAssignment.objects.filter(assignment_id=assignment_id).first()
    if not assignment:
        messages.error(request, 'Assignment not found.')
        return redirect('school_assignments')

    # Scope by the assignment's own teacher rather than a stored school id
    # (the model has none) - same manual-FK discipline as everywhere else.
    assignment_teacher = Teacher.objects.filter(
        teacher_id=assignment.teacher_id,
        school_profile_id=teacher.school_profile_id,
        role__in=(Teacher.ROLE_SUBJECT_TEACHER, Teacher.ROLE_ADVISER),
    ).first()
    if not assignment_teacher:
        messages.error(request, 'Assignment not found in this school.')
        return redirect('school_assignments')

    assignment.delete()
    messages.success(request, f'Assignment removed from {assignment_teacher.full_name}.')
    return redirect('school_assignments')


def _get_adviser_with_section(request):
    """Resolve the requesting Teacher, confirm they're a Class Adviser (not
    _get_school_admin_teacher, which explicitly excludes advisers), and
    resolve their own Section. Returns (teacher, section, error_redirect) -
    error_redirect is None on success."""
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return None, None, redirect('login')

    if teacher.role != Teacher.ROLE_ADVISER:
        messages.error(request, 'This page is only available to Class Advisers.')
        return None, None, redirect('dashboard')

    section = Section.objects.filter(adviser_id=teacher.teacher_id).first()
    if not section:
        messages.warning(request, 'Complete your section setup first.')
        return None, None, redirect('complete_profile')

    return teacher, section, None


@login_required
def adviser_subject_assignments(request):
    teacher, section, error = _get_adviser_with_section(request)
    if error:
        return error

    if request.method == 'POST':
        subject_teacher_id = request.POST.get('teacher_id', '').strip()
        mapping_id = request.POST.get('mapping_id', '').strip()

        if not (subject_teacher_id and mapping_id):
            messages.error(request, 'Select a teacher and a subject.')
            return redirect('adviser_subject_assignments')

        subject_teacher = Teacher.objects.filter(
            teacher_id=subject_teacher_id,
            school_profile_id=teacher.school_profile_id,
            role__in=(Teacher.ROLE_ADVISER, Teacher.ROLE_SUBJECT_TEACHER),
        ).first()
        mapping = SubjectMapping.objects.filter(
            mapping_id=mapping_id, school_profile_id=teacher.school_profile_id
        ).first()

        if not (subject_teacher and mapping):
            messages.error(request, 'Selected teacher or subject not found in this school.')
            return redirect('adviser_subject_assignments')

        # The subject dropdown is already scoped to this section's grade
        # level/strand, but keep the mismatch check as a safety net anyway
        # (mirrors school_assignments above).
        strand_mismatch = mapping.strand and mapping.strand != section.strand
        if mapping.grade_level != section.grade_level or strand_mismatch:
            messages.error(
                request,
                f'{mapping.subject_name} (Grade {mapping.grade_level} {mapping.strand}) '
                f'doesn\'t match your section {section.grade_level}-{section.strand}-{section.section_name}.'
            )
            return redirect('adviser_subject_assignments')

        # Never trust a section_id from the request - always the adviser's own.
        TeacherSubjectAssignment.objects.create(
            teacher_id=subject_teacher.teacher_id,
            section_id=section.section_id,
            mapping_id=mapping.mapping_id,
        )
        messages.success(
            request,
            f'✅ {subject_teacher.full_name} assigned to {mapping.subject_name} in {section.section_name}.'
        )
        return redirect('adviser_subject_assignments')

    # Includes the adviser themself, so they can assign themselves to teach
    # a subject in their own section.
    subject_teachers = Teacher.objects.filter(
        school_profile_id=teacher.school_profile_id,
        role__in=(Teacher.ROLE_ADVISER, Teacher.ROLE_SUBJECT_TEACHER),
    ).order_by('full_name')

    # A blank mapping.strand applies to every strand at that grade level.
    mappings = SubjectMapping.objects.filter(
        Q(strand='') | Q(strand=section.strand),
        school_profile_id=teacher.school_profile_id,
        grade_level=section.grade_level,
        is_active=True,
    ).order_by('subject_name')

    teachers_by_id = {t.teacher_id: t for t in subject_teachers}
    mappings_by_id = {m.mapping_id: m for m in mappings}

    assignments = TeacherSubjectAssignment.objects.filter(
        section_id=section.section_id
    ).order_by('assignment_id')

    assignment_rows = [
        {
            'assignment': a,
            'teacher': teachers_by_id.get(a.teacher_id)
                or Teacher.objects.filter(teacher_id=a.teacher_id).first(),
            'mapping': mappings_by_id.get(a.mapping_id)
                or SubjectMapping.objects.filter(mapping_id=a.mapping_id).first(),
        }
        for a in assignments
    ]

    return render(request, 'school/adviser_assignments.html', {
        'section': section,
        'subject_teachers': subject_teachers,
        'mappings': mappings,
        'assignment_rows': assignment_rows,
    })


@login_required
def remove_adviser_subject_assignment(request, assignment_id):
    if request.method != 'POST':
        return redirect('adviser_subject_assignments')

    teacher, section, error = _get_adviser_with_section(request)
    if error:
        return error

    # Scoped to the adviser's own section - even a guessed assignment_id from
    # another section won't match this filter.
    assignment = TeacherSubjectAssignment.objects.filter(
        assignment_id=assignment_id, section_id=section.section_id
    ).first()
    if not assignment:
        messages.error(request, 'Assignment not found in your section.')
        return redirect('adviser_subject_assignments')

    assignment_teacher = Teacher.objects.filter(teacher_id=assignment.teacher_id).first()
    assignment.delete()
    name = assignment_teacher.full_name if assignment_teacher else 'Teacher'
    messages.success(request, f'Assignment removed from {name}.')
    return redirect('adviser_subject_assignments')
