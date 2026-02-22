from attendance.models import Faculty, Student

def user_roles(request):
    """
    Makes role variables available in every template automatically.
    Add to settings.py TEMPLATES context_processors list.
    """
    if not request.user.is_authenticated:
        return {}

    faculty = None
    student = None
    is_stall_owner = False

    try:
        faculty = Faculty.objects.get(user=request.user)
    except Faculty.DoesNotExist:
        pass

    try:
        student = Student.objects.get(user=request.user)
    except Student.DoesNotExist:
        pass

    try:
        from food.models import FoodStall
        FoodStall.objects.get(owner=request.user)
        is_stall_owner = True
    except Exception:
        pass

    return {
        'faculty':        faculty,
        'student':        student,
        'is_stall_owner': is_stall_owner,
    }