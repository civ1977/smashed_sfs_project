from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction

from students.models import Student
from grades.views import build_student_grade_sheet
from .models import StudentAccount


def _reject_if_inactive(request):
    """Belt-and-suspenders: ModelBackend.get_user() already re-checks
    is_active on every request and downgrades the session to AnonymousUser
    the moment an account is deactivated, so @login_required alone already
    bounces a stale session to the login page (verified via Client tests).
    This just adds a clear message instead of a bare unexplained redirect,
    and stays correct if the auth backend ever changes. Returns a redirect
    if blocked, else None."""
    if not request.user.is_active:
        logout(request)
        messages.error(request, 'Your account has been deactivated. Please contact your school registrar.')
        return redirect('login')
    return None


def portal_register(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        lrn = request.POST.get('lrn', '').strip()

        if not email:
            messages.error(request, 'Email is required.')
            return render(request, 'portal/register.html')

        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, 'Enter a valid email address.')
            return render(request, 'portal/register.html')

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
            user = User.objects.create_user(username=username, password=password, email=email)
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
    blocked = _reject_if_inactive(request)
    if blocked:
        return blocked

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
    blocked = _reject_if_inactive(request)
    if blocked:
        return blocked

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
