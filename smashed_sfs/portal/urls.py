from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.portal_register, name='portal_register'),
    path('pending/', views.portal_pending, name='portal_pending'),
    path('dashboard/', views.portal_dashboard, name='portal_dashboard'),
    path('grades/', views.portal_grades, name='portal_grades'),
]
