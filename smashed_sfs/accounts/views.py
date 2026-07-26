from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction

from students.models import Section
from portal.models import StudentAccount
from .models import Teacher
from .forms import SchoolProfileSelectForm, SchoolProfileForm, SectionForm

def register(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        full_name = request.POST.get('full_name')
        position = request.POST.get('position')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        
        if password != password_confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/register.html')
        
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'accounts/register.html')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'accounts/register.html')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'accounts/register.html')
        
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            user.first_name = full_name.split()[0] if full_name else ''
            user.last_name = full_name.split()[-1] if len(full_name.split()) > 1 else ''
            user.save()

            Teacher.objects.create(
                user=user,
                username=username,
                password=user.password,
                full_name=full_name,
                position=position,
                email=email,
            )

        login(request, user)
        messages.success(request, f'Registration successful! Welcome {username}!')
        return redirect('complete_profile')

    return render(request, 'accounts/register.html')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {username}!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'accounts/login.html')


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def dashboard(request):
    student_account = StudentAccount.objects.filter(user=request.user).first()
    if student_account:
        if student_account.status == StudentAccount.STATUS_APPROVED:
            return redirect('portal_dashboard')
        return redirect('portal_pending')

    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile. Please contact the administrator.')
        return render(request, 'accounts/dashboard.html', {'teacher': None, 'profile_incomplete': False})

    if teacher.role != Teacher.ROLE_ADVISER:
        return redirect('school_dashboard')

    profile_incomplete = not teacher.school_profile_id or not Section.objects.filter(adviser_id=teacher.teacher_id).exists()

    return render(request, 'accounts/dashboard.html', {
        'teacher': teacher,
        'profile_incomplete': profile_incomplete,
    })


@login_required
def complete_profile(request):
    try:
        teacher = Teacher.objects.get(username=request.user.username)
    except Teacher.DoesNotExist:
        messages.error(request, 'Your account is not linked to a Teacher profile. Please contact the administrator.')
        return redirect('dashboard')

    needs_school = not teacher.school_profile_id
    needs_section = not Section.objects.filter(adviser_id=teacher.teacher_id).exists()

    if not needs_school and not needs_section:
        messages.info(request, 'Your profile is already complete.')
        return redirect('dashboard')

    data = request.POST if request.method == 'POST' else None

    school_select_form = SchoolProfileSelectForm(data, prefix='school') if needs_school else None
    school_create_form = SchoolProfileForm(data, prefix='newschool') if needs_school else None
    section_form = SectionForm(data, prefix='section') if needs_section else None

    if request.method == 'POST':
        new_school_needed = False
        school_valid = True
        if needs_school:
            school_valid = school_select_form.is_valid()
            new_school_needed = school_valid and school_select_form.is_new_school()
            if new_school_needed:
                school_valid = school_create_form.is_valid()

        section_valid = section_form.is_valid() if needs_section else True

        if school_valid and section_valid:
            with transaction.atomic():
                if needs_school:
                    if new_school_needed:
                        school_profile = school_create_form.save(commit=False)
                        school_profile.created_by = teacher.teacher_id
                        school_profile.save()
                        profile_id = school_profile.profile_id
                    else:
                        profile_id = int(school_select_form.cleaned_data['school_profile'])
                    teacher.school_profile_id = profile_id
                    teacher.save()

                if needs_section:
                    section = section_form.save(commit=False)
                    section.adviser_id = teacher.teacher_id
                    section.school_profile_id = teacher.school_profile_id
                    section.save()

            messages.success(request, '✅ Profile setup complete! You can now upload students and grades.')
            return redirect('dashboard')

        messages.error(request, 'Please fix the errors below.')

    return render(request, 'accounts/complete_profile.html', {
        'needs_school': needs_school,
        'needs_section': needs_section,
        'school_select_form': school_select_form,
        'school_create_form': school_create_form,
        'section_form': section_form,
    })