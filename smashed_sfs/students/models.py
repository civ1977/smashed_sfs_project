from django.db import models

class SchoolProfile(models.Model):
    profile_id = models.AutoField(primary_key=True)
    school_year = models.CharField(max_length=20)
    region = models.CharField(max_length=100)
    division = models.CharField(max_length=200)
    district = models.CharField(max_length=100)
    municipality = models.CharField(max_length=100)
    school_name = models.CharField(max_length=200)
    school_id = models.CharField(max_length=20)
    registrar_name = models.CharField(max_length=100)
    registrar_designation = models.CharField(max_length=100)
    guidance_counselor = models.CharField(max_length=100)
    principal_name = models.CharField(max_length=100)
    principal_designation = models.CharField(max_length=100)
    sds_name = models.CharField(max_length=100)
    created_by = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    # Some schools don't distinguish Core vs Elective at all - toggled from
    # the Arrange Subjects page (grades/views.py's arrange_subjects), these
    # control whether SF9/SF10 show the "Core Subjects"/"Elective Subjects"
    # header row above that group, independently of each other. Subjects
    # themselves still render either way; only the label row is affected.
    show_core_heading = models.BooleanField(default=True)
    show_elective_heading = models.BooleanField(default=True)
    # Toggled from the Enrollment page (school/views.py's school_enrollment) -
    # gates whether /portal/enrollment/ accepts submissions. Off by default
    # so a newly-seeded school doesn't silently accept applications before
    # a registrar/principal/officer has actually reviewed the process.
    enrollment_enabled = models.BooleanField(default=False)

    class Meta:
        db_table = 'school_profile'

    def __str__(self):
        return self.school_name


class Section(models.Model):
    section_id = models.AutoField(primary_key=True)
    grade_level = models.CharField(max_length=10)
    track = models.CharField(max_length=50)
    strand = models.CharField(max_length=50)
    section_name = models.CharField(max_length=50)
    modality = models.CharField(max_length=50)
    adviser_id = models.IntegerField(null=True, blank=True)
    school_profile_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'section'


class Student(models.Model):
    SEX_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_DROPPED = 'dropped'
    STATUS_TRANSFERRED = 'transferred'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_DROPPED, 'Dropped'),
        (STATUS_TRANSFERRED, 'Transferred'),
    ]

    lrn = models.CharField(max_length=12, primary_key=True)
    surname = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    extension = models.CharField(max_length=10, blank=True, null=True)
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    birthday = models.DateField(blank=True, null=True)
    school_g10 = models.CharField(max_length=200)
    school_address_g10 = models.CharField(max_length=300)
    average_g10 = models.DecimalField(max_digits=5, decimal_places=2)
    completion_date_g10 = models.DateField(blank=True, null=True)
    shs_admission_date = models.DateField(blank=True, null=True)
    section_id = models.IntegerField()
    adviser_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    # Enrollment status shown on SF9/SF10, distinct from is_active (which
    # gates whether the student appears in the adviser's day-to-day roster
    # queries throughout the app) - a Dropped/Transferred student's
    # historical grades still need to render correctly on their official
    # forms, which is what this field feeds.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    class Meta:
        db_table = 'student'


class StudentRecordAuditLog(models.Model):
    """DPA accountability trail: who touched an actual Student, Grade, or
    Attendance row, when, and which one. Separate from
    TeacherAccountAuditLog/SectionAuditLog (school/models.py), which only
    cover account and section administration - not the student data itself
    that DPA breach-notification and accountability obligations center on.

    record_id is stored as text since it spans different PK types across
    the three record types (Student.lrn is a CharField; Grade.grade_id and
    AttendanceMark.mark_id are AutoFields). lrn is always the affected
    student's LRN regardless of record_type, so "which students were
    touched" is answerable with one filter no matter which table changed.
    """

    RECORD_STUDENT = 'student'
    RECORD_GRADE = 'grade'
    RECORD_ATTENDANCE = 'attendance'
    RECORD_TYPE_CHOICES = [
        (RECORD_STUDENT, 'Student'),
        (RECORD_GRADE, 'Grade'),
        (RECORD_ATTENDANCE, 'Attendance'),
    ]

    ACTION_CREATED = 'created'
    ACTION_UPDATED = 'updated'
    ACTION_DELETED = 'deleted'
    ACTION_CHOICES = [
        (ACTION_CREATED, 'Created'),
        (ACTION_UPDATED, 'Updated'),
        (ACTION_DELETED, 'Deleted'),
    ]

    log_id = models.AutoField(primary_key=True)
    record_type = models.CharField(max_length=20, choices=RECORD_TYPE_CHOICES)
    record_id = models.CharField(max_length=50)
    lrn = models.CharField(max_length=12)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.IntegerField()
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'student_record_audit_log'
        ordering = ['-performed_at']

    def __str__(self):
        return f'{self.record_type} {self.record_id} {self.action} by {self.performed_by}'


def log_student_record_change(record_type, record_id, lrn, action, performed_by):
    """Shared helper for the create/update/delete call sites touching
    Student, Grade, or AttendanceMark rows - keeps the one-line-per-call
    convention consistent instead of constructing StudentRecordAuditLog
    directly at each site."""
    StudentRecordAuditLog.objects.create(
        record_type=record_type,
        record_id=str(record_id),
        lrn=lrn,
        action=action,
        performed_by=performed_by,
    )

    def __str__(self):
        return f"{self.surname}, {self.name} ({self.lrn})"