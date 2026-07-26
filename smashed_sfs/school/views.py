from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from accounts.models import Teacher
from students.models import SchoolProfile, Section, Student


@login_required
def school_dashboard(request):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('login')

    if teacher.role == Teacher.ROLE_ADVISER:
        messages.error(request, 'This page is only available to registrar/principal accounts.')
        return redirect('dashboard')

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()

    return render(request, 'school/dashboard.html', {
        'teacher': teacher,
        'school_profile': school_profile,
    })


@login_required
def school_student_list(request):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile.')
        return redirect('login')

    if teacher.role == Teacher.ROLE_ADVISER:
        messages.error(request, 'This page is only available to registrar/principal accounts.')
        return redirect('dashboard')

    students = []
    if teacher.school_profile_id:
        section_ids = Section.objects.filter(
            school_profile_id=teacher.school_profile_id
        ).values_list('section_id', flat=True)
        students = Student.objects.filter(section_id__in=section_ids).order_by('surname', 'name')
    else:
        messages.warning(request, 'Your account has no school assigned yet.')

    return render(request, 'school/students.html', {'students': students})
