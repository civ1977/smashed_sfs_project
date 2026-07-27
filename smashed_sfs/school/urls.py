from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.school_dashboard, name='school_dashboard'),
    path('students/', views.school_student_list, name='school_student_list'),
    path('sections/', views.school_sections, name='school_sections'),
    path('sections/<int:section_id>/reassign/', views.reassign_section_adviser, name='reassign_section_adviser'),
    path('accounts/', views.school_accounts, name='school_accounts'),
    path('accounts/<int:teacher_id>/toggle-active/', views.toggle_teacher_active, name='toggle_teacher_active'),
    path('accounts/<int:teacher_id>/reassign-section/', views.reassign_teacher_section, name='reassign_teacher_section'),
]
