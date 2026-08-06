from django.db import models

class SubjectMapping(models.Model):
    mapping_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    grade_level = models.CharField(max_length=10)
    strand = models.CharField(max_length=50)
    subject_number = models.IntegerField()
    subject_name = models.CharField(max_length=100)
    created_by = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_elective = models.BooleanField(default=False)

    class Meta:
        db_table = 'subject_mapping'

    def __str__(self):
        return f"{self.subject_number}: {self.subject_name}"


class TeacherSubjectAssignment(models.Model):
    """Links a Subject Teacher to a section/subject they teach. Empty until
    a registrar or principal creates assignments (not built yet)."""

    assignment_id = models.AutoField(primary_key=True)
    teacher_id = models.IntegerField()
    section_id = models.IntegerField()
    mapping_id = models.IntegerField()

    class Meta:
        db_table = 'teacher_subject_assignment'

    def __str__(self):
        return f"teacher {self.teacher_id} -> mapping {self.mapping_id} (section {self.section_id})"


class SubjectTermExclusion(models.Model):
    """Marks a subject as not offered in one specific term - e.g. a subject
    that only runs Term 1-2 shouldn't be required for a Term 3 gradesheet or
    count against a student's Term 3 ranking completeness. The subject stays
    required for whichever terms it isn't excluded from."""

    exclusion_id = models.AutoField(primary_key=True)
    mapping_id = models.IntegerField()
    term = models.IntegerField()
    excluded_by = models.IntegerField()
    excluded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subject_term_exclusion'
        unique_together = ('mapping_id', 'term')

    def __str__(self):
        return f"mapping {self.mapping_id} excluded from term {self.term}"


class StudentTermRemark(models.Model):
    """A teacher's free-text comment for one student for one term - edited
    from the rankings table's Comments/Remarks column and mirrored into the
    SF9 report's Teacher's Comments/Remarks box for that same term."""

    remark_id = models.AutoField(primary_key=True)
    lrn = models.CharField(max_length=12)
    term = models.IntegerField()
    remark = models.TextField(blank=True, default='')
    updated_by = models.IntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'student_term_remark'
        unique_together = ('lrn', 'term')

    def __str__(self):
        return f"{self.lrn} term {self.term} remark"


class Grade(models.Model):
    grade_id = models.AutoField(primary_key=True)
    lrn = models.CharField(max_length=12)
    mapping_id = models.IntegerField()
    term = models.IntegerField()
    grade = models.IntegerField()
    comment = models.TextField(blank=True, null=True)
    uploaded_by = models.IntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'grades'

    def __str__(self):
        return f"{self.lrn} - Term {self.term}: {self.grade}"


ATTENDANCE_MONTHS = ['Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr']
MONTH_CHOICES = [(m, m) for m in ATTENDANCE_MONTHS]


class Attendance(models.Model):
    attendance_id = models.AutoField(primary_key=True)
    lrn = models.CharField(max_length=12)
    month = models.CharField(max_length=3, choices=MONTH_CHOICES)
    days_present = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    uploaded_by = models.IntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'attendance'


class AttendanceMark(models.Model):
    """Per-day attendance exception for one student, matching the SF2-SHS
    form's own convention: a day with no mark means Present (blank cell on
    the form) - Present is never stored as a row here."""

    STATUS_ABSENT = 'absent'
    STATUS_LATE_COMER = 'late_comer'
    STATUS_CUTTING_CLASSES = 'cutting_classes'
    STATUS_CHOICES = [
        (STATUS_ABSENT, 'Absent'),
        (STATUS_LATE_COMER, 'Late Comer'),
        (STATUS_CUTTING_CLASSES, 'Cutting Classes'),
    ]

    mark_id = models.AutoField(primary_key=True)
    lrn = models.CharField(max_length=12)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    remarks = models.TextField(blank=True, null=True)
    recorded_by = models.IntegerField()

    class Meta:
        db_table = 'attendance_mark'
        unique_together = ('lrn', 'date')

    def __str__(self):
        return f"{self.lrn} {self.date} {self.status}"


class SchoolCalendarException(models.Model):
    """A date that breaks the Mon-Fri school-day default for one school -
    a Saturday added as a make-up class, or a weekday excluded as a
    holiday. Empty by default; most months need no rows here at all."""

    exception_id = models.AutoField(primary_key=True)
    school_profile_id = models.IntegerField()
    date = models.DateField()
    is_school_day = models.BooleanField()

    class Meta:
        db_table = 'school_calendar_exception'
        unique_together = ('school_profile_id', 'date')

    def __str__(self):
        return f"{self.school_profile_id} {self.date} {'school day' if self.is_school_day else 'no school'}"