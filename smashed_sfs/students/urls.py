from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_students, name='upload_students'),
    path('save/', views.save_students, name='save_students'),
    path('list/', views.student_list, name='student_list'),
]