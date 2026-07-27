from datetime import date
from pathlib import Path

import openpyxl
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse

from accounts.models import Teacher
from students.models import Student, SchoolProfile, Section
from grades.models import Grade, SubjectMapping, Attendance, ATTENDANCE_MONTHS, AttendanceMark
from grades.views import MONTH_NAMES, _school_days_in_month


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


# =====================================================================
# SF2 (Daily Attendance Report) Excel export
#
# SF2.xlsx (reports/xlsx_templates/SF2.xlsx) is used purely as a layout
# template - it was exported out of DepEd's LIS and most of its formulas
# are broken external-workbook links (`[1]INPUT_Homeroom_Data!...` etc.)
# that reference a file we don't have. Every cell we touch below is
# overwritten with a real, static value computed from this app's own data;
# none of the template's own formulas for these fields are read or kept.
# =====================================================================

SF2_TEMPLATE_PATH = Path(__file__).resolve().parent / 'xlsx_templates' / 'SF2.xlsx'

# The 30 day-slot columns (5 weeks x Mon-Sat), left to right, as laid out in
# the template's row 17/18 header and each student row's mark cells. Only
# the top-left cell of each (possibly merged) day-slot is listed here - that
# is the one real, writable cell per slot.
DAY_COLUMNS = [
    'K', 'M', 'N', 'O', 'S', 'V',
    'W', 'Z', 'AA', 'AB', 'AE', 'AH',
    'AI', 'AL', 'AN', 'AP', 'AR', 'AS',
    'AU', 'AV', 'AW', 'AY', 'BB', 'BD',
    'BE', 'BI', 'BJ', 'BK', 'BM', 'BO',
]
MAX_DAY_SLOTS = len(DAY_COLUMNS)  # 30
MAX_STUDENTS_PER_GENDER = 55
MALE_ROW_START = 19    # rows 19-73
FEMALE_ROW_START = 75  # rows 75-129

# date.weekday(): Monday=0 ... Sunday=6. Normally only Mon-Sat show up here
# (Sundays are never school days by default), but a SchoolCalendarException
# can mark any date - including a Sunday - as a school day, so all 7 are covered.
WEEKDAY_ABBR = ['M', 'T', 'W', 'TH', 'F', 'S', 'SU']

# Blank = Present (never written). "L"/"C" are plain-letter stand-ins for
# the template's original diagonal half-shaded Late-Comer/Cutting-Classes
# cell styling - the one intentional visual deviation from the source file.
MARK_SYMBOL = {
    AttendanceMark.STATUS_ABSENT: 'x',
    AttendanceMark.STATUS_LATE_COMER: 'L',
    AttendanceMark.STATUS_CUTTING_CLASSES: 'C',
}

# This app has no explicit semester field (grades use Term 1/2/3, not
# semesters), so the semester shown on SF2 is inferred from where the month
# falls in ATTENDANCE_MONTHS (Jun-Oct / Nov-Apr split).
FIRST_SEMESTER_MONTHS = {6, 7, 8, 9, 10}


def _semester_for_month(month):
    return 'First Semester' if month in FIRST_SEMESTER_MONTHS else 'Second Semester'


def _sf2_student_name(student):
    parts = [f'{student.surname.strip()}, {student.name.strip()}']
    if student.middle_name:
        parts.append(student.middle_name.strip())
    return ' '.join(parts)


def _fill_sf2_header(ws, teacher, section, school_profile, year, month):
    ws['I5'] = school_profile.school_name if school_profile else ''
    ws['Y5'] = school_profile.school_id if school_profile else ''
    ws['AQ5'] = school_profile.district if school_profile else ''
    ws['BH5'] = school_profile.division if school_profile else ''
    ws['BY5'] = school_profile.region if school_profile else ''
    ws['U8'] = school_profile.school_year if school_profile else ''
    ws['I7'] = _semester_for_month(month)
    ws['AN8'] = f'Grade {section.grade_level}'
    ws['I12'] = section.section_name
    ws['BC7'] = '/'.join(part for part in (section.track, section.strand) if part)
    ws['BN11'] = MONTH_NAMES[month - 1].upper()
    ws['BR168'] = teacher.full_name
    ws['BR171'] = school_profile.principal_name if school_profile else ''


def _fill_sf2_gender_block(ws, students, row_start, school_days, warnings, gender_label):
    if len(students) > MAX_STUDENTS_PER_GENDER:
        warnings.append(
            f'{len(students)} {gender_label} students found, but SF2 only has room for '
            f'{MAX_STUDENTS_PER_GENDER}. Only the first {MAX_STUDENTS_PER_GENDER} are on this form.'
        )
        students = students[:MAX_STUDENTS_PER_GENDER]

    lrns = [s.lrn for s in students]
    marks_by_key = {
        f'{m.lrn}|{m.date.isoformat()}': m.status
        for m in AttendanceMark.objects.filter(lrn__in=lrns, date__in=school_days)
    }

    for i in range(MAX_STUDENTS_PER_GENDER):
        row = row_start + i
        if i >= len(students):
            ws[f'G{row}'] = ''
            ws[f'BS{row}'] = 0
            ws[f'BV{row}'] = 0
            continue

        student = students[i]
        ws[f'G{row}'] = _sf2_student_name(student)

        absent_count = 0
        for day_index, day in enumerate(school_days):
            status = marks_by_key.get(f'{student.lrn}|{day.isoformat()}', 'present')
            if status == AttendanceMark.STATUS_ABSENT:
                absent_count += 1
            ws[f'{DAY_COLUMNS[day_index]}{row}'] = MARK_SYMBOL.get(status, '')

        ws[f'BS{row}'] = absent_count
        ws[f'BV{row}'] = len(school_days) - absent_count


def _build_sf2_workbook(teacher, section, school_profile, year, month):
    """Returns (workbook, warnings). warnings is a list of human-readable
    strings for anything this export had to cap/truncate rather than
    silently drop."""
    wb = openpyxl.load_workbook(SF2_TEMPLATE_PATH)
    ws = wb['Sheet1']
    warnings = []

    # The template's own external-workbook link definitions (the source of
    # every broken [1]... formula) - drop them outright rather than just
    # overwriting the formulas that referenced them, so no dangling link
    # survives in the saved file for Excel to prompt about on open.
    wb._external_links = []

    school_days = _school_days_in_month(section.school_profile_id, year, month)
    if len(school_days) > MAX_DAY_SLOTS:
        warnings.append(
            f'{MONTH_NAMES[month - 1]} {year} has {len(school_days)} school days, but SF2 only '
            f'has room for {MAX_DAY_SLOTS}. Only the first {MAX_DAY_SLOTS} days are on this form.'
        )
        school_days = school_days[:MAX_DAY_SLOTS]

    _fill_sf2_header(ws, teacher, section, school_profile, year, month)
    ws['BZ134'] = len(school_days)

    for day_index, col in enumerate(DAY_COLUMNS):
        if day_index < len(school_days):
            ws[f'{col}17'] = school_days[day_index].day
            ws[f'{col}18'] = WEEKDAY_ABBR[school_days[day_index].weekday()]
        else:
            ws[f'{col}17'] = None
            ws[f'{col}18'] = None

    students = Student.objects.filter(adviser_id=teacher.teacher_id).order_by('surname', 'name')
    males = [s for s in students if s.sex in ('MALE', 'M')]
    females = [s for s in students if s.sex in ('FEMALE', 'F')]

    _fill_sf2_gender_block(ws, males, MALE_ROW_START, school_days, warnings, 'male')
    _fill_sf2_gender_block(ws, females, FEMALE_ROW_START, school_days, warnings, 'female')

    return wb, warnings


@login_required
def export_sf2(request, year, month):
    try:
        teacher = _get_teacher(request)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    section = Section.objects.filter(adviser_id=teacher.teacher_id).first()
    if not section:
        messages.error(request, 'Your profile is missing a section. Please complete your profile first.')
        return redirect('attendance_grid')

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()

    wb, warnings = _build_sf2_workbook(teacher, section, school_profile, year, month)
    for warning in warnings:
        messages.warning(request, warning)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f'SF2_{section.section_name}_{MONTH_NAMES[month - 1]}{year}.xlsx'.replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
