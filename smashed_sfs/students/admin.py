from django.contrib import admin
from .models import SchoolProfile, Section, Student


@admin.register(SchoolProfile)
class SchoolProfileAdmin(admin.ModelAdmin):
    list_display = ('profile_id', 'school_name', 'school_id', 'school_year')
    search_fields = ('school_name', 'school_id')


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('section_id', 'section_name', 'grade_level', 'track', 'strand', 'modality', 'adviser_id', 'school_profile_id')
    search_fields = ('section_name',)
    list_filter = ('grade_level', 'track', 'strand')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('lrn', 'surname', 'name', 'section_id', 'adviser_id')
    search_fields = ('lrn', 'surname', 'name')
