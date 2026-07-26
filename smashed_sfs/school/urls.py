from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.school_dashboard, name='school_dashboard'),
    path('students/', views.school_student_list, name='school_student_list'),
]
