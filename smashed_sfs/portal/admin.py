from django.contrib import admin
from .models import StudentAccount


@admin.register(StudentAccount)
class StudentAccountAdmin(admin.ModelAdmin):
    list_display = ('account_id', 'lrn', 'user', 'status', 'is_active', 'requested_at', 'decided_at')
    search_fields = ('lrn',)
    list_filter = ('status', 'is_active')
