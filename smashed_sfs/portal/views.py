from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from students.models import Student, Section, SchoolProfile
from grades.views import build_student_grade_sheet
from school.models import EnrollmentApplication
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

        if request.POST.get('agree_terms') != 'on':
            messages.error(request, "Please check the box confirming you agree to the User's Agreement and Privacy Policy.")
            return render(request, 'portal/register.html')

        with transaction.atomic():
            user = User.objects.create_user(username=username, password=password, email=email)
            StudentAccount.objects.create(user=user, lrn=lrn, terms_accepted_at=timezone.now())

        return render(request, 'portal/register_submitted.html')

    return render(request, 'portal/register.html')


@login_required
def portal_pending(request):
    account = get_object_or_404(StudentAccount, user=request.user)

    if account.status == StudentAccount.STATUS_APPROVED:
        return redirect('portal_grades')

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


@login_required
def portal_enrollment_form(request):
    """Enrollment application form for an approved student. Doesn't touch
    Student/Section at all - the applicant's info is held directly on
    EnrollmentApplication (school/models.py) since a Student row requires a
    section/adviser an enrollee doesn't have yet; a registrar places them
    into an actual section separately, from the existing Sections/Students
    pages, once a decision is made."""
    blocked = _reject_if_inactive(request)
    if blocked:
        return blocked

    account = StudentAccount.objects.filter(user=request.user, status=StudentAccount.STATUS_APPROVED).first()
    if not account:
        return redirect('portal_pending')

    student = Student.objects.filter(lrn=account.lrn).first()

    school_profile_id = None
    if student:
        section = Section.objects.filter(section_id=student.section_id).first()
        if section:
            school_profile_id = section.school_profile_id
    school_profile = SchoolProfile.objects.filter(profile_id=school_profile_id).first() if school_profile_id else None

    if not school_profile or not school_profile.enrollment_enabled:
        messages.error(request, 'Enrollment is currently closed. Please check back later.')
        return redirect('portal_grades')

    if EnrollmentApplication.objects.filter(lrn=account.lrn).exclude(status=EnrollmentApplication.STATUS_REJECTED).exists():
        messages.info(request, 'You already have an enrollment application in progress.')
        return redirect('portal_grades')

    if request.method == 'POST':
        birthday = request.POST.get('birthday')
        required = {
            'surname': request.POST.get('surname', '').strip(),
            'given_name': request.POST.get('given_name', '').strip(),
            'sex': request.POST.get('sex', ''),
            'address': request.POST.get('address', '').strip(),
            'grade_level': request.POST.get('grade_level', ''),
            'guardian_name': request.POST.get('guardian_name', '').strip(),
            'guardian_contact': request.POST.get('guardian_contact', '').strip(),
        }
        if not birthday or not all(required.values()):
            messages.error(request, 'Please fill in all required fields.')
            return render(request, 'portal/enrollment_form.html', {'student': student})

        application = EnrollmentApplication.objects.create(
            school_profile_id=school_profile_id,
            lrn=account.lrn,
            surname=required['surname'],
            given_name=required['given_name'],
            middle_name=request.POST.get('middle_name', '').strip(),
            extension=request.POST.get('extension', '').strip(),
            sex=required['sex'],
            birthday=datetime.strptime(birthday, '%Y-%m-%d').date(),
            address=required['address'],
            grade_level=required['grade_level'],
            track=request.POST.get('track', '').strip(),
            strand=request.POST.get('strand', '').strip(),
            previous_school=request.POST.get('previous_school', '').strip(),
            guardian_name=required['guardian_name'],
            guardian_relationship=request.POST.get('guardian_relationship', '').strip(),
            guardian_contact=required['guardian_contact'],
        )
        send_mail(
            'Enrollment Application Received',
            f'Hello {application.given_name},\n\n'
            'Your enrollment application has been received and is now queued for processing by your school. '
            "You'll receive another email once a personal-appearance schedule is set.\n\n"
            'Thank you.',
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email] if request.user.email else [],
            fail_silently=True,
        )
        return render(request, 'portal/enrollment_submitted.html')

    return render(request, 'portal/enrollment_form.html', {'student': student})
