from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction

from students.models import Student
from grades.views import build_student_grade_sheet
from .models import StudentAccount


def portal_register(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        lrn = request.POST.get('lrn', '').strip()

        if password != password_confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'portal/register.html')

        if not password or len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'portal/register.html')

        if not username:
            messages.error(request, 'Username is required.')
            return render(request, 'portal/register.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'portal/register.html')

        if not Student.objects.filter(lrn=lrn).exists():
            messages.error(request, 'That LRN was not found. Please check with your adviser and try again.')
            return render(request, 'portal/register.html')

        if StudentAccount.objects.filter(lrn=lrn).exclude(status=StudentAccount.STATUS_REJECTED).exists():
            messages.error(request, 'An account request for this LRN already exists.')
            return render(request, 'portal/register.html')

        with transaction.atomic():
            user = User.objects.create_user(username=username, password=password)
            StudentAccount.objects.create(user=user, lrn=lrn)

        return render(request, 'portal/register_submitted.html')

    return render(request, 'portal/register.html')


@login_required
def portal_pending(request):
    account = get_object_or_404(StudentAccount, user=request.user)

    if account.status == StudentAccount.STATUS_APPROVED:
        return redirect('portal_dashboard')

    return render(request, 'portal/pending.html', {'account': account})


@login_required
def portal_dashboard(request):
    account = StudentAccount.objects.filter(user=request.user, status=StudentAccount.STATUS_APPROVED).first()
    if not account:
        return redirect('portal_pending')

    student = Student.objects.filter(lrn=account.lrn).first()

    return render(request, 'portal/dashboard.html', {
        'account': account,
        'student': student,
    })


@login_required
def portal_grades(request):
    account = StudentAccount.objects.filter(user=request.user, status=StudentAccount.STATUS_APPROVED).first()
    if not account:
        return redirect('portal_pending')

    student = get_object_or_404(Student, lrn=account.lrn)
    subject_grades, subject_names, general_average, grades = build_student_grade_sheet(account.lrn)

    return render(request, 'portal/grades.html', {
        'student': student,
        'subject_grades': subject_grades,
        'subject_names': subject_names,
        'general_average': general_average,
        'grades': grades,
    })
