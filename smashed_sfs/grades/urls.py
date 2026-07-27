from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_grades, name='upload_grades'),
    path('save/', views.save_grades, name='save_grades'),
    path('view/<str:lrn>/', views.view_grades, name='view_grades'),

    path('attendance/grid/', views.attendance_grid, name='attendance_grid'),
    path('attendance/grid/save/', views.attendance_grid_save, name='attendance_grid_save'),
    path('attendance/holiday/add/', views.add_holiday, name='add_holiday'),
    path('attendance/holiday/remove/', views.remove_holiday, name='remove_holiday'),
    path('attendance/view/<str:lrn>/', views.view_attendance, name='view_attendance'),
]