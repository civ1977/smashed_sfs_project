"""Regroups the Django admin index by real-world category (Accounts &
Access, School Setup, Students, Grades & Attendance) instead of by Django
app label - the default grouping puts Attendance/Grades/Subject Mappings
under "GRADES" and Sections/School Profiles under "STUDENTS" purely
because of which app they're coded in, which doesn't match how a school
admin actually thinks about the data.

Applied by monkey-patching admin.site.get_app_list rather than swapping
in a custom AdminSite class, so every app's existing `@admin.register(...)`
call (which registers against the default site) keeps working unchanged.
"""
from django.contrib import admin

ADMIN_GROUPS = [
    ('Accounts & Access', [
        ('accounts', 'Teacher'),
        ('portal', 'StudentAccount'),
        ('auth', 'User'),
        ('auth', 'Group'),
    ]),
    ('School Setup', [
        ('students', 'SchoolProfile'),
        ('students', 'Section'),
        ('grades', 'SubjectMapping'),
        ('grades', 'SubjectTermExclusion'),
        ('grades', 'SchoolCalendarException'),
        ('grades', 'TeacherSubjectAssignment'),
    ]),
    ('Students', [
        ('students', 'Student'),
    ]),
    ('Grades & Attendance', [
        ('grades', 'Grade'),
        ('grades', 'StudentTermRemark'),
        ('grades', 'Attendance'),
        ('grades', 'AttendanceMark'),
    ]),
]

OTHER_GROUP_NAME = 'Other'


def group_slug(group_name):
    return group_name.lower().replace(' & ', '_').replace(' ', '_')


def registered_model_keys():
    """(app_label, object_name) for every model currently registered on
    admin.site - the same universe _grouped_get_app_list draws from."""
    return {(model._meta.app_label, model.__name__) for model in admin.site._registry}


def resolve_group_keys(slug):
    """(app_label, object_name) keys belonging to one group, by its slug -
    the single source both the index page and the backup-download feature
    (admin_backup.py) read from, so a group's button always backs up
    exactly the tables that group displays. Returns None for an unknown
    slug; the 'other' slug is resolved dynamically as whatever's
    registered but not claimed by a named group above."""
    for group_name, keys in ADMIN_GROUPS:
        if group_slug(group_name) == slug:
            return list(keys)

    if slug == group_slug(OTHER_GROUP_NAME):
        claimed = {key for _, keys in ADMIN_GROUPS for key in keys}
        return [key for key in registered_model_keys() if key not in claimed]

    return None


def _grouped_get_app_list(self, request, app_label=None):
    app_dict = self._build_app_dict(request, app_label)

    model_lookup = {}
    for app in app_dict.values():
        for model in app['models']:
            model_lookup[(app['app_label'], model['object_name'])] = model

    grouped = []
    used = set()
    for group_name, keys in ADMIN_GROUPS:
        models = []
        for app_label_key, object_name in keys:
            model = model_lookup.get((app_label_key, object_name))
            if model:
                models.append(model)
                used.add((app_label_key, object_name))
        if models:
            models.sort(key=lambda m: m['name'])
            grouped.append({
                'name': group_name,
                'app_label': group_slug(group_name),
                'app_url': '#',
                'has_module_perms': True,
                'models': models,
            })

    # Anything registered later but not added to ADMIN_GROUPS above still
    # shows up here instead of silently disappearing from the index.
    leftover = []
    for app in app_dict.values():
        for model in app['models']:
            key = (app['app_label'], model['object_name'])
            if key not in used:
                leftover.append(model)
    if leftover:
        leftover.sort(key=lambda m: m['name'])
        grouped.append({
            'name': OTHER_GROUP_NAME,
            'app_label': group_slug(OTHER_GROUP_NAME),
            'app_url': '#',
            'has_module_perms': True,
            'models': leftover,
        })

    return grouped


def apply():
    admin.site.get_app_list = _grouped_get_app_list.__get__(admin.site, admin.site.__class__)
