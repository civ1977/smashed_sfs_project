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
    school_profile_id = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'teacher_adviser'

    def __str__(self):
        return self.full_name