from django.urls import path
from . import views

urlpatterns = [
    path('', views.select_student_for_report, name='select_student_report'),
    path('subject-statistics/', views.subject_statistics_report, name='subject_statistics_report'),
    path('report-cards/', views.report_cards, name='report_cards'),
    path('summary-of-ratings/', views.summary_of_ratings, name='summary_of_ratings'),
    path('summary-of-ratings/export/', views.export_summary_of_ratings, name='export_summary_of_ratings'),
    path('sf7/', views.view_sf7, name='view_sf7'),
    path('sf9/<str:student_lrn>/', views.view_sf9, name='view_sf9'),
    path('sf10/<str:student_lrn>/', views.view_sf10, name='view_sf10'),
    path('ratings/<str:student_lrn>/', views.view_student_ratings, name='view_student_ratings'),
    path('sf2/<int:year>/<int:month>/', views.export_sf2, name='export_sf2'),
]