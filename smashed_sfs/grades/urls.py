from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_grades, name='upload_grades'),
    path('save/', views.save_grades, name='save_grades'),
    path('view/<str:lrn>/', views.view_grades, name='view_grades'),
    path('rankings/', views.view_rankings, name='view_rankings'),
    path('subjects/arrange/', views.arrange_subjects, name='arrange_subjects'),
    path('subjects/arrange/heading/<str:group>/toggle/', views.toggle_subject_group_heading, name='toggle_subject_group_heading'),
    path('subject/<int:mapping_id>/exclude/', views.exclude_subject_term, name='exclude_subject_term'),
    path('subject/<int:mapping_id>/restore/', views.restore_subject_term, name='restore_subject_term'),
    path('term-remark/save/', views.save_term_remark, name='save_term_remark'),

    path('my-subject-teaching/', views.my_subject_teaching, name='my_subject_teaching'),
    path('my-subject-teaching/<int:assignment_id>/', views.subject_teaching_grades, name='subject_teaching_grades'),

    path('attendance/grid/', views.attendance_grid, name='attendance_grid'),
    path('attendance/grid/save/', views.attendance_grid_save, name='attendance_grid_save'),
    path('attendance/holiday/add/', views.add_holiday, name='add_holiday'),
    path('attendance/holiday/remove/', views.remove_holiday, name='remove_holiday'),
    path('attendance/view/<str:lrn>/', views.view_attendance, name='view_attendance'),
]