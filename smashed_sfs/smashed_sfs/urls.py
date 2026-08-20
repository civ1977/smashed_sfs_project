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
    path('register/pending/', views.registration_pending, name='registration_pending'),
    path('register/verify/<uidb64>/<token>/', views.verify_email, name='verify_email'),
    path('register/resend-verification/', views.resend_verification, name='resend_verification'),
    path('register/finish-social-signup/', views.finish_social_signup, name='finish_social_signup'),
    # Only the provider connect/callback endpoints (e.g.
    # /accounts/google/login/, /accounts/facebook/login/callback/) -
    # deliberately not the full allauth.urls, which would also add a
    # second, competing set of login/signup/password pages on top of this
    # app's own (see settings.py's comment above AUTHENTICATION_BACKENDS).
    # allauth.socialaccount.urls alone only has the cancelled/error/signup/
    # connections views, not the actual per-provider login/callback ones -
    # those live in each provider's own urls module (mirroring what
    # allauth.urls itself does internally via build_provider_urlpatterns).
    path('accounts/', include('allauth.socialaccount.urls')),
    path('accounts/', include('allauth.socialaccount.providers.google.urls')),
    path('accounts/', include('allauth.socialaccount.providers.facebook.urls')),
    path('about/', views.about, name='about'),
    path('how-it-works/', views.how_it_works, name='how_it_works'),
    path('tutorials/', views.tutorials, name='tutorials'),
    path('pricing/', views.pricing, name='pricing'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('user-agreement/', views.user_agreement, name='user_agreement'),
    path('user-agreement/embed/', views.user_agreement_embed, name='user_agreement_embed'),
    path('contact-us/', views.contact_us, name='contact_us'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('account/', views.account_settings, name='account_settings'),
    path('complete-profile/', views.complete_profile, name='complete_profile'),
    path('masterlist/divisions/', views.masterlist_divisions, name='masterlist_divisions'),
    path('masterlist/municipalities/', views.masterlist_municipalities, name='masterlist_municipalities'),
    path('masterlist/districts/', views.masterlist_districts, name='masterlist_districts'),
    path('masterlist/schools/', views.masterlist_schools, name='masterlist_schools'),
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
    path('tools/dtr/save-cell/', views.save_dtr_cell, name='save_dtr_cell'),
    path('tools/dtr/bulk-fill-lunch/', views.bulk_fill_dtr_lunch, name='bulk_fill_dtr_lunch'),
    path('tools/dtr/save-signature/', views.save_dtr_signature, name='save_dtr_signature'),
    
    path('students/', include('students.urls')),
    path('grades/', include('grades.urls')),
    path('reports/', include('reports.urls')),
    path('school/', include('school.urls')),
    path('portal/', include('portal.urls')),
]