from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import SchoolProfile, Section, Student


@admin.register(SchoolProfile)
class SchoolProfileAdmin(admin.ModelAdmin):
    list_display = ('profile_id', 'school_name', 'school_id', 'school_year', 'view_accounts')
    search_fields = ('school_name', 'school_id')

    def view_accounts(self, obj):
        url = reverse('admin:accounts_teacher_changelist')
        return format_html(
            '<a class="button" href="{}?school_profile_id__exact={}">View Accounts</a>',
            url, obj.profile_id,
        )
    view_accounts.short_description = 'Accounts'


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('section_id', 'section_name', 'grade_level', 'track', 'strand', 'modality', 'adviser_id', 'school_profile_id')
    search_fields = ('section_name',)
    list_filter = ('grade_level', 'track', 'strand')


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('lrn', 'surname', 'name', 'section_id', 'adviser_id')
    search_fields = ('lrn', 'surname', 'name')
