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
                _nav_item(request, "Learner's Academic Ratings", 'portal_grades'),
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
                _nav_item(request, 'Attendance', 'attendance_grid',
                          match_names={'attendance_grid', 'attendance_grid_save', 'view_attendance'}),
                _nav_item(request, 'Ratings', 'view_grades', ['all'],
                          match_names={'view_grades', 'upload_grades', 'save_grades'}),
                _nav_item(request, 'Reports', 'select_student_report',
                          match_names={'select_student_report', 'view_sf9', 'view_sf10', 'view_rankings'}),
                _nav_item(request, 'Ancillary', 'ancillary'),
                _nav_item(request, 'Tools', 'tools'),
                _nav_item(request, 'Access Requests', 'access_requests',
                          match_names={'access_requests', 'decide_access_request'}),
            ],
        }

    if teacher.role == Teacher.ROLE_SUBJECT_TEACHER:
        return {
            'shell_role': 'subject_teacher',
            'shell_breadcrumb_context': 'MY SUBJECT TEACHING',
            'shell_nav_items': [
                _nav_item(request, 'My Assignment', 'my_subject_teaching',
                          match_names={'my_subject_teaching', 'subject_teaching_grades'}),
                _nav_item(request, 'Reports', 'select_student_report',
                          match_names={'select_student_report', 'view_sf7', 'view_sf9', 'view_sf10',
                                       'view_rankings', 'subject_statistics_report'}),
                _nav_item(request, 'Tools', 'tools'),
            ],
        }

    if teacher.role == Teacher.ROLE_NON_TEACHING and not teacher.is_officer:
        return {
            'shell_role': 'non_teaching',
            'shell_breadcrumb_context': 'MY ACCOUNT',
            'shell_nav_items': [
                _nav_item(request, 'Tools', 'tools'),
            ],
        }

    # Registrar/Principal, and a Non-Teaching Officer (is_officer=True) -
    # same full school-admin nav for all three, matching
    # school/views.py's _get_school_admin_teacher gate.
    school_profile = None
    if teacher.school_profile_id:
        school_profile = SchoolProfile.objects.filter(profile_id=teacher.school_profile_id).first()
    breadcrumb_context = school_profile.school_name.upper() if school_profile else 'NO SCHOOL YET'

    return {
        'shell_role': 'school_admin',
        'shell_breadcrumb_context': breadcrumb_context,
        'shell_nav_items': [
            _nav_item(request, 'Dashboard', 'school_dashboard'),
            _nav_item(request, 'Students', 'school_student_list'),
            _nav_item(request, 'Sections', 'school_sections',
                      match_names={'school_sections', 'reassign_section_adviser'}),
            _nav_item(request, 'Accounts', 'school_accounts',
                      match_names={'school_accounts', 'toggle_teacher_active', 'toggle_teacher_officer', 'reassign_teacher_section'}),
            _nav_item(request, 'Assignments', 'school_assignments',
                      match_names={'school_assignments', 'remove_teacher_subject_assignment'}),
        ],
    }
