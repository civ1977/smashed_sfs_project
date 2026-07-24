from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_grades, name='upload_grades'),
    path('save/', views.save_grades, name='save_grades'),
    path('view/<str:lrn>/', views.view_grades, name='view_grades'),
]