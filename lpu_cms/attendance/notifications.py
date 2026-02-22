# attendance/notifications.py
"""
Notification Service
─────────────────────
Handles all automated alerts:
- Absentee email to student + parent
- Low attendance warning (below 75%)
- Daily absentee summary to faculty

In development: uses Django's console email backend
In production:  swap for SendGrid / SMTP
"""

from django.core.mail import send_mail, send_mass_mail
from django.conf import settings
from django.utils import timezone
from .models import AbsenteeAlert, AttendanceSummary


# ─────────────────────────────────────
# SINGLE ABSENTEE ALERT
# ─────────────────────────────────────

def notify_absent_student(record):
    """
    Sends absence notification to student and optionally their parent.
    Logs the alert in AbsenteeAlert table.

    Called automatically after attendance is saved.
    """
    student = record.student
    session = record.session
    course  = session.course

    subject = f"[LPU] Absence Recorded — {course.code}"

    student_message = f"""Dear {student.user.get_full_name()},

This is an automated notification from the LPU Smart Attendance System.

You were marked ABSENT for the following class:

  Course  : {course.name} ({course.code})
  Date    : {session.date.strftime('%d %B %Y')}
  Time    : {session.start_time.strftime('%I:%M %p')} – {session.end_time.strftime('%I:%M %p')}
  Faculty : {session.created_by.user.get_full_name()}

If this is incorrect, please contact your faculty immediately.

Current Attendance Status:
"""

    # Append attendance summary if available
    try:
        summary = AttendanceSummary.objects.get(student=student, course=course)
        student_message += f"""
  Classes Held     : {summary.total_classes}
  Classes Attended : {summary.classes_attended}
  Attendance %     : {summary.percentage}%
  Status           : {'⚠ BELOW 75% — At Risk' if summary.is_below_threshold else '✓ Safe'}
"""
    except AttendanceSummary.DoesNotExist:
        pass

    student_message += "\nRegards,\nLPU Smart Campus System\n(This is an automated message)"

    # ── Parent message (slightly different tone) ──
    parent_message = f"""Dear Parent/Guardian of {student.user.get_full_name()},

Your ward has been marked ABSENT in the following class at Lovely Professional University:

  Course  : {course.name} ({course.code})
  Date    : {session.date.strftime('%d %B %Y')}
  Time    : {session.start_time.strftime('%I:%M %p')} – {session.end_time.strftime('%I:%M %p')}

Please ensure regular attendance. Students with less than 75% attendance
may be detained from examinations.

Regards,
LPU Smart Campus System"""

    # ── Collect recipients ──
    recipients = []
    if student.user.email:
        recipients.append(student.user.email)

    # ── Send emails ──
    sent = False
    try:
        send_mail(
            subject,
            student_message,
            'noreply@lpu.in',
            recipients,
            fail_silently=True
        )

        # Notify parent separately
        if student.parent_email:
            send_mail(
                subject,
                parent_message,
                'noreply@lpu.in',
                [student.parent_email],
                fail_silently=True
            )

        sent = True
    except Exception as e:
        print(f"[NOTIFY] Email failed: {e}")

    # ── Log the alert ──
    AbsenteeAlert.objects.create(
        record    = record,
        channel   = 'EMAIL',
        recipient = student.user.email or 'no-email',
        message   = student_message,
        is_sent   = sent
    )

    return sent


# ─────────────────────────────────────
# LOW ATTENDANCE WARNING
# ─────────────────────────────────────

def notify_low_attendance(summary):
    """
    Sends a warning when a student's attendance drops below 75%.
    Called from update_summary() in views.py whenever attendance is recalculated.
    """
    student = summary.student
    course  = summary.course

    subject = f"[LPU] ⚠ Low Attendance Warning — {course.code}"
    message = f"""Dear {student.user.get_full_name()},

WARNING: Your attendance in {course.name} ({course.code}) has dropped below 75%.

  Current Attendance : {summary.percentage}%
  Classes Attended   : {summary.classes_attended} / {summary.total_classes}

Students with less than 75% attendance risk being DETAINED from examinations.

Please contact your faculty or the registrar's office immediately.

Regards,
LPU Smart Campus System"""

    recipients = [r for r in [student.user.email, student.parent_email] if r]

    if recipients:
        send_mail(subject, message, 'noreply@lpu.in', recipients, fail_silently=True)
        print(f"[NOTIFY] Low attendance warning sent to {student.user.get_full_name()}")


# ─────────────────────────────────────
# FACULTY DAILY SUMMARY
# ─────────────────────────────────────

def send_faculty_summary(session, absent_records):
    """
    Sends a summary email to faculty after attendance is marked.
    Lists all absentees for the session.
    """
    faculty  = session.created_by
    course   = session.course
    total    = course.students.count()
    absent_n = len(absent_records)
    present_n = total - absent_n

    if not faculty.user.email:
        return

    subject = f"[LPU] Attendance Summary — {course.code} | {session.date}"

    absentee_list = "\n".join([
        f"  - {r.student.user.get_full_name()} ({r.student.registration_no})"
        for r in absent_records
    ]) or "  None"

    message = f"""Dear {faculty.user.get_full_name()},

Attendance has been recorded for your class:

  Course  : {course.name} ({course.code})
  Date    : {session.date.strftime('%d %B %Y')}
  Time    : {session.start_time.strftime('%I:%M %p')} – {session.end_time.strftime('%I:%M %p')}

SUMMARY:
  Total Students  : {total}
  Present         : {present_n}
  Absent          : {absent_n}
  Attendance Rate : {round(present_n/total*100,1) if total else 0}%

ABSENTEES:
{absentee_list}

Notifications have been sent to all absentees and their parents.

Regards,
LPU Smart Campus System"""

    send_mail(subject, message, 'noreply@lpu.in', [faculty.user.email], fail_silently=True)