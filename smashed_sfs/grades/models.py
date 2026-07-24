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

    class Meta:
        db_table = 'subject_mapping'

    def __str__(self):
        return f"{self.subject_number}: {self.subject_name}"


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


class Attendance(models.Model):
    attendance_id = models.AutoField(primary_key=True)
    lrn = models.CharField(max_length=12)
    term = models.IntegerField()
    days_present = models.IntegerField(default=0)
    days_absent = models.IntegerField(default=0)
    uploaded_by = models.IntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'attendance'