import io

import openpyxl
from openpyxl.styles import Font, PatternFill

from collections import defaultdict

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa

from datetime import date

from accounts.forms import SectionForm, SchoolProfileForm, SchoolOfficialsForm
from accounts.models import Teacher, TeacherTimeRecord
from accounts.views import build_dtr_days
from students.models import SchoolProfile, Section, Student
from grades.models import Grade, SubjectMapping, TeacherSubjectAssignment, SchoolCalendarException, SubjectTestMaxScore
from grades.views import MONTH_NAMES, _score_stats
from .models import TeacherAccountAuditLog, SectionAuditLog


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


def _section_label(section):
    return f"Grade {section.grade_level}-{section.strand}-{section.section_name}"


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
def school_subject_statistics(request):
    """School-wide version of reports.subject_statistics_report: instead of
    one adviser's own section, this consolidates every section per grade
    level - Mean/Mode/Median/SD/MPS for Final Rating/Pre-Test/Final Exam,
    per subject, per term, aggregated across all sections in that grade."""
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    if not teacher.school_profile_id:
        messages.warning(request, 'Your account has no school assigned yet.')
        return render(request, 'school/subject_statistics.html', {'grade_level_rows': []})

    grade_levels = sorted(set(
        Section.objects.filter(school_profile_id=teacher.school_profile_id).values_list('grade_level', flat=True)
    ))

    grade_level_rows = []
    for grade_level in grade_levels:
        section_ids = list(Section.objects.filter(
            school_profile_id=teacher.school_profile_id, grade_level=grade_level
        ).values_list('section_id', flat=True))
        student_lrns = list(Student.objects.filter(section_id__in=section_ids).values_list('lrn', flat=True))

        subjects = SubjectMapping.objects.filter(
            school_profile_id=teacher.school_profile_id, grade_level=grade_level
        ).order_by('subject_name')

        # Multiple sections can teach the same subject under different
        # TeacherSubjectAssignment rows (one per section) - gather them all
        # per subject so a Pre-Test/Final Exam max score can still be found
        # once scores from every section are combined below.
        assignments_by_mapping = {}
        for a in TeacherSubjectAssignment.objects.filter(section_id__in=section_ids):
            assignments_by_mapping.setdefault(a.mapping_id, []).append(a)

        assignment_ids = [a.assignment_id for assignments in assignments_by_mapping.values() for a in assignments]
        max_scores = {
            (m.assignment_id, m.term): m
            for m in SubjectTestMaxScore.objects.filter(assignment_id__in=assignment_ids)
        }

        subject_scores = []
        for subject in subjects:
            grades = Grade.objects.filter(lrn__in=student_lrns, mapping_id=subject.mapping_id)
            final_by_term = {1: [], 2: [], 3: []}
            pretest_by_term = {1: [], 2: [], 3: []}
            final_exam_by_term = {1: [], 2: [], 3: []}
            for g in grades:
                if g.grade is not None:
                    final_by_term[g.term].append(g.grade)
                if g.pretest_score is not None:
                    pretest_by_term[g.term].append(g.pretest_score)
                if g.final_exam_score is not None:
                    final_exam_by_term[g.term].append(g.final_exam_score)

            subject_scores.append({
                'subject': subject,
                'assignments': assignments_by_mapping.get(subject.mapping_id, []),
                'final_by_term': final_by_term,
                'pretest_by_term': pretest_by_term,
                'final_exam_by_term': final_exam_by_term,
            })

        terms = []
        for term in (1, 2, 3):
            rows = []
            for entry in subject_scores:
                # Different sections' assignments can have different max
                # scores set - once their Pre-Test/Final Exam numbers are
                # combined there's no single "correct" denominator, so this
                # just uses the first one found for the term as a stand-in.
                max_score = None
                for a in entry['assignments']:
                    max_score = max_scores.get((a.assignment_id, term))
                    if max_score:
                        break
                rows.append({
                    'subject': entry['subject'],
                    'final_rating': _score_stats(entry['final_by_term'][term], 100),
                    'pretest': _score_stats(entry['pretest_by_term'][term], max_score.pretest_max if max_score else None),
                    'final_exam': _score_stats(entry['final_exam_by_term'][term], max_score.final_exam_max if max_score else None),
                })
            terms.append({'term': term, 'rows': rows})

        grade_level_rows.append({'grade_level': grade_level, 'terms': terms})

    return render(request, 'school/subject_statistics.html', {
        'grade_level_rows': grade_level_rows,
    })


@login_required
def school_dtr_upload(request):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    today = date.today()

    # Any employee's DTR could have been prepared by any registrar/principal
    # at this school, not just the one viewing this page - scope by the
    # whole school's Teacher ids so "already uploaded" reflects the school,
    # not just this account's own uploads.
    school_teacher_ids = Teacher.objects.filter(
        school_profile_id=teacher.school_profile_id
    ).values_list('teacher_id', flat=True)

    uploaded_months = (
        TeacherTimeRecord.objects.filter(teacher_id__in=school_teacher_ids)
        .annotate(month_start=TruncMonth('date'))
        .values('month_start')
        .annotate(record_count=Count('record_id'))
        .order_by('-month_start')
    )
    uploaded_month_rows = [
        {
            'label': f"{MONTH_NAMES[row['month_start'].month - 1]} {row['month_start'].year}",
            'record_count': row['record_count'],
            'year': row['month_start'].year,
            'month': row['month_start'].month,
        }
        for row in uploaded_months
    ]

    return render(request, 'school/dtr_upload.html', {
        'dtr_current_year': today.year,
        'dtr_current_month': today.month,
        'dtr_months': list(enumerate(MONTH_NAMES, start=1)),
        'uploaded_month_rows': uploaded_month_rows,
    })


@login_required
def download_dtr_upload_template(request):
    """Blank starter workbook matching the column shape upload_dtr's own
    parser (accounts/views.py's _dtr_parse_upload_bulk) prefers - Name +
    separate Arrival/Departure date+time columns, the actual shape of this
    school's DTR app export."""
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    headers = ['Name', 'Arrival Date', 'Arrival Time', 'Departure Date', 'Departure Time', 'Total']
    sample_row = ['Dela Cruz, Juan', '2026-07-01', '08:00 AM', '2026-07-01', '05:00 PM', '9:00']

    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = 'DTR Upload'

    sheet.append(headers)
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2F5496', end_color='2F5496', fill_type='solid')
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill

    sheet.append(sample_row)

    widths = [24, 14, 12, 14, 12, 10]
    for i, width in enumerate(widths, start=1):
        sheet.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="dtr_upload_template.xlsx"'
    wb.save(response)
    return response


@login_required
def download_dtr_pdf(request, year, month):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    school_teacher_ids = Teacher.objects.filter(
        school_profile_id=teacher.school_profile_id
    ).values_list('teacher_id', flat=True)

    records = TeacherTimeRecord.objects.filter(
        teacher_id__in=school_teacher_ids, date__year=year, date__month=month
    )
    employee_names = sorted(
        {r.employee_name for r in records if r.employee_name}, key=str.lower
    )
    if not employee_names:
        messages.error(request, f'No DTR data found for {MONTH_NAMES[month - 1]} {year}.')
        return redirect('school_dtr_upload')

    exceptions = {
        e.date: e.is_school_day
        for e in SchoolCalendarException.objects.filter(
            school_profile_id=teacher.school_profile_id, date__year=year, date__month=month
        )
    }

    records_by_employee = {}
    for r in records:
        records_by_employee.setdefault(r.employee_name, {})[r.date] = r

    forms = [
        {
            'employee_name': name,
            'days': build_dtr_days(year, month, exceptions, records_by_employee.get(name, {})),
        }
        for name in employee_names
    ]

    html = render_to_string('school/dtr_pdf.html', {
        'forms': forms,
        'month_name': MONTH_NAMES[month - 1],
        'year': year,
    })

    buffer = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer)
    if result.err:
        messages.error(request, 'Could not generate the PDF. Please try again.')
        return redirect('school_dtr_upload')

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    filename = f"DTR_{MONTH_NAMES[month - 1]}_{year}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def delete_dtr_month(request, year, month):
    if request.method != 'POST':
        return redirect('school_dtr_upload')

    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    school_teacher_ids = Teacher.objects.filter(
        school_profile_id=teacher.school_profile_id
    ).values_list('teacher_id', flat=True)

    deleted_count, _ = TeacherTimeRecord.objects.filter(
        teacher_id__in=school_teacher_ids, date__year=year, date__month=month
    ).delete()

    target_label = f"{MONTH_NAMES[month - 1]} {year}"
    if deleted_count:
        messages.success(request, f'Deleted {deleted_count} DTR record(s) for {target_label}.')
    else:
        messages.error(request, f'No DTR data found for {target_label}.')
    return redirect('school_dtr_upload')


@login_required
def school_student_list(request):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    query = request.GET.get('q', '').strip()
    student_rows = []

    if not teacher.school_profile_id:
        messages.warning(request, 'Your account has no school assigned yet.')
    elif query:
        sections_by_id = {
            s.section_id: s for s in Section.objects.filter(school_profile_id=teacher.school_profile_id)
        }
        students = Student.objects.filter(
            section_id__in=sections_by_id.keys()
        ).filter(
            Q(lrn__icontains=query) | Q(surname__icontains=query) | Q(name__icontains=query)
        ).order_by('surname', 'name')

        adviser_ids = {s.adviser_id for s in sections_by_id.values() if s.adviser_id}
        advisers_by_id = {t.teacher_id: t for t in Teacher.objects.filter(teacher_id__in=adviser_ids)}

        student_rows = []
        for s in students:
            section = sections_by_id.get(s.section_id)
            student_rows.append({
                'student': s,
                'section': section,
                'adviser': advisers_by_id.get(section.adviser_id) if section else None,
            })

    return render(request, 'school/students.html', {'query': query, 'student_rows': student_rows})


@login_required
def school_sections(request):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    if not teacher.school_profile_id:
        messages.warning(request, 'Your account has no school assigned yet.')
        return render(request, 'school/sections.html', {'section_rows': []})

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

    all_teachers = Teacher.objects.filter(
        school_profile_id=teacher.school_profile_id, role=Teacher.ROLE_ADVISER
    ).order_by('full_name')

    teachers_by_id = {t.teacher_id: t for t in Teacher.objects.filter(school_profile_id=teacher.school_profile_id)}
    audit_log = SectionAuditLog.objects.filter(school_profile_id=teacher.school_profile_id)[:50]
    audit_log_rows = [
        {'log': entry, 'performed_by': teachers_by_id.get(entry.performed_by)}
        for entry in audit_log
    ]

    return render(request, 'school/sections.html', {
        'section_rows': section_rows,
        'all_teachers': all_teachers,
        'audit_log_rows': audit_log_rows,
    })


@login_required
def school_section_students(request, section_id):
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    section = Section.objects.filter(
        section_id=section_id, school_profile_id=teacher.school_profile_id
    ).first()
    if not section:
        messages.error(request, 'Section not found.')
        return redirect('school_sections')

    adviser = Teacher.objects.filter(teacher_id=section.adviser_id).first() if section.adviser_id else None
    students = Student.objects.filter(section_id=section.section_id).order_by('surname', 'name')

    return render(request, 'school/section_students.html', {
        'section': section,
        'adviser': adviser,
        'students': students,
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
        SectionAuditLog.objects.create(
            school_profile_id=teacher.school_profile_id,
            section_label=_section_label(section),
            action=SectionAuditLog.ACTION_EDITED,
            detail='Adviser unassigned',
            performed_by=teacher.teacher_id,
        )
    else:
        adviser = Teacher.objects.filter(
            teacher_id=adviser_teacher_id, school_profile_id=teacher.school_profile_id
        ).first()
        if not adviser:
            messages.error(request, 'Teacher not found in this school.')
        else:
            _reassign_section_adviser(teacher.school_profile_id, section, adviser)
            messages.success(request, f'✅ {section.section_name} adviser reassigned to {adviser.full_name}.')
            SectionAuditLog.objects.create(
                school_profile_id=teacher.school_profile_id,
                section_label=_section_label(section),
                action=SectionAuditLog.ACTION_EDITED,
                detail=f'Adviser reassigned to {adviser.full_name}',
                performed_by=teacher.teacher_id,
            )

    return redirect('school_sections')


@login_required
def delete_section(request, section_id):
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

    # A section with students or subject-teaching assignments still pointing
    # at it can't be deleted - there's no cascading delete in this schema
    # (see CLAUDE.md), so removing it would silently orphan those rows.
    student_count = Student.objects.filter(section_id=section.section_id).count()
    assignment_count = TeacherSubjectAssignment.objects.filter(section_id=section.section_id).count()
    if student_count or assignment_count:
        messages.error(
            request,
            f'Cannot delete {section.section_name}: it still has {student_count} student(s) and '
            f'{assignment_count} subject-teaching assignment(s). Move or remove those first.'
        )
        return redirect('school_sections')

    label = _section_label(section)
    section.delete()

    SectionAuditLog.objects.create(
        school_profile_id=teacher.school_profile_id,
        section_label=label,
        action=SectionAuditLog.ACTION_DELETED,
        detail='',
        performed_by=teacher.teacher_id,
    )
    messages.success(request, f'✅ {label} deleted.')
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

    teachers_by_id = {t.teacher_id: t for t in teachers}
    audit_log = TeacherAccountAuditLog.objects.filter(
        target_teacher_id__in=teachers_by_id.keys()
    )[:50]
    audit_log_rows = [
        {
            'log': entry,
            'target': teachers_by_id.get(entry.target_teacher_id),
            'performed_by': teachers_by_id.get(entry.performed_by),
        }
        for entry in audit_log
    ]

    return render(request, 'school/accounts.html', {
        'account_rows': account_rows,
        'sections': sections,
        'audit_log_rows': audit_log_rows,
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
    TeacherAccountAuditLog.objects.create(
        target_teacher_id=target.teacher_id,
        action=status,
        performed_by=teacher.teacher_id,
    )
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
        strand_mismatch = section.strand and mapping.strand and mapping.strand != section.strand
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
def edit_my_section(request):
    teacher, section, error = _get_adviser_with_section(request)
    if error:
        return error

    school_profile = SchoolProfile.objects.filter(profile_id=section.school_profile_id).first()

    if request.method == 'POST':
        form = SectionForm(request.POST, instance=section, prefix='section')
        officials_form = SchoolOfficialsForm(
            request.POST, instance=school_profile, prefix='officials'
        ) if school_profile else None

        if form.is_valid() and (officials_form is None or officials_form.is_valid()):
            form.save()
            if officials_form:
                officials_form.save()
            messages.success(request, '✅ Classroom details updated.')
            return redirect('tools')
    else:
        form = SectionForm(instance=section, prefix='section')
        officials_form = SchoolOfficialsForm(
            instance=school_profile, prefix='officials'
        ) if school_profile else None

    return render(request, 'school/edit_my_section.html', {
        'section': section,
        'section_form': form,
        'officials_form': officials_form,
    })


@login_required
def edit_school_profile(request):
    """Registrar/principal-only edit of the school-wide profile (name,
    region/division/district/municipality, registrar/principal/SDS names) -
    the same SchoolProfileForm used to create one during profile setup,
    reused here for editing an existing one."""
    teacher, error = _get_school_admin_teacher(request)
    if error:
        return error

    school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()
    if not school_profile:
        messages.error(request, 'No school profile found. Please complete your profile first.')
        return redirect('complete_profile')

    if request.method == 'POST':
        form = SchoolProfileForm(request.POST, instance=school_profile)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ School data updated.')
            return redirect('tools')
    else:
        form = SchoolProfileForm(instance=school_profile)

    return render(request, 'school/edit_school_profile.html', {
        'school_profile': school_profile,
        'school_profile_form': form,
    })


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
        strand_mismatch = section.strand and mapping.strand and mapping.strand != section.strand
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

    # A blank mapping.strand applies to every strand at that grade level, and
    # a blank section.strand (no strand distinction for this section at all)
    # matches every mapping regardless of its strand.
    mappings = SubjectMapping.objects.filter(
        school_profile_id=teacher.school_profile_id,
        grade_level=section.grade_level,
        is_active=True,
    )
    if section.strand:
        mappings = mappings.filter(Q(strand='') | Q(strand=section.strand))
    mappings = mappings.order_by('subject_name')

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
