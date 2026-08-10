from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include, reverse_lazy
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
    path('about/', views.about, name='about'),
    path('how-it-works/', views.how_it_works, name='how_it_works'),
    path('tutorials/', views.tutorials, name='tutorials'),
    path('pricing/', views.pricing, name='pricing'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('contact-us/', views.contact_us, name='contact_us'),
    path('advisory/', views.dashboard, name='dashboard'),
    path('complete-profile/', views.complete_profile, name='complete_profile'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        email_template_name='accounts/password_reset_email.html',
        subject_template_name='accounts/password_reset_subject.txt',
        success_url=reverse_lazy('password_reset_done'),
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url=reverse_lazy('password_reset_complete'),
    ), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),
    path('ancillary/', views.ancillary, name='ancillary'),
    path('tools/', views.tools, name='tools'),
    path('tools/dtr/', views.daily_time_record, name='daily_time_record'),
    path('tools/dtr/upload/', views.upload_dtr, name='upload_dtr'),
    path('tools/dtr/rename/', views.rename_dtr_employee, name='rename_dtr_employee'),
    path('tools/dtr/save-cell/', views.save_dtr_cell, name='save_dtr_cell'),
    
    path('students/', include('students.urls')),
    path('grades/', include('grades.urls')),
    path('reports/', include('reports.urls')),
    path('school/', include('school.urls')),
    path('portal/', include('portal.urls')),
]