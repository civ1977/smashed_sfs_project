from django.urls import path
from . import views

urlpatterns = [
    path('select-student/', views.select_student_for_report, name='select_student_report'),
    path('sf9/<str:student_lrn>/', views.view_sf9, name='view_sf9'),
    path('sf10/<str:student_lrn>/', views.view_sf10, name='view_sf10'),
    path('sf2/<int:year>/<int:month>/', views.export_sf2, name='export_sf2'),
]