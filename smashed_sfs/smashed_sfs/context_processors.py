"""Site-wide shell context: sidebar nav items and breadcrumb label, by role.

Runs on every request so templates/base.html can render the correct sidebar
without every view having to pass it explicitly. Reuses the same
Teacher.objects.get(username=request.user.username) / teacher.role pattern
already established in school/views.py.
"""

from django.urls import reverse

from accounts.models import Teacher
from portal.models import StudentAccount
from students.models import Section, SchoolProfile


def _nav_item(request, label, url_name, url_args=None, match_names=None):
    href = reverse(url_name, args=url_args or [])
    match_names = match_names or {url_name}
    active = bool(request.resolver_match) and request.resolver_match.url_name in match_names
    return {'label': label, 'href': href, 'active': active}


def shell_context(request):
    if not request.user.is_authenticated:
        return {}

    student_account = StudentAccount.objects.filter(
        user=request.user, status=StudentAccount.STATUS_APPROVED
    ).first()
    if student_account:
        return {
            'shell_role': 'student',
            'shell_breadcrumb_context': 'MY ACCOUNT',
            'shell_nav_items': [
                _nav_item(request, 'My Grades', 'portal_grades'),
            ],
        }

    teacher = Teacher.objects.filter(username=request.user.username).first()
    if not teacher:
        return {}

    if teacher.role == Teacher.ROLE_ADVISER:
        section = Section.objects.filter(adviser_id=teacher.teacher_id).first()
        if section:
            breadcrumb_context = f"GRADE {section.grade_level} · {section.strand} · {section.section_name}".upper()
        else:
            breadcrumb_context = 'NO SECTION YET'

        return {
            'shell_role': 'adviser',
            'shell_breadcrumb_context': breadcrumb_context,
            'shell_nav_items': [
                _nav_item(request, 'Home', 'dashboard'),
                _nav_item(request, 'Students', 'student_list',
                          match_names={'student_list', 'upload_students', 'save_students', 'update_student'}),
                _nav_item(request, 'Grades', 'view_grades', ['all'],
                          match_names={'view_grades', 'upload_grades', 'save_grades'}),
                _nav_item(request, 'Attendance', 'view_attendance', ['all'],
                          match_names={'view_attendance', 'upload_attendance', 'save_attendance',
                                       'download_attendance_template'}),
                _nav_item(request, 'Access Requests', 'access_requests',
                          match_names={'access_requests', 'decide_access_request'}),
                _nav_item(request, 'Reports', 'select_student_report',
                          match_names={'select_student_report', 'view_sf9', 'view_sf10'}),
            ],
        }

    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()
    breadcrumb_context = school_profile.school_name.upper() if school_profile else 'NO SCHOOL YET'

    return {
        'shell_role': 'school_admin',
        'shell_breadcrumb_context': breadcrumb_context,
        'shell_nav_items': [
            _nav_item(request, 'Overview', 'school_dashboard'),
            _nav_item(request, 'Students', 'school_student_list'),
            _nav_item(request, 'Sections', 'school_sections',
                      match_names={'school_sections', 'reassign_section_adviser'}),
            _nav_item(request, 'Accounts', 'school_accounts',
                      match_names={'school_accounts', 'toggle_teacher_active', 'reassign_teacher_section'}),
        ],
    }
