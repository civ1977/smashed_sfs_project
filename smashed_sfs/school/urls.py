from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.school_dashboard, name='school_dashboard'),
    path('students/', views.school_student_list, name='school_student_list'),
    path('sections/', views.school_sections, name='school_sections'),
    path('sections/<int:section_id>/reassign/', views.reassign_section_adviser, name='reassign_section_adviser'),
    path('accounts/', views.school_accounts, name='school_accounts'),
    path('accounts/<int:teacher_id>/toggle-active/', views.toggle_teacher_active, name='toggle_teacher_active'),
    path('student-accounts/<int:account_id>/toggle-active/', views.toggle_student_account_active, name='toggle_student_account_active'),
    path('accounts/<int:teacher_id>/reassign-section/', views.reassign_teacher_section, name='reassign_teacher_section'),
    path('assignments/', views.school_assignments, name='school_assignments'),
    path('assignments/<int:assignment_id>/remove/', views.remove_teacher_subject_assignment, name='remove_teacher_subject_assignment'),
    path('my-assignments/', views.adviser_subject_assignments, name='adviser_subject_assignments'),
    path('my-assignments/<int:assignment_id>/remove/', views.remove_adviser_subject_assignment, name='remove_adviser_subject_assignment'),
    path('my-section/edit/', views.edit_my_section, name='edit_my_section'),
    path('profile/edit/', views.edit_school_profile, name='edit_school_profile'),
]
