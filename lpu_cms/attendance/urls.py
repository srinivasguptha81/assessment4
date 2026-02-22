from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('',                                     views.dashboard,              name='dashboard'),
    path('admin-dashboard/',                     views.admin_dashboard,        name='admin_dashboard'),
    path('faculty/',                             views.faculty_dashboard,      name='faculty_dashboard'),
    path('session/start/',                       views.start_session,          name='start_session'),
    path('session/<int:session_id>/mark/',       views.mark_attendance,        name='mark_attendance'),
    path('session/<int:session_id>/ai-mark/',    views.ai_mark_attendance,     name='ai_mark'),  # ← new
    path('session/<int:session_id>/',            views.session_detail,         name='session_detail'),
    path('course/<int:course_id>/report/',       views.course_attendance_report, name='course_report'),
    path('student/',                             views.student_dashboard,      name='student_dashboard'),
    path('student/course/<int:course_id>/',      views.student_course_detail,  name='student_course_detail'),
    path('api/absentees/<int:session_id>/',      views.detect_absentees,       name='detect_absentees'),
]