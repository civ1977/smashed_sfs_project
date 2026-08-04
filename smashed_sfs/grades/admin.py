from django.contrib import admin
from .models import (
    SubjectMapping, TeacherSubjectAssignment, Grade, Attendance,
    AttendanceMark, SchoolCalendarException,
)


@admin.register(SubjectMapping)
class SubjectMappingAdmin(admin.ModelAdmin):
    list_display = ('mapping_id', 'subject_name', 'subject_number', 'grade_level', 'strand', 'school_profile_id', 'is_active')
    search_fields = ('subject_name',)
    list_filter = ('grade_level', 'strand', 'is_active')


@admin.register(TeacherSubjectAssignment)
class TeacherSubjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ('assignment_id', 'teacher_id', 'section_id', 'mapping_id')


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('grade_id', 'lrn', 'mapping_id', 'term', 'grade', 'uploaded_by', 'updated_at')
    search_fields = ('lrn',)
    list_filter = ('term',)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('attendance_id', 'lrn', 'month', 'days_present', 'days_absent', 'uploaded_by')
    search_fields = ('lrn',)
    list_filter = ('month',)


@admin.register(AttendanceMark)
class AttendanceMarkAdmin(admin.ModelAdmin):
    list_display = ('mark_id', 'lrn', 'date', 'status', 'recorded_by')
    search_fields = ('lrn',)
    list_filter = ('status',)


@admin.register(SchoolCalendarException)
class SchoolCalendarExceptionAdmin(admin.ModelAdmin):
    list_display = ('exception_id', 'school_profile_id', 'date', 'is_school_day')
    list_filter = ('is_school_day',)
