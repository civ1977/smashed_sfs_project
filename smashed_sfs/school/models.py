from django.db import models


class EnrollmentAssignment(models.Model):
    """One (teacher, scope) pairing on the Enrollment page's Assign
    Personnel form - who's allowed to process which applications.
    scope_code is either 'all' (Whole School) or a grade_level string; more
    than one teacher can be assigned to the same scope, and the same
    teacher can hold several scope rows (e.g. Grade 11 and Grade 12
    separately). unique_together is the same "already assigned" guard the
    UI enforces, kept here too since this is the actual source of truth."""

    assignment_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    teacher_id = models.IntegerField()
    scope_code = models.CharField(max_length=10)
    assigned_by = models.IntegerField()
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'enrollment_assignment'
        unique_together = ('school_profile_id', 'teacher_id', 'scope_code')

    def __str__(self):
        return f'teacher {self.teacher_id} -> {self.scope_code}'


class EnrollmentApplication(models.Model):
    """One learner's submission from /portal/enrollment/ - deliberately
    holds the applicant's full submitted info directly (rather than a
    Student FK) since Student.section_id/adviser_id are required fields an
    enrollee doesn't have yet; a real Student row only gets created
    separately (via the existing Sections/Students admin pages) once a
    registrar decides where to place them. lrn links back to the Student
    record the application was filed from (portal_register already
    requires the LRN to exist), used only to prefill the form and is not
    itself a foreign key, matching this codebase's no-FK convention."""

    STATUS_PENDING = 'pending'
    STATUS_SCHEDULED = 'scheduled'
    STATUS_ENROLLED = 'enrolled'
    STATUS_REJECTED = 'rejected'
    STATUS_OTHER = 'other'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_ENROLLED, 'Enrolled'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_OTHER, 'Other'),
    ]

    SEX_CHOICES = [
        ('MALE', 'Male'),
        ('FEMALE', 'Female'),
    ]

    application_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    lrn = models.CharField(max_length=12)

    surname = models.CharField(max_length=100)
    given_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default='')
    extension = models.CharField(max_length=10, blank=True, default='')
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    birthday = models.DateField()
    address = models.CharField(max_length=300)

    grade_level = models.CharField(max_length=10)
    track = models.CharField(max_length=50, blank=True, default='')
    strand = models.CharField(max_length=50, blank=True, default='')
    previous_school = models.CharField(max_length=200, blank=True, default='')

    guardian_name = models.CharField(max_length=100)
    guardian_relationship = models.CharField(max_length=50, blank=True, default='')
    guardian_contact = models.CharField(max_length=50)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)
    appearance_date = models.DateField(blank=True, null=True)
    appearance_time = models.TimeField(blank=True, null=True)
    scheduled_by = models.IntegerField(blank=True, null=True)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    decided_by = models.IntegerField(blank=True, null=True)
    decided_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'enrollment_application'
        ordering = ['-submitted_at']

    @property
    def full_name(self):
        return f'{self.surname}, {self.given_name}'

    def __str__(self):
        return f'{self.full_name} ({self.get_status_display()})'


class TimeSlot(models.Model):
    """One numbered period in a school's daily bell schedule (e.g. "1st,
    7:30-8:30"). is_break marks a Recess/Lunch row, which the scheduling
    grid renders as a full-width label instead of an editable cell.
    Seeded automatically per school_profile_id the first time the
    scheduling page is opened (see school.views.school_scheduling)."""

    timeslot_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    slot_order = models.IntegerField()
    label = models.CharField(max_length=50)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_break = models.BooleanField(default=False)

    class Meta:
        db_table = 'time_slot'
        ordering = ['school_profile_id', 'slot_order']

    def __str__(self):
        return f"{self.label} ({self.start_time}-{self.end_time})"


class ScheduleRequirement(models.Model):
    """How many times per week a TeacherSubjectAssignment (grades app)
    needs to meet. One row per assignment; assignments with no row here
    default to 4 sessions/week (see school.scheduler.DEFAULT_SESSIONS_PER_WEEK)."""

    requirement_id = models.AutoField(primary_key=True)
    assignment_id = models.IntegerField(unique=True)
    sessions_per_week = models.PositiveIntegerField(default=4)

    class Meta:
        db_table = 'schedule_requirement'

    def __str__(self):
        return f"assignment {self.assignment_id}: {self.sessions_per_week}/week"


class ScheduleEntry(models.Model):
    """One placed class session: a TeacherSubjectAssignment occupying one
    (day, timeslot) cell. teacher_id/section_id/mapping_id are snapshotted
    from the assignment onto the row (rather than looked up each time) so
    conflict checks and grid queries stay single-table.

    The two unique_together constraints ARE the conflict guarantee: a
    section can't have two things happening at once, and a teacher can't
    be in two places at once. Nothing upstream needs to re-check this."""

    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
    ]

    entry_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    assignment_id = models.IntegerField()
    teacher_id = models.IntegerField()
    section_id = models.IntegerField()
    mapping_id = models.IntegerField()
    day_of_week = models.CharField(max_length=10, choices=DAY_CHOICES)
    timeslot_id = models.IntegerField()

    class Meta:
        db_table = 'schedule_entry'
        unique_together = [
            ('section_id', 'day_of_week', 'timeslot_id'),
            ('teacher_id', 'day_of_week', 'timeslot_id'),
        ]

    def __str__(self):
        return f"assignment {self.assignment_id} @ {self.day_of_week} slot {self.timeslot_id}"


class TeacherAccountAuditLog(models.Model):
    """One row per activate/deactivate action taken on a Teacher account from
    the school-admin Accounts page - who did it, to whom, and when."""

    ACTION_ACTIVATED = 'activated'
    ACTION_DEACTIVATED = 'deactivated'
    ACTION_PROMOTED_OFFICER = 'promoted_officer'
    ACTION_DEMOTED_OFFICER = 'demoted_officer'
    ACTION_CHOICES = [
        (ACTION_ACTIVATED, 'Activated'),
        (ACTION_DEACTIVATED, 'Deactivated'),
        (ACTION_PROMOTED_OFFICER, 'Promoted to Officer'),
        (ACTION_DEMOTED_OFFICER, 'Demoted to Non-Officer'),
    ]

    log_id = models.AutoField(primary_key=True)
    target_teacher_id = models.IntegerField()
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.IntegerField()
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'teacher_account_audit_log'
        ordering = ['-performed_at']

    def __str__(self):
        return f"teacher {self.target_teacher_id} {self.action} by {self.performed_by}"


class SectionAuditLog(models.Model):
    """One row per edit/delete action taken on a Section from the
    school-admin Sections page. section_label is a snapshot (e.g.
    "Grade 11-STEM-A") rather than a live section_id lookup, so the log
    stays readable after a section is deleted."""

    ACTION_EDITED = 'edited'
    ACTION_DELETED = 'deleted'
    ACTION_CHOICES = [
        (ACTION_EDITED, 'Edited'),
        (ACTION_DELETED, 'Deleted'),
    ]

    log_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    section_label = models.CharField(max_length=100)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    detail = models.CharField(max_length=255, blank=True, default='')
    performed_by = models.IntegerField()
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'section_audit_log'
        ordering = ['-performed_at']

    def __str__(self):
        return f"{self.section_label} {self.action} by {self.performed_by}"
