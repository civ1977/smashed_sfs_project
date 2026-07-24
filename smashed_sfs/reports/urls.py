from django.urls import path
from . import views

urlpatterns = [
    path('select-student/', views.select_student_for_report, name='select_student_report'),
    path('sf9/<str:student_lrn>/', views.view_sf9, name='view_sf9'),
    path('sf10/<str:student_lrn>/', views.view_sf10, name='view_sf10'),
    path('sf9-excel/<str:student_lrn>/<int:term>/', views.generate_sf9_excel, name='generate_sf9_excel'),
    path('sf10-excel/<str:student_lrn>/', views.generate_sf10_excel, name='generate_sf10_excel'),
]