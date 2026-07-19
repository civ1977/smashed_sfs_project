from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_grades, name='upload_grades'),
]