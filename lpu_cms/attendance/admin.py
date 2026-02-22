from django.contrib import admin
from .models import (
    Department, Faculty, Student, Course,
    AttendanceSession, AttendanceRecord,
    AbsenteeAlert, AttendanceSummary
)

admin.site.register(Department)
admin.site.register(Faculty)
admin.site.register(Student)
admin.site.register(Course)
admin.site.register(AttendanceSession)
admin.site.register(AttendanceRecord)
admin.site.register(AbsenteeAlert)
admin.site.register(AttendanceSummary)