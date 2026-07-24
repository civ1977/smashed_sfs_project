from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse

from accounts.models import Teacher
from students.models import Student, SchoolProfile
from grades.models import Grade, SubjectMapping, Attendance


@login_required
def select_student_for_report(request):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    students = Student.objects.filter(adviser_id=teacher.teacher_id).order_by('surname', 'name')

    return render(request, 'reports/select_student.html', {'students': students})


@login_required
def view_sf9(request, student_lrn):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('dashboard')

    student = get_object_or_404(Student, lrn=student_lrn, adviser_id=teacher.teacher_id)

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()

    grades = Grade.objects.filter(lrn=student_lrn)

    grades_by_subject = {}
    for grade in grades:
        grades_by_subject.setdefault(grade.mapping_id, {1: None, 2: None, 3: None})[grade.term] = grade.grade

    subject_rows = []
    for mapping_id, terms in grades_by_subject.items():
        try:
            subject_name = SubjectMapping.objects.get(mapping_id=mapping_id).subject_name
        except SubjectMapping.DoesNotExist:
            subject_name = f'Subject {mapping_id}'

        term_grades = [terms[1], terms[2], terms[3]]
        valid_grades = [g for g in term_grades if g is not None]
        final = round(sum(valid_grades) / len(valid_grades)) if valid_grades else None

        subject_rows.append({
            'subject_name': subject_name,
            'term_1': terms[1],
            'term_2': terms[2],
            'term_3': terms[3],
            'final': final,
            'remarks': None if final is None else ('Passed' if final >= 75 else 'Failed'),
        })
    subject_rows.sort(key=lambda row: row['subject_name'])

    finals = [row['final'] for row in subject_rows if row['final'] is not None]
    general_average = round(sum(finals) / len(finals), 2) if finals else None

    attendance_rows = [
        {'term': term, 'attendance': Attendance.objects.filter(lrn=student_lrn, term=term).first()}
        for term in (1, 2, 3)
    ]

    return render(request, 'reports/sf9.html', {
        'student': student,
        'school_profile': school_profile,
        'subject_rows': subject_rows,
        'general_average': general_average,
        'attendance_rows': attendance_rows,
    })


@login_required
def view_sf10(request, student_lrn):
    return HttpResponse('SF10 is not implemented yet.', status=501)


@login_required
def generate_sf9_excel(request, student_lrn, term):
    return HttpResponse('SF9 Excel export is not implemented yet.', status=501)


@login_required
def generate_sf10_excel(request, student_lrn):
    return HttpResponse('SF10 Excel export is not implemented yet.', status=501)
