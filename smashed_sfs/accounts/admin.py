from django.contrib import admin
from .models import Teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('teacher_id', 'username', 'full_name', 'position', 'email', 'school_profile_id', 'is_active')
    search_fields = ('username', 'full_name', 'email')
