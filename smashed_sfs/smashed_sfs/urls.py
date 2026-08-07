from django.contrib import admin
from django.urls import path, include
from accounts import views
from . import admin_grouping, admin_monitoring, admin_backup

admin_grouping.apply()
admin_monitoring.apply()
admin_backup.apply()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.landing_page, name='landing'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register, name='register'),
    path('advisory/', views.dashboard, name='dashboard'),
    path('complete-profile/', views.complete_profile, name='complete_profile'),
    path('logout/', views.logout_view, name='logout'),
    path('ancillary/', views.ancillary, name='ancillary'),
    path('tools/', views.tools, name='tools'),
    
    path('students/', include('students.urls')),
    path('grades/', include('grades.urls')),
    path('reports/', include('reports.urls')),
    path('school/', include('school.urls')),
    path('portal/', include('portal.urls')),
]