from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
import csv
import io
from datetime import datetime
from students.models import Student, Section
from accounts.models import Teacher
from .models import Grade, SubjectMapping, Attendance, ATTENDANCE_MONTHS

GRADE_TERMS = [
    {'value': 1, 'label': 'Term 1'},
    {'value': 2, 'label': 'Term 2'},
    {'value': 3, 'label': 'Term 3'},
]

ATTENDANCE_MONTH_OPTIONS = [{'value': m, 'label': m} for m in ATTENDANCE_MONTHS]

GRADE_LEVELS = [
    {'value': '11', 'label': 'Grade 11'},
    {'value': '12', 'label': 'Grade 12'},
]


def convert_date(date_str):
    """Convert various date formats to YYYY-MM-DD"""
    if not date_str or date_str.strip() == '':
        return None
    
    date_str = date_str.strip()
    
    formats = [
        '%b %d, %Y',
        '%B %d, %Y',
        '%m/%d/%Y',
        '%m-%d-%Y',
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%d-%b-%Y',
        '%d %b %Y',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    return date_str


@login_required
def upload_grades(request):
    preview_data = None
    term = request.POST.get('term') if request.method == 'POST' else None
    grade_level = request.POST.get('grade_level') if request.method == 'POST' else None
    headers = None

    if request.method == 'POST' and 'csv_file' in request.FILES:
        csv_file = request.FILES['csv_file']
        term = request.POST.get('term')
        grade_level = request.POST.get('grade_level')
        skip_header = request.POST.get('skip_header') == 'on'
        replace_all = request.POST.get('replace_all') == 'on'

        try:
            decoded_file = csv_file.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.reader(io_string, delimiter=',', quotechar='"')
            
            preview_data = []
            headers = None
            
            if skip_header:
                try:
                    headers = next(reader)
                    headers = [h.strip() if h else f'Subject{i+1}' for i, h in enumerate(headers)]
                except StopIteration:
                    pass
            
            for row in reader:
                if row:
                    if headers and len(row) < len(headers):
                        row.extend([''] * (len(headers) - len(row)))
                    preview_data.append(row)
            
            if not headers and preview_data:
                headers = ['LRN'] + [f'Subject{i+1}' for i in range(len(preview_data[0]) - 1)]
            
            request.session['grade_preview_data'] = preview_data
            request.session['grade_term'] = term
            request.session['grade_level'] = grade_level
            request.session['grade_replace_all'] = replace_all
            request.session['grade_headers'] = headers

            messages.info(request, f'📋 Preview loaded: {len(preview_data)} students found for Term {term}.')

        except Exception as e:
            messages.error(request, f'Error reading CSV: {str(e)}')

    if 'grade_preview_data' in request.session and not preview_data:
        preview_data = request.session.get('grade_preview_data')
        term = request.session.get('grade_term')
        grade_level = request.session.get('grade_level')
        headers = request.session.get('grade_headers')

    return render(request, 'grades/upload.html', {
        'preview_data': preview_data,
        'term': term,
        'terms': GRADE_TERMS,
        'grade_level': grade_level or '11',
        'grade_levels': GRADE_LEVELS,
        'headers': headers,
    })


@login_required
def save_grades(request):
    if request.method == 'POST':
        row_count = int(request.POST.get('row_count', 0))
        term = int(request.POST.get('term', 1))
        grade_level = request.POST.get('grade_level') or '11'
        replace_all = request.POST.get('replace_all') == 'on'
        update_subjects = request.POST.get('update_subjects') == 'on'
        
        saved_count = 0
        error_count = 0
        errors = []
        
        # Get teacher
        try:
            teacher = Teacher.objects.get(username=request.user.username)
        except Teacher.DoesNotExist:
            messages.error(request, 'Your account is not linked to a Teacher profile.')
            return redirect('upload_grades')
        
        if not teacher.school_profile_id:
            messages.error(request, 'Your profile is missing a school. Please complete your profile first.')
            return redirect('complete_profile')
        
        # Get subject mapping
        subject_mappings = {}
        for i in range(1, 31):
            subject_name = request.POST.get(f'subject_name_{i}')
            if subject_name and update_subjects:
                mapping, created = SubjectMapping.objects.get_or_create(
                    school_profile_id=teacher.school_profile_id,
                    grade_level=grade_level,
                    strand='STEM',
                    subject_number=i,
                    defaults={
                        'subject_name': subject_name,
                        'created_by': teacher.teacher_id
                    }
                )
                if not created and mapping.subject_name != subject_name:
                    mapping.subject_name = subject_name
                    mapping.save()
                subject_mappings[i] = mapping.mapping_id
            else:
                try:
                    mapping = SubjectMapping.objects.get(
                        school_profile_id=teacher.school_profile_id,
                        grade_level=grade_level,
                        strand='STEM',
                        subject_number=i
                    )
                    subject_mappings[i] = mapping.mapping_id
                except SubjectMapping.DoesNotExist:
                    pass
        
        # Delete existing grades for this term if replace_all - scoped to this
        # grade level's mappings only, so a Grade 12 replace doesn't wipe a
        # student's Grade 11 history for the same term number.
        if replace_all:
            grade_level_mapping_ids = set(subject_mappings.values())
            students = Student.objects.filter(adviser_id=teacher.teacher_id)
            for student in students:
                Grade.objects.filter(
                    lrn=student.lrn,
                    term=term,
                    mapping_id__in=grade_level_mapping_ids
                ).delete()
            messages.info(request, f'🗑️ Existing Grade {grade_level} Term {term} grades deleted.')
        
        for i in range(row_count):
            try:
                lrn = request.POST.get(f'lrn_{i}', '').strip()
                if not lrn:
                    continue
                
                try:
                    student = Student.objects.get(lrn=lrn, adviser_id=teacher.teacher_id)
                except Student.DoesNotExist:
                    messages.warning(request, f'Student {lrn} not found. Skipping.')
                    continue
                
                for subject_num in range(1, 31):
                    grade_value = request.POST.get(f'grade_{i}_{subject_num}', '').strip()
                    if grade_value:
                        try:
                            grade = int(grade_value)
                            if grade < 60 or grade > 100:
                                messages.warning(request, f'Grade {grade} for {lrn} is outside 60-100 range.')
                                continue
                            
                            mapping_id = subject_mappings.get(subject_num)
                            if mapping_id:
                                existing = Grade.objects.filter(
                                    lrn=lrn,
                                    mapping_id=mapping_id,
                                    term=term
                                ).first()
                                
                                if existing:
                                    existing.grade = grade
                                    existing.save()
                                else:
                                    Grade.objects.create(
                                        lrn=lrn,
                                        mapping_id=mapping_id,
                                        term=term,
                                        grade=grade,
                                        uploaded_by=teacher.teacher_id
                                    )
                                saved_count += 1
                        except ValueError:
                            messages.warning(request, f'Invalid grade value for {lrn}: {grade_value}')
                
            except Exception as e:
                error_count += 1
                errors.append(f'Error saving grades for row {i+1}: {str(e)}')
                messages.error(request, f'Error saving grades for row {i+1}: {str(e)}')
        
        request.session.pop('grade_preview_data', None)
        request.session.pop('grade_term', None)
        request.session.pop('grade_level', None)
        request.session.pop('grade_headers', None)

        if saved_count > 0:
            messages.success(request, f'✅ {saved_count} grades saved successfully for Term {term}!')
        if error_count > 0:
            messages.warning(request, f'⚠️ {error_count} students had errors.')
        
        return redirect('view_grades', lrn='all')
    
    return redirect('upload_grades')


@login_required
def view_grades(request, lrn):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')
    
    if lrn == 'all':
        students = Student.objects.filter(adviser_id=teacher.teacher_id).order_by('surname', 'name')

        # Scope the subject list to this teacher's own grade level so Grade
        # 11 and Grade 12 mappings (which share a school_profile_id) don't
        # get mixed into the same gradesheet.
        teacher_section = Section.objects.filter(adviser_id=teacher.teacher_id).first()
        subjects = SubjectMapping.objects.filter(school_profile_id=teacher.school_profile_id)
        if teacher_section:
            subjects = subjects.filter(grade_level=teacher_section.grade_level)
        subjects = subjects.order_by('subject_number')
        subject_ids = set(subjects.values_list('mapping_id', flat=True))

        grades_data = {}
        for student in students:
            grades = Grade.objects.filter(lrn=student.lrn, mapping_id__in=subject_ids)
            subject_grades = {}
            for grade in grades:
                if grade.mapping_id not in subject_grades:
                    subject_grades[grade.mapping_id] = {1: None, 2: None, 3: None}
                subject_grades[grade.mapping_id][grade.term] = grade.grade
            grades_data[student.lrn] = subject_grades

        return render(request, 'grades/list.html', {
            'students': students,
            'grades_data': grades_data,
            'subjects': subjects,
            'teacher': teacher,
        })
    else:
        student = get_object_or_404(Student, lrn=lrn, adviser_id=teacher.teacher_id)

        # Scope to the student's own current grade level, same reasoning as
        # the 'all' branch above.
        student_section = Section.objects.filter(section_id=student.section_id).first()
        grades = Grade.objects.filter(lrn=lrn).order_by('term', 'mapping_id')
        if student_section:
            grade_level_mapping_ids = set(SubjectMapping.objects.filter(
                school_profile_id=teacher.school_profile_id,
                grade_level=student_section.grade_level
            ).values_list('mapping_id', flat=True))
            grades = grades.filter(mapping_id__in=grade_level_mapping_ids)

        subject_grades = {}
        for grade in grades:
            if grade.mapping_id not in subject_grades:
                subject_grades[grade.mapping_id] = {1: None, 2: None, 3: None}
            subject_grades[grade.mapping_id][grade.term] = grade.grade
        
        for mapping_id in subject_grades:
            grades_list = [
                subject_grades[mapping_id][1],
                subject_grades[mapping_id][2],
                subject_grades[mapping_id][3]
            ]
            valid_grades = [g for g in grades_list if g is not None]
            subject_grades[mapping_id]['final'] = round(sum(valid_grades) / len(valid_grades)) if valid_grades else None
            subject_grades[mapping_id]['remarks'] = 'Passed' if subject_grades[mapping_id]['final'] and subject_grades[mapping_id]['final'] >= 75 else 'Failed'
        
        subject_names = {}
        for mapping_id in subject_grades.keys():
            try:
                subject = SubjectMapping.objects.get(mapping_id=mapping_id)
                subject_names[mapping_id] = subject.subject_name
            except SubjectMapping.DoesNotExist:
                subject_names[mapping_id] = f'Subject {mapping_id}'

        return render(request, 'grades/view.html', {
            'student': student,
            'subject_grades': subject_grades,
            'subject_names': subject_names,
            'grades': grades,
        })


@login_required
def download_attendance_template(request):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('upload_attendance')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="attendance_template.csv"'

    writer = csv.writer(response)
    writer.writerow(['LRN', 'Days Present', 'Days Absent'])

    students = Student.objects.filter(adviser_id=teacher.teacher_id).order_by('surname', 'name')
    for student in students:
        writer.writerow([student.lrn, '', ''])

    return response


@login_required
def upload_attendance(request):
    preview_data = None
    month = request.POST.get('month') if request.method == 'POST' else None

    if request.method == 'POST' and 'csv_file' in request.FILES:
        csv_file = request.FILES['csv_file']
        month = request.POST.get('month')
        skip_header = request.POST.get('skip_header') == 'on'
        replace_all = request.POST.get('replace_all') == 'on'

        if month not in ATTENDANCE_MONTHS:
            messages.error(request, 'Please select a valid month.')
            return render(request, 'grades/attendance_upload.html', {
                'preview_data': None,
                'month': month,
                'months': ATTENDANCE_MONTH_OPTIONS,
            })

        try:
            decoded_file = csv_file.read().decode('utf-8-sig')
            io_string = io.StringIO(decoded_file)
            reader = csv.reader(io_string, delimiter=',', quotechar='"')

            preview_data = []

            if skip_header:
                next(reader, None)

            for row in reader:
                if row:
                    preview_data.append(row)

            request.session['attendance_preview_data'] = preview_data
            request.session['attendance_month'] = month
            request.session['attendance_replace_all'] = replace_all

            messages.info(request, f'📋 Preview loaded: {len(preview_data)} students found for {month}.')

        except Exception as e:
            messages.error(request, f'Error reading CSV: {str(e)}')

    if 'attendance_preview_data' in request.session and not preview_data:
        preview_data = request.session.get('attendance_preview_data')
        month = request.session.get('attendance_month')

    return render(request, 'grades/attendance_upload.html', {
        'preview_data': preview_data,
        'month': month,
        'months': ATTENDANCE_MONTH_OPTIONS,
    })


@login_required
def save_attendance(request):
    if request.method == 'POST':
        row_count = int(request.POST.get('row_count', 0))
        month = request.POST.get('month', '')
        replace_all = request.POST.get('replace_all') == 'on'

        saved_count = 0
        error_count = 0

        try:
            teacher = Teacher.objects.get(username=request.user.username)
        except Teacher.DoesNotExist:
            messages.error(request, 'Your account is not linked to a Teacher profile.')
            return redirect('upload_attendance')

        if month not in ATTENDANCE_MONTHS:
            messages.error(request, 'Please select a valid month.')
            return redirect('upload_attendance')

        # Delete existing attendance for this month if replace_all
        if replace_all:
            students = Student.objects.filter(adviser_id=teacher.teacher_id)
            for student in students:
                Attendance.objects.filter(lrn=student.lrn, month=month).delete()
            messages.info(request, f'🗑️ Existing {month} attendance deleted.')

        for i in range(row_count):
            try:
                lrn = request.POST.get(f'lrn_{i}', '').strip()
                if not lrn:
                    continue

                try:
                    student = Student.objects.get(lrn=lrn, adviser_id=teacher.teacher_id)
                except Student.DoesNotExist:
                    messages.warning(request, f'Student {lrn} not found. Skipping.')
                    continue

                days_present_str = request.POST.get(f'days_present_{i}', '').strip()
                days_absent_str = request.POST.get(f'days_absent_{i}', '').strip()

                try:
                    days_present = int(days_present_str) if days_present_str else 0
                    days_absent = int(days_absent_str) if days_absent_str else 0
                except ValueError:
                    messages.warning(request, f'Invalid attendance value for {lrn}. Skipping.')
                    continue

                if days_present < 0 or days_absent < 0:
                    messages.warning(request, f'Attendance for {lrn} cannot be negative. Skipping.')
                    continue

                existing = Attendance.objects.filter(lrn=lrn, month=month).first()
                if existing:
                    existing.days_present = days_present
                    existing.days_absent = days_absent
                    existing.save()
                else:
                    Attendance.objects.create(
                        lrn=lrn,
                        month=month,
                        days_present=days_present,
                        days_absent=days_absent,
                        uploaded_by=teacher.teacher_id
                    )
                saved_count += 1

            except Exception as e:
                error_count += 1
                messages.error(request, f'Error saving attendance for row {i+1}: {str(e)}')

        request.session.pop('attendance_preview_data', None)
        request.session.pop('attendance_month', None)
        request.session.pop('attendance_replace_all', None)

        if saved_count > 0:
            messages.success(request, f'✅ {saved_count} attendance records saved for {month}!')
        if error_count > 0:
            messages.warning(request, f'⚠️ {error_count} rows had errors.')

        return redirect('view_attendance', lrn='all')

    return redirect('upload_attendance')


@login_required
def view_attendance(request, lrn):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    if lrn == 'all':
        students = Student.objects.filter(adviser_id=teacher.teacher_id).order_by('surname', 'name')

        attendance_data = {}
        for student in students:
            records = Attendance.objects.filter(lrn=student.lrn)
            month_attendance = {m: None for m in ATTENDANCE_MONTHS}
            for record in records:
                month_attendance[record.month] = record
            attendance_data[student.lrn] = month_attendance

        return render(request, 'grades/attendance_list.html', {
            'students': students,
            'attendance_data': attendance_data,
            'months': ATTENDANCE_MONTH_OPTIONS,
        })
    else:
        student = get_object_or_404(Student, lrn=lrn, adviser_id=teacher.teacher_id)
        records = Attendance.objects.filter(lrn=lrn)

        month_attendance = {m: None for m in ATTENDANCE_MONTHS}
        for record in records:
            month_attendance[record.month] = record

        return render(request, 'grades/attendance_view.html', {
            'student': student,
            'month_attendance': month_attendance,
            'months': ATTENDANCE_MONTH_OPTIONS,
        })