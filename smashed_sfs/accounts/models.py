from django.db import models
from django.contrib.auth.models import User

class Teacher(models.Model):
    teacher_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=255)
    full_name = models.CharField(max_length=100)
    position = models.CharField(max_length=100)
    email = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(blank=True, null=True)
    school_profile_id = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = 'teacher_adviser'

    def __str__(self):
        return self.full_name