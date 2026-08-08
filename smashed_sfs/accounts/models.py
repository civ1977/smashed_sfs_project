from django.db import models
from django.contrib.auth.models import User

class Teacher(models.Model):
    ROLE_ADVISER = 'adviser'
    ROLE_REGISTRAR = 'registrar'
    ROLE_PRINCIPAL = 'principal'
    ROLE_NON_TEACHING = 'non_teaching'
    ROLE_SUBJECT_TEACHER = 'subject_teacher'
    ROLE_CHOICES = [
        (ROLE_ADVISER, 'Class Adviser'),
        (ROLE_REGISTRAR, 'Registrar'),
        (ROLE_PRINCIPAL, 'Principal'),
        (ROLE_NON_TEACHING, 'Non-Teaching'),
        (ROLE_SUBJECT_TEACHER, 'Subject Teacher'),
    ]

    teacher_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)
    full_name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    email = models.CharField(max_length=100, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ADVISER)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(blank=True, null=True)
    last_seen = models.DateTimeField(blank=True, null=True)
    school_profile_id = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'teacher_adviser'

    def __str__(self):
        return self.full_name


class TeacherTimeRecord(models.Model):
    """One day's worth of Daily Time Record (Civil Service Form No. 48)
    entries for a named employee - either typed in by hand or imported
    from a biometric/DTR app's CSV or Excel export via
    accounts.views.upload_dtr.

    teacher_id is the logged-in account preparing/editing this DTR (for
    access scoping), NOT necessarily who it's for - a registrar routinely
    prepares DTRs for other staff, so employee_name is the actual subject
    of the record and is searchable/editable independently of the account
    that owns the edit. Defaults to that account's own Teacher.full_name
    the first time a DTR is opened, but can be changed to anyone."""

    record_id = models.AutoField(primary_key=True)
    teacher_id = models.IntegerField()
    employee_name = models.CharField(max_length=100, default='')
    date = models.DateField()
    am_arrival = models.CharField(max_length=16, blank=True, null=True)
    am_departure = models.CharField(max_length=16, blank=True, null=True)
    pm_arrival = models.CharField(max_length=16, blank=True, null=True)
    pm_departure = models.CharField(max_length=16, blank=True, null=True)
    undertime_hours = models.CharField(max_length=16, blank=True, null=True)
    undertime_minutes = models.CharField(max_length=16, blank=True, null=True)

    class Meta:
        db_table = 'teacher_time_record'
        unique_together = ('teacher_id', 'employee_name', 'date')