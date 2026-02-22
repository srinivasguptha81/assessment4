from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# ─────────────────────────────────────────
# DEPARTMENT
# ─────────────────────────────────────────
class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return self.name


# ─────────────────────────────────────────
# FACULTY
# ─────────────────────────────────────────
class Faculty(models.Model):
    user       = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    faculty_id = models.CharField(max_length=20, unique=True)
    phone      = models.CharField(max_length=15, blank=True)
    photo      = models.ImageField(upload_to='faculty_photos/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.faculty_id})"


# ─────────────────────────────────────────
# STUDENT
# ─────────────────────────────────────────
class Student(models.Model):
    user           = models.OneToOneField(User, on_delete=models.CASCADE)
    department     = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    registration_no = models.CharField(max_length=20, unique=True)
    section        = models.CharField(max_length=10)
    semester       = models.IntegerField(default=1)
    parent_email   = models.EmailField(blank=True)   # for notifications
    parent_phone   = models.CharField(max_length=15, blank=True)
    photo          = models.ImageField(upload_to='student_photos/', blank=True, null=True)
    # photo is used later for AI face recognition

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.registration_no})"


# ─────────────────────────────────────────
# COURSE
# ─────────────────────────────────────────
class Course(models.Model):
    name        = models.CharField(max_length=100)
    code        = models.CharField(max_length=20, unique=True)
    department  = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    faculty     = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True)
    students    = models.ManyToManyField(Student, related_name='courses', blank=True)
    total_classes = models.IntegerField(default=0)  # increments each session

    def __str__(self):
        return f"{self.code} — {self.name}"


# ─────────────────────────────────────────
# ATTENDANCE SESSION
# A session = one class held on one date
# Faculty creates this, then marks students
# ─────────────────────────────────────────
class AttendanceSession(models.Model):
    course      = models.ForeignKey(Course, on_delete=models.CASCADE)
    date        = models.DateField(default=timezone.now)
    start_time  = models.TimeField()
    end_time    = models.TimeField()
    created_by  = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True)
    is_makeup   = models.BooleanField(default=False)  # used in makeup module later

    class Meta:
        unique_together = ('course', 'date', 'start_time')
        ordering = ['-date', '-start_time']

    def __str__(self):
        return f"{self.course.code} | {self.date} {self.start_time}"


# ─────────────────────────────────────────
# ATTENDANCE RECORD
# One row per student per session
# ─────────────────────────────────────────
class AttendanceRecord(models.Model):

    STATUS_CHOICES = [
        ('P', 'Present'),
        ('A', 'Absent'),
        ('L', 'Late'),
        ('E', 'Excused'),
    ]

    session   = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    student   = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    status    = models.CharField(max_length=1, choices=STATUS_CHOICES, default='A')
    marked_at = models.DateTimeField(auto_now_add=True)
    # For AI face recognition — stores the uploaded image
    face_image = models.ImageField(upload_to='face_captures/', blank=True, null=True)
    ai_verified = models.BooleanField(default=False)  # True if marked by AI

    class Meta:
        unique_together = ('session', 'student')  # can't mark same student twice
        ordering = ['student__user__last_name']

    def __str__(self):
        return f"{self.student} — {self.session} — {self.get_status_display()}"


# ─────────────────────────────────────────
# ABSENTEE ALERT
# Logs every notification sent
# ─────────────────────────────────────────
class AbsenteeAlert(models.Model):

    CHANNEL_CHOICES = [
        ('EMAIL', 'Email'),
        ('SMS',   'SMS'),
        ('BOTH',  'Both'),
    ]

    record     = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE)
    sent_at    = models.DateTimeField(auto_now_add=True)
    channel    = models.CharField(max_length=5, choices=CHANNEL_CHOICES, default='EMAIL')
    recipient  = models.EmailField()   # parent or student email
    message    = models.TextField()
    is_sent    = models.BooleanField(default=False)

    def __str__(self):
        return f"Alert → {self.recipient} @ {self.sent_at}"


# ─────────────────────────────────────────
# ATTENDANCE SUMMARY (computed/cached)
# Tracks % attendance per student per course
# ─────────────────────────────────────────
class AttendanceSummary(models.Model):
    student         = models.ForeignKey(Student, on_delete=models.CASCADE)
    course          = models.ForeignKey(Course, on_delete=models.CASCADE)
    total_classes   = models.IntegerField(default=0)
    classes_attended = models.IntegerField(default=0)
    last_updated    = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'course')

    @property
    def percentage(self):
        if self.total_classes == 0:
            return 0
        return round((self.classes_attended / self.total_classes) * 100, 2)

    @property
    def is_below_threshold(self):
        return self.percentage < 75  # LPU standard

    def __str__(self):
        return f"{self.student} | {self.course.code} | {self.percentage}%"