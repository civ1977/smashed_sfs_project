from django.urls import path
from . import views

urlpatterns = [
    path('', views.assessment_home, name='assessment_home'),
    path('generate/', views.generate_assessment, name='assessment_generate'),
    path('download/', views.download_assessment, name='assessment_download'),
]
