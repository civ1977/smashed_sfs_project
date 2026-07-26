from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_grades, name='upload_grades'),
    path('save/', views.save_grades, name='save_grades'),
    path('view/<str:lrn>/', views.view_grades, name='view_grades'),

    path('attendance/upload/', views.upload_attendance, name='upload_attendance'),
    path('attendance/template/', views.download_attendance_template, name='download_attendance_template'),
    path('attendance/save/', views.save_attendance, name='save_attendance'),
    path('attendance/view/<str:lrn>/', views.view_attendance, name='view_attendance'),
]