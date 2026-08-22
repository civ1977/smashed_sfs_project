from django.urls import path
from . import views

urlpatterns = [
    path('', views.lesson_planning_home, name='lesson_planning_home'),
    path('connect/', views.connect_ai, name='lesson_planning_connect'),
    path('disconnect/', views.disconnect_ai, name='lesson_planning_disconnect'),
    path('generate/', views.generate_lesson_plan, name='lesson_planning_generate'),
    path('download/', views.download_lesson_plan, name='lesson_planning_download'),
]
