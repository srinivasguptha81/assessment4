from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Count, Q
from .ai_service import recognize_faces_in_image, get_known_encodings
from .notifications import notify_absent_student, notify_low_attendance, send_faculty_summary


from .models import (
    Faculty, Student, Course, AttendanceSession,
    AttendanceRecord, AbsenteeAlert, AttendanceSummary
)
from .forms import AttendanceSessionForm, BulkAttendanceForm, ImageUploadForm
import json


# ─────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────

def get_faculty(user):
    """Returns Faculty object or None"""
    try:
        return Faculty.objects.get(user=user)
    except Faculty.DoesNotExist:
        return None


def get_student(user):
    """Returns Student object or None"""
    try:
        return Student.objects.get(user=user)
    except Student.DoesNotExist:
        return None


def update_summary(student, course):
    total    = AttendanceSession.objects.filter(course=course).count()
    attended = AttendanceRecord.objects.filter(
        student=student,
        session__course=course,
        status='P'
    ).count()

    summary, _ = AttendanceSummary.objects.get_or_create(
        student=student, course=course
    )
    summary.total_classes    = total
    summary.classes_attended = attended
    summary.save()

    # Auto-trigger low attendance warning
    if summary.is_below_threshold and total >= 3:
        notify_low_attendance(summary)

    return summary



def send_absentee_notification(record):
    notify_absent_student(record)


# ─────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────

@login_required
def dashboard(request):
    """
    Redirects to the correct dashboard based on role.
    Admin → admin dashboard
    Faculty → faculty dashboard
    Student → student dashboard
    """
    if request.user.is_staff:
        return redirect('attendance:admin_dashboard')

    faculty = get_faculty(request.user)
    if faculty:
        return redirect('attendance:faculty_dashboard')

    student = get_student(request.user)
    if student:
        return redirect('attendance:student_dashboard')

    return render(request, 'attendance/no_role.html')


# ─────────────────────────────────────────────────────
# ADMIN DASHBOARD
# ─────────────────────────────────────────────────────

@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        return redirect('attendance:dashboard')

    # Overall stats
    total_students = Student.objects.count()
    total_faculty  = Faculty.objects.count()
    total_courses  = Course.objects.count()
    total_sessions = AttendanceSession.objects.count()

    # Students below 75% attendance
    low_attendance = AttendanceSummary.objects.filter(
        total_classes__gt=0
    ).select_related('student', 'course')

    low_attendance = [s for s in low_attendance if s.is_below_threshold]

    # Recent sessions
    recent_sessions = AttendanceSession.objects.select_related(
        'course', 'created_by'
    ).order_by('-date', '-start_time')[:10]

    context = {
        'total_students':  total_students,
        'total_faculty':   total_faculty,
        'total_courses':   total_courses,
        'total_sessions':  total_sessions,
        'low_attendance':  low_attendance,
        'recent_sessions': recent_sessions,
    }
    return render(request, 'attendance/admin_dashboard.html', context)


# ─────────────────────────────────────────────────────
# FACULTY VIEWS
# ─────────────────────────────────────────────────────

@login_required
def faculty_dashboard(request):
    faculty = get_faculty(request.user)
    if not faculty:
        return redirect('attendance:dashboard')

    courses         = Course.objects.filter(faculty=faculty)
    recent_sessions = AttendanceSession.objects.filter(
        created_by=faculty
    ).order_by('-date', '-start_time')[:8]

    # Count absentees in last 7 days
    from datetime import timedelta
    week_ago = timezone.now().date() - timedelta(days=7)
    recent_absences = AttendanceRecord.objects.filter(
        session__created_by=faculty,
        session__date__gte=week_ago,
        status='A'
    ).count()

    context = {
        'faculty':         faculty,
        'courses':         courses,
        'recent_sessions': recent_sessions,
        'recent_absences': recent_absences,
    }
    return render(request, 'attendance/faculty_dashboard.html', context)


@login_required
def start_session(request):
    faculty = get_faculty(request.user)
    if not faculty:
        return redirect('attendance:dashboard')

    if request.method == 'POST':
        form = AttendanceSessionForm(faculty, request.POST)
        if form.is_valid():
            session            = form.save(commit=False)
            session.created_by = faculty
            session.save()

            mark_method = request.POST.get('mark_method', 'manual')

            messages.success(request, f'Session created for {session.course.code}')

            # Redirect based on faculty's choice
            if mark_method == 'ai':
                return redirect('attendance:ai_mark', session_id=session.id)
            else:
                return redirect('attendance:mark_attendance', session_id=session.id)
    else:
        form = AttendanceSessionForm(faculty)

    return render(request, 'attendance/start_session.html', {'form': form})

@login_required
def mark_attendance(request, session_id):
    """
    Main attendance marking view.
    Shows all enrolled students — faculty marks each one P/A/L/E.
    One-click bulk submit saves all records instantly.
    """
    faculty = get_faculty(request.user)
    session = get_object_or_404(AttendanceSession, id=session_id)

    # Security: only the session creator can mark
    if session.created_by != faculty:
        messages.error(request, 'You are not authorized to mark this session.')
        return redirect('attendance:faculty_dashboard')

    students = session.course.students.all().order_by('user__last_name')

    # Check if already marked
    existing_records = AttendanceRecord.objects.filter(session=session)
    already_marked   = existing_records.exists()

    if request.method == 'POST':
        form = BulkAttendanceForm(session, request.POST)
        if form.is_valid():
            absentees = []

            for student in students:
                field_name = f'student_{student.id}'
                status     = form.cleaned_data.get(field_name, 'A')

                # update_or_create prevents duplicate entries
                record, created = AttendanceRecord.objects.update_or_create(
                    session=session,
                    student=student,
                    defaults={'status': status}
                )

                if status == 'A':
                    absentees.append(record)

                # Update summary for this student
                update_summary(student, session.course)

            # Auto-send notifications to absentees
            for record in absentees:
                send_absentee_notification(record)

            messages.success(
                request,
                f'Attendance saved! {len(absentees)} absentee(s) notified.'
            )
            return redirect('attendance:session_detail', session_id=session.id)
    else:
        form = BulkAttendanceForm(session)

    context = {
        'session':        session,
        'students':       students,
        'form':           form,
        'already_marked': already_marked,
        'student_count':  students.count(),
    }
    return render(request, 'attendance/mark_attendance.html', context)


@login_required
def session_detail(request, session_id):
    """Shows results of a completed session"""
    session = get_object_or_404(AttendanceSession, id=session_id)
    records = AttendanceRecord.objects.filter(
        session=session
    ).select_related('student__user').order_by('student__user__last_name')

    present  = records.filter(status='P').count()
    absent   = records.filter(status='A').count()
    late     = records.filter(status='L').count()
    excused  = records.filter(status='E').count()
    total    = records.count()

    context = {
        'session': session,
        'records': records,
        'present': present,
        'absent':  absent,
        'late':    late,
        'excused': excused,
        'total':   total,
        'present_pct': round((present / total * 100), 1) if total else 0,
    }
    return render(request, 'attendance/session_detail.html', context)


@login_required
def course_attendance_report(request, course_id):
    """Full attendance report for a course — all students, all sessions"""
    course   = get_object_or_404(Course, id=course_id)
    students = course.students.all().order_by('user__last_name')
    sessions = AttendanceSession.objects.filter(course=course).order_by('date')

    # Build a matrix: rows=students, cols=sessions
    matrix = []
    for student in students:
        row = {'student': student, 'records': []}
        for session in sessions:
            try:
                record = AttendanceRecord.objects.get(session=session, student=student)
                row['records'].append(record.status)
            except AttendanceRecord.DoesNotExist:
                row['records'].append('—')

        summary = AttendanceSummary.objects.filter(
            student=student, course=course
        ).first()
        row['summary'] = summary
        matrix.append(row)

    context = {
        'course':   course,
        'sessions': sessions,
        'matrix':   matrix,
    }
    return render(request, 'attendance/course_report.html', context)


# ─────────────────────────────────────────────────────
# STUDENT VIEWS
# ─────────────────────────────────────────────────────

@login_required
def student_dashboard(request):
    student = get_student(request.user)
    if not student:
        return redirect('attendance:dashboard')

    courses   = student.courses.all()
    summaries = AttendanceSummary.objects.filter(
        student=student
    ).select_related('course')

    # Build summary data with warning flags
    course_data = []
    for summary in summaries:
        course_data.append({
            'course':     summary.course,
            'percentage': summary.percentage,
            'attended':   summary.classes_attended,
            'total':      summary.total_classes,
            'warning':    summary.is_below_threshold,
        })

    # Recent attendance records
    recent_records = AttendanceRecord.objects.filter(
        student=student
    ).select_related('session__course').order_by('-session__date')[:15]

    context = {
        'student':        student,
        'course_data':    course_data,
        'recent_records': recent_records,
    }
    return render(request, 'attendance/student_dashboard.html', context)


@login_required
def student_course_detail(request, course_id):
    """Student views their full attendance for one course"""
    student = get_student(request.user)
    course  = get_object_or_404(Course, id=course_id)

    records = AttendanceRecord.objects.filter(
        student=student,
        session__course=course
    ).select_related('session').order_by('-session__date')

    summary = AttendanceSummary.objects.filter(
        student=student, course=course
    ).first()

    context = {
        'student': student,
        'course':  course,
        'records': records,
        'summary': summary,
    }
    return render(request, 'attendance/student_course_detail.html', context)


# ─────────────────────────────────────────────────────
# ABSENTEE DETECTION API (AJAX)
# ─────────────────────────────────────────────────────

@login_required
def detect_absentees(request, session_id):
    """
    Returns JSON list of absentees for a session.
    Called via AJAX from the mark_attendance page.
    """
    session  = get_object_or_404(AttendanceSession, id=session_id)
    enrolled = set(session.course.students.values_list('id', flat=True))
    marked   = set(
        AttendanceRecord.objects.filter(session=session, status='P')
        .values_list('student_id', flat=True)
    )

    absentee_ids = enrolled - marked
    absentees    = Student.objects.filter(id__in=absentee_ids).select_related('user')

    data = [{
        'id':   s.id,
        'name': s.user.get_full_name(),
        'reg':  s.registration_no,
    } for s in absentees]

    return JsonResponse({'absentees': data, 'count': len(data)})
@login_required
def ai_mark_attendance(request, session_id):
    faculty = get_faculty(request.user)
    session = get_object_or_404(AttendanceSession, id=session_id)

    if session.created_by != faculty:
        messages.error(request, 'Unauthorized.')
        return redirect('attendance:faculty_dashboard')

    if request.method == 'POST':
        form = ImageUploadForm(request.POST, request.FILES)

        if form.is_valid():
            uploaded_image    = request.FILES['image']
            enrolled_students = session.course.students.all()

            if not enrolled_students.exists():
                messages.error(request, 'No students enrolled in this course.')
                return redirect('attendance:faculty_dashboard')

            # Step 1: Build known encodings from student profile photos
            known_encodings = get_known_encodings(enrolled_students)

            if not known_encodings:
                messages.warning(
                    request,
                    f'No student profile photos found. '
                    f'Upload photos for students in admin first. '
                    f'Falling back to manual marking.'
                )
                return redirect('attendance:mark_attendance', session_id=session.id)

            # Step 2: Reset file pointer before passing to AI
            uploaded_image.seek(0)

            # Step 3: Run face recognition
            result = recognize_faces_in_image(uploaded_image, known_encodings)

            if result.get('total_faces', 0) == 0:
                messages.error(
                    request,
                    'No faces detected in the uploaded image. '
                    'Ensure the photo is clear and well-lit.'
                )
                return redirect('attendance:ai_mark', session_id=session.id)

            recognized_ids = result['recognized_ids']
            absentees      = []

            # Step 4: Mark attendance for every enrolled student
            for student in enrolled_students:
                is_present = student.id in recognized_ids
                status     = 'P' if is_present else 'A'

                # Reset file pointer for each save attempt
                uploaded_image.seek(0)

                record, _ = AttendanceRecord.objects.update_or_create(
                    session=session,
                    student=student,
                    defaults={
                        'status':      status,
                        'ai_verified': is_present,
                        'face_image':  uploaded_image if is_present else None,
                    }
                )

                update_summary(student, session.course)

                if status == 'A':
                    absentees.append(record)
                    notify_absent_student(record)

            # Step 5: Notify faculty
            send_faculty_summary(session, absentees)

            present_count = enrolled_students.count() - len(absentees)

            messages.success(
                request,
                f'✅ AI Attendance saved! '
                f'{result["total_faces"]} face(s) detected · '
                f'{present_count} present · '
                f'{len(absentees)} absent · '
                f'{result.get("unrecognized", 0)} unknown face(s).'
            )
            return redirect('attendance:session_detail', session_id=session.id)
    else:
        form = ImageUploadForm()

    context = {
        'form':    form,
        'session': session,
    }
    return render(request, 'attendance/ai_mark.html', context)