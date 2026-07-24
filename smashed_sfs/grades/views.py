from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
import csv
import io
from datetime import datetime
from students.models import Student
from accounts.models import Teacher
from .models import Grade, SubjectMapping


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
    headers = None
    
    if request.method == 'POST' and 'csv_file' in request.FILES:
        csv_file = request.FILES['csv_file']
        term = request.POST.get('term')
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
            request.session['grade_replace_all'] = replace_all
            request.session['grade_headers'] = headers
            
            messages.info(request, f'📋 Preview loaded: {len(preview_data)} students found for Term {term}.')
            
        except Exception as e:
            messages.error(request, f'Error reading CSV: {str(e)}')
    
    if 'grade_preview_data' in request.session and not preview_data:
        preview_data = request.session.get('grade_preview_data')
        term = request.session.get('grade_term')
        headers = request.session.get('grade_headers')
    
    terms = [
        {'value': 1, 'label': 'Term 1'},
        {'value': 2, 'label': 'Term 2'},
        {'value': 3, 'label': 'Term 3'},
    ]
    
    return render(request, 'grades/upload.html', {
        'preview_data': preview_data,
        'term': term,
        'terms': terms,
        'headers': headers,
    })


@login_required
def save_grades(request):
    if request.method == 'POST':
        row_count = int(request.POST.get('row_count', 0))
        term = int(request.POST.get('term', 1))
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
                    grade_level='11',
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
                        grade_level='11',
                        strand='STEM',
                        subject_number=i
                    )
                    subject_mappings[i] = mapping.mapping_id
                except SubjectMapping.DoesNotExist:
                    pass
        
        # Delete existing grades for this term if replace_all
        if replace_all:
            students = Student.objects.filter(adviser_id=teacher.teacher_id)
            for student in students:
                Grade.objects.filter(lrn=student.lrn, term=term).delete()
            messages.info(request, f'🗑️ Existing Term {term} grades deleted.')
        
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
        
        subjects = SubjectMapping.objects.filter(
            school_profile_id=teacher.school_profile_id
        ).order_by('subject_number')
        
        grades_data = {}
        for student in students:
            grades = Grade.objects.filter(lrn=student.lrn)
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
        grades = Grade.objects.filter(lrn=lrn).order_by('term', 'mapping_id')
        
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