"""Who's-online monitoring page, added onto the admin site at
/admin/online-users/. Reads the last_seen heartbeat TrackLastSeenMiddleware
stamps on Teacher/StudentAccount on every request, and groups people the
way a school admin actually thinks about them: Division -> School ->
Teachers / Students, rather than as flat, ungrouped tables.

Wired in the same way as admin_grouping.py: monkey-patch admin.site
rather than swap in a custom AdminSite subclass, so nothing else about
the existing admin registrations has to change.
"""
from datetime import timedelta

from django.contrib import admin
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from accounts.models import Teacher
from portal.models import StudentAccount
from students.models import SchoolProfile, Section, Student

# A session with no request in the last 5 minutes is treated as offline -
# generous enough to survive normal page-to-page navigation gaps.
ONLINE_WINDOW = timedelta(minutes=5)
UNASSIGNED_DIVISION = 'Unassigned Division'
UNASSIGNED_SCHOOL = 'Unassigned School'


def _status(last_seen, now):
    if last_seen is None:
        return {'online': False, 'last_seen': None, 'label': 'Never logged in'}
    return {'online': last_seen >= now - ONLINE_WINDOW, 'last_seen': last_seen, 'label': None}


def _build_student_rows(profile_id, now, accounts_by_lrn):
    section_ids = list(
        Section.objects.filter(school_profile_id=profile_id).values_list('section_id', flat=True)
    ) if profile_id is not None else []
    students = Student.objects.filter(section_id__in=section_ids).order_by('surname', 'name') if section_ids else []

    rows = []
    for s in students:
        account = accounts_by_lrn.get(s.lrn)
        if account is None:
            rows.append({'name': f'{s.surname}, {s.name}', 'online': False, 'last_seen': None, 'label': 'No portal account'})
        else:
            rows.append({'name': f'{s.surname}, {s.name}', **_status(account.last_seen, now)})
    return rows


def _school_display_name(profile_id):
    if profile_id is None:
        return UNASSIGNED_SCHOOL
    profile = SchoolProfile.objects.filter(profile_id=profile_id).first()
    return profile.school_name if profile else UNASSIGNED_SCHOOL


def online_users_view(request):
    now = timezone.now()

    teachers = list(Teacher.objects.all().order_by('full_name'))
    accounts_by_lrn = {
        sa.lrn: sa for sa in StudentAccount.objects.filter(status=StudentAccount.STATUS_APPROVED)
    }

    profiles = list(SchoolProfile.objects.all().order_by('division', 'school_name'))
    known_profile_ids = {p.profile_id for p in profiles}

    division_order = []
    divisions = {}
    for profile in profiles:
        division_name = profile.division or UNASSIGNED_DIVISION
        if division_name not in divisions:
            division_order.append(division_name)
            divisions[division_name] = []
        divisions[division_name].append(profile)

    orphan_teacher_ids = {t.school_profile_id for t in teachers if t.school_profile_id not in known_profile_ids}
    if orphan_teacher_ids:
        divisions.setdefault(UNASSIGNED_DIVISION, [])
        if UNASSIGNED_DIVISION not in division_order:
            division_order.append(UNASSIGNED_DIVISION)

    def build_school_block(school_name, profile_id):
        profile_teachers = [t for t in teachers if t.school_profile_id == profile_id]

        teacher_rows = []
        for t in profile_teachers:
            teacher_rows.append({'name': t.full_name, 'role': t.get_role_display(), **_status(t.last_seen, now)})

        student_rows = _build_student_rows(profile_id, now, accounts_by_lrn)

        return {
            'name': school_name,
            'profile_id': profile_id,
            'teacher_rows': teacher_rows,
            'students_total': len(student_rows),
            'teachers_online': sum(1 for r in teacher_rows if r['online']),
            'students_online': sum(1 for r in student_rows if r['online']),
        }

    division_blocks = []
    total_online = 0
    for division_name in division_order:
        school_blocks = [build_school_block(p.school_name, p.profile_id) for p in divisions[division_name]]
        if division_name == UNASSIGNED_DIVISION and orphan_teacher_ids:
            for profile_id in orphan_teacher_ids:
                school_blocks.append(build_school_block(UNASSIGNED_SCHOOL, profile_id))
        for block in school_blocks:
            total_online += block['teachers_online'] + block['students_online']
        division_blocks.append({'name': division_name, 'schools': school_blocks})

    context = {
        **admin.site.each_context(request),
        'title': 'Online Users',
        'division_blocks': division_blocks,
        'total_online': total_online,
        'online_window_minutes': int(ONLINE_WINDOW.total_seconds() // 60),
    }
    return render(request, 'admin/online_users.html', context)


def online_users_school_students_view(request, profile_id=None):
    now = timezone.now()
    accounts_by_lrn = {
        sa.lrn: sa for sa in StudentAccount.objects.filter(status=StudentAccount.STATUS_APPROVED)
    }
    student_rows = _build_student_rows(profile_id, now, accounts_by_lrn)

    context = {
        **admin.site.each_context(request),
        'title': 'Online Students',
        'school_name': _school_display_name(profile_id),
        'student_rows': student_rows,
        'students_online': sum(1 for r in student_rows if r['online']),
        'online_window_minutes': int(ONLINE_WINDOW.total_seconds() // 60),
    }
    return render(request, 'admin/online_users_students.html', context)


def apply():
    original_get_urls = admin.site.get_urls

    def get_urls():
        custom = [
            path('online-users/', admin.site.admin_view(online_users_view), name='online_users'),
            path(
                'online-users/students/unassigned/',
                admin.site.admin_view(online_users_school_students_view),
                name='online_users_students_unassigned',
            ),
            path(
                'online-users/students/<int:profile_id>/',
                admin.site.admin_view(online_users_school_students_view),
                name='online_users_students',
            ),
        ]
        return custom + original_get_urls()

    admin.site.get_urls = get_urls
