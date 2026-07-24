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
    adviser_id = models.IntegerField()
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

    class Meta:
        db_table = 'student'

    def __str__(self):
        return f"{self.surname}, {self.name} ({self.lrn})"