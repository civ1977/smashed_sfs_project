from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from accounts.models import Teacher
from students.models import Student, SchoolProfile, Section
from grades.models import Grade, SubjectMapping, Attendance, ATTENDANCE_MONTHS


def _get_teacher(request):
    return Teacher.objects.get(username=request.user.username)


def _final_average(term_grades):
    valid = [g for g in term_grades if g is not None]
    return round(sum(valid) / len(valid)) if valid else None


def _remarks_for(final):
    if final is None:
        return None
    return 'Passed' if final >= 75 else 'Failed'


def _build_subject_rows(lrn, grade_level=None, term=None):
    """Build per-subject grade rows for a student, optionally scoped to one
    subject grade_level (a student's Grade table can hold both Grade 11 and
    Grade 12 rows once they've been promoted) and/or one term (for a
    single-quarter SF9 export)."""
    grades = Grade.objects.filter(lrn=lrn)
    if term is not None:
        grades = grades.filter(term=term)

    mapping_ids = {g.mapping_id for g in grades}
    mappings = {m.mapping_id: m for m in SubjectMapping.objects.filter(mapping_id__in=mapping_ids)}

    grouped = {}
    for grade in grades:
        mapping = mappings.get(grade.mapping_id)
        if grade_level is not None and (mapping is None or mapping.grade_level != grade_level):
            continue
        grouped.setdefault(grade.mapping_id, {1: None, 2: None, 3: None})[grade.term] = grade.grade

    subject_rows = []
    for mapping_id, terms in grouped.items():
        mapping = mappings.get(mapping_id)
        subject_name = mapping.subject_name if mapping else f'Subject {mapping_id}'
        term_grades = [terms[1], terms[2], terms[3]]
        final = _final_average(term_grades)
        subject_rows.append({
            'subject_name': subject_name,
            'term_1': terms[1],
            'term_2': terms[2],
            'term_3': terms[3],
            'final': final,
            'remarks': _remarks_for(final),
        })
    subject_rows.sort(key=lambda row: row['subject_name'])
    return subject_rows


def _grade_levels_for_student(lrn):
    mapping_ids = Grade.objects.filter(lrn=lrn).values_list('mapping_id', flat=True)
    levels = SubjectMapping.objects.filter(mapping_id__in=set(mapping_ids)).values_list('grade_level', flat=True)
    return sorted(set(levels))


def _attendance_rows(lrn):
    rows = []
    for month in ATTENDANCE_MONTHS:
        attendance = Attendance.objects.filter(lrn=lrn, month=month).first()
        present = attendance.days_present if attendance is not None else None
        absent = attendance.days_absent if attendance is not None else None
        total = (present + absent) if attendance is not None else None
        rows.append({
            'month': month,
            'attendance': attendance,
            'present': present,
            'absent': absent,
            'total': total,
        })
    return rows


def _attendance_totals(attendance_rows):
    """Year-to-date totals for the SF9 monthly attendance grid."""
    present = [r['present'] for r in attendance_rows if r['attendance'] is not None]
    absent = [r['absent'] for r in attendance_rows if r['attendance'] is not None]
    if not present and not absent:
        return {'class_days': None, 'present': None, 'absent': None}
    total_present = sum(present)
    total_absent = sum(absent)
    return {
        'class_days': total_present + total_absent,
        'present': total_present,
        'absent': total_absent,
    }


def _age_from_birthday(birthday):
    if not birthday:
        return None
    today = date.today()
    had_birthday_this_year = (today.month, today.day) >= (birthday.month, birthday.day)
    return today.year - birthday.year - (0 if had_birthday_this_year else 1)


def _gate_finals_pending_term3(subject_rows):
    """A subject's Final Grade/Remarks only show once Term 3 data has
    actually been uploaded for it. Returns True if every subject on this
    report has a displayable final, which gates whether the General
    Average shows."""
    all_complete = True
    for row in subject_rows:
        if row['term_3'] is None:
            row['final'] = None
            row['remarks'] = None
            all_complete = False
    return all_complete


def _split_core_elective(subject_rows):
    """SF9 groups Learning Areas under 'Core Subjects' and 'Elective Subjects'
    headers. There's no core/elective flag in SubjectMapping, so use the
    'Elective' naming convention already used for elective subject names."""
    core_rows = [r for r in subject_rows if 'elective' not in r['subject_name'].lower()]
    elective_rows = [r for r in subject_rows if 'elective' in r['subject_name'].lower()]
    return core_rows, elective_rows


@login_required
def select_student_for_report(request):
    try:
        teacher = _get_teacher(request)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    students = Student.objects.filter(adviser_id=teacher.teacher_id).order_by('surname', 'name')

    return render(request, 'reports/select_student.html', {'students': students})


@login_required
def view_sf9(request, student_lrn):
    try:
        teacher = _get_teacher(request)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    student = get_object_or_404(Student, lrn=student_lrn, adviser_id=teacher.teacher_id)

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()

    section = Section.objects.filter(section_id=student.section_id).first()

    subject_rows = _build_subject_rows(student_lrn, grade_level=section.grade_level if section else None)
    all_finals_ready = _gate_finals_pending_term3(subject_rows)
    core_rows, elective_rows = _split_core_elective(subject_rows)

    finals = [row['final'] for row in subject_rows if row['final'] is not None]
    general_average = round(sum(finals) / len(finals), 2) if (all_finals_ready and finals) else None

    attendance_rows = _attendance_rows(student_lrn)
    attendance_by_month = {row['month']: row for row in attendance_rows}

    return render(request, 'reports/sf9.html', {
        'student': student,
        'school_profile': school_profile,
        'section': section,
        'age': _age_from_birthday(student.birthday),
        'core_rows': core_rows,
        'elective_rows': elective_rows,
        'general_average': general_average,
        'attendance_rows': attendance_rows,
        'attendance_by_month': attendance_by_month,
        'attendance_totals': _attendance_totals(attendance_rows),
        'attendance_months': ATTENDANCE_MONTHS,
        'teacher': teacher,
    })


@login_required
def view_sf10(request, student_lrn):
    try:
        teacher = _get_teacher(request)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    student = get_object_or_404(Student, lrn=student_lrn, adviser_id=teacher.teacher_id)

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()

    section = Section.objects.filter(section_id=student.section_id).first()

    grade_level_sections = []
    for grade_level in _grade_levels_for_student(student_lrn):
        subject_rows = _build_subject_rows(student_lrn, grade_level=grade_level)
        all_finals_ready = _gate_finals_pending_term3(subject_rows)
        finals = [row['final'] for row in subject_rows if row['final'] is not None]
        general_average = round(sum(finals) / len(finals), 2) if (all_finals_ready and finals) else None
        grade_level_sections.append({
            'grade_level': grade_level,
            'subject_rows': subject_rows,
            'general_average': general_average,
            'remarks': _remarks_for(general_average) if all_finals_ready else None,
        })

    return render(request, 'reports/sf10.html', {
        'student': student,
        'school_profile': school_profile,
        'section': section,
        'grade_level_sections': grade_level_sections,
        'attendance_rows': _attendance_rows(student_lrn),
    })
