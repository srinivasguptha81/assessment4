from django import forms
from .models import AttendanceSession, AttendanceRecord, Course
from django.utils import timezone


class AttendanceSessionForm(forms.ModelForm):
    """Faculty uses this to start a new attendance session"""

    class Meta:
        model  = AttendanceSession
        fields = ['course', 'date', 'start_time', 'end_time']
        widgets = {
            'date':       forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time':   forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, faculty, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Faculty only sees their own courses
        self.fields['course'].queryset = Course.objects.filter(faculty=faculty)


class BulkAttendanceForm(forms.Form):
    """
    Dynamically generated form — one radio button per student.
    Faculty sees every enrolled student and marks P/A/L/E
    """
    def __init__(self, session, *args, **kwargs):
        super().__init__(*args, **kwargs)
        students = session.course.students.all().order_by('user__last_name')

        for student in students:
            self.fields[f'student_{student.id}'] = forms.ChoiceField(
                label=str(student),
                choices=AttendanceRecord.STATUS_CHOICES,
                initial='P',
                widget=forms.RadioSelect(attrs={'class': 'attendance-radio'}),
            )


class ImageUploadForm(forms.Form):
    """For AI face recognition — faculty uploads class photo"""
    image = forms.ImageField(
        label='Upload Class Photo',
        help_text='System will auto-detect students from this image'
    )