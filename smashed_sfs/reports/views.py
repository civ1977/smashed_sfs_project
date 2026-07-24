from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
import openpyxl

from accounts.models import Teacher
from students.models import Student, SchoolProfile, Section
from grades.models import Grade, SubjectMapping, Attendance
from .excel_utils import merge_and_write, write_table_header, write_table_row, excel_response


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
    subject grade_level (for SF10, which spans grade 11 and grade 12) and/or
    one term (for a single-quarter SF9 export)."""
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
    return [
        {'term': term, 'attendance': Attendance.objects.filter(lrn=lrn, term=term).first()}
        for term in (1, 2, 3)
    ]


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

    subject_rows = _build_subject_rows(student_lrn)

    finals = [row['final'] for row in subject_rows if row['final'] is not None]
    general_average = round(sum(finals) / len(finals), 2) if finals else None

    return render(request, 'reports/sf9.html', {
        'student': student,
        'school_profile': school_profile,
        'subject_rows': subject_rows,
        'general_average': general_average,
        'attendance_rows': _attendance_rows(student_lrn),
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
        finals = [row['final'] for row in subject_rows if row['final'] is not None]
        general_average = round(sum(finals) / len(finals), 2) if finals else None
        grade_level_sections.append({
            'grade_level': grade_level,
            'subject_rows': subject_rows,
            'general_average': general_average,
            'remarks': _remarks_for(general_average),
        })

    return render(request, 'reports/sf10.html', {
        'student': student,
        'school_profile': school_profile,
        'section': section,
        'grade_level_sections': grade_level_sections,
        'attendance_rows': _attendance_rows(student_lrn),
    })


@login_required
def generate_sf9_excel(request, student_lrn, term):
    try:
        teacher = _get_teacher(request)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    student = get_object_or_404(Student, lrn=student_lrn, adviser_id=teacher.teacher_id)

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()

    subject_rows = _build_subject_rows(student_lrn, term=term)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f'SF9 Term {term}'
    for col, width in zip('ABC', (32, 14, 14)):
        ws.column_dimensions[col].width = width

    row = 1
    if school_profile:
        merge_and_write(ws, row, 1, 3, school_profile.school_name, bold=True, size=14)
        row += 1
        merge_and_write(ws, row, 1, 3, f'{school_profile.municipality}, {school_profile.division}, {school_profile.region}')
        row += 1
        merge_and_write(ws, row, 1, 3, f'School ID: {school_profile.school_id} | School Year: {school_profile.school_year}')
        row += 1
    row += 1

    merge_and_write(ws, row, 1, 3, 'Learner\'s Progress Report Card (SF9)', bold=True, size=12)
    row += 1
    merge_and_write(ws, row, 1, 3, f'Term {term}', bold=True)
    row += 2

    ws.cell(row=row, column=1, value=f"Name: {student.surname}, {student.name} {student.middle_name or ''}".strip())
    row += 1
    ws.cell(row=row, column=1, value=f'LRN: {student.lrn}')
    row += 1
    ws.cell(row=row, column=1, value=f'Sex: {student.sex}')
    row += 1
    ws.cell(row=row, column=1, value=f'Birthday: {student.birthday}')
    row += 2

    write_table_header(ws, row, 1, ['Subject', f'Term {term} Grade', 'Remarks'])
    row += 1
    for subject_row in subject_rows:
        grade_value = subject_row[f'term_{term}']
        write_table_row(ws, row, 1, [
            subject_row['subject_name'],
            grade_value if grade_value is not None else '—',
            'Passed' if grade_value is not None and grade_value >= 75 else ('Failed' if grade_value is not None else '—'),
        ])
        row += 1

    row += 2
    if school_profile:
        ws.cell(row=row, column=1, value=f'Registrar: {school_profile.registrar_name}')
        row += 1
        ws.cell(row=row, column=1, value=f'Principal: {school_profile.principal_name}')

    filename = f'SF9_{student_lrn}_Term{term}.xlsx'
    return excel_response(wb, filename)


@login_required
def generate_sf10_excel(request, student_lrn):
    try:
        teacher = _get_teacher(request)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    student = get_object_or_404(Student, lrn=student_lrn, adviser_id=teacher.teacher_id)

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()

    wb = openpyxl.Workbook()
    first_sheet = True

    for grade_level in _grade_levels_for_student(student_lrn):
        subject_rows = _build_subject_rows(student_lrn, grade_level=grade_level)
        finals = [row['final'] for row in subject_rows if row['final'] is not None]
        general_average = round(sum(finals) / len(finals), 2) if finals else None

        if first_sheet:
            ws = wb.active
            ws.title = f'Grade {grade_level}'
            first_sheet = False
        else:
            ws = wb.create_sheet(title=f'Grade {grade_level}')

        for col, width in zip('ABCDEF', (32, 10, 10, 10, 12, 12)):
            ws.column_dimensions[col].width = width

        row = 1
        if school_profile:
            merge_and_write(ws, row, 1, 6, school_profile.school_name, bold=True, size=14)
            row += 1
            merge_and_write(ws, row, 1, 6, f'School ID: {school_profile.school_id} | School Year: {school_profile.school_year}')
            row += 2

        merge_and_write(ws, row, 1, 6, 'Learner\'s Permanent Academic Record (SF10)', bold=True, size=12)
        row += 1
        merge_and_write(ws, row, 1, 6, f'{student.surname}, {student.name} {student.middle_name or ""} | LRN: {student.lrn}'.strip())
        row += 1
        merge_and_write(ws, row, 1, 6, f'Grade Level: {grade_level}', bold=True)
        row += 2

        write_table_header(ws, row, 1, ['Subject', 'Term 1', 'Term 2', 'Term 3', 'Final', 'Remarks'])
        row += 1
        for subject_row in subject_rows:
            write_table_row(ws, row, 1, [
                subject_row['subject_name'],
                subject_row['term_1'] if subject_row['term_1'] is not None else '—',
                subject_row['term_2'] if subject_row['term_2'] is not None else '—',
                subject_row['term_3'] if subject_row['term_3'] is not None else '—',
                subject_row['final'] if subject_row['final'] is not None else '—',
                subject_row['remarks'] or '—',
            ])
            row += 1

        row += 1
        merge_and_write(ws, row, 1, 6, f'General Average: {general_average if general_average is not None else "—"}', bold=True)

    if first_sheet:
        # No grades on record at all — still produce a valid, mostly-empty workbook.
        ws = wb.active
        ws.title = 'SF10'
        ws.cell(row=1, column=1, value=f'No grades on record for {student.surname}, {student.name} ({student.lrn}).')

    filename = f'SF10_{student_lrn}.xlsx'
    return excel_response(wb, filename)
