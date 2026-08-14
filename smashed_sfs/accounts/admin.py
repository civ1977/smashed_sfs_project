from django.contrib import admin

from students.models import SchoolProfile
from .models import Teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('teacher_id', 'username', 'full_name', 'position', 'role', 'school_name', 'email', 'is_active')
    search_fields = ('username', 'full_name', 'email')
    list_filter = ('school_profile_id', 'role', 'is_active')

    def school_name(self, obj):
        if not obj.school_profile_id:
            return '—'
        school = SchoolProfile.objects.filter(profile_id=obj.school_profile_id).first()
        return school.school_name if school else f'#{obj.school_profile_id}'
    school_name.short_description = 'School'
