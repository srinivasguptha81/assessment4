---

I Built a Campus Resource Tracker That Tells You Which Classrooms Are Overcrowded - Here's How
Django properties, aggregate queries, and why computed fields beat stored ones every time
Walk into any large university's administration office and ask "which classrooms are running at over 90% capacity right now?" and watch the blank stares. The answer probably exists somewhere - buried across spreadsheets, timetable PDFs, and handwritten registers - but nobody can pull it up in seconds.
That was the core problem I set out to solve with Module 3 of my LPU Smart Campus Management System. The assignment asked for a system that manages campus blocks, classrooms, courses, faculty, and students, then calculates capacity utilization and workload distribution. What sounds like a reporting exercise turned into a deep dive into Django's ORM, computed properties, and building dashboards that update themselves.
Here's what I learned.
The Data Structure Problem
Before writing a single view, I had to think carefully about how these entities relate to each other.
The hierarchy goes:
Campus
  └── Blocks (physical buildings)
        └── Classrooms (rooms inside blocks)
              └── Courses (assigned to classrooms + faculty)
                    └── Enrollments (students registered in courses)
And separately:
Faculty → teaches → Courses
Students → enrolled in → Courses (via Enrollment)
WorkloadRecord → calculated from → Faculty's courses
The WorkloadRecord model was an interesting design choice. I could have just calculated workload on the fly every time, but I wanted a record that persists and can be queried - so administrators can see historical workload patterns, not just the current state. I used update_or_create to keep it current:
record, created = WorkloadRecord.objects.update_or_create(
    faculty=faculty,
    semester=1,
    academic_year='2024-25',
    defaults={
        'total_courses':    total_courses,
        'total_hours_week': total_hours_week,
        'total_students':   total_students,
        'status':           status,
    }
)
The defaults parameter is the key - it only updates those fields if the record already exists. If it doesn't exist, it creates a new one with all the fields set. One line pattern, zero duplicate records.

---

The @property Pattern - My Favourite Django Trick
The most satisfying part of this module was how I handled utilization calculations. My first instinct was to store utilization percentages as database fields and update them whenever enrollments changed. This approach has a fatal flaw: data goes stale the moment you forget to update it.
Instead, I made them @property methods on the model:
class Classroom(models.Model):
    capacity = models.IntegerField(default=60)
    @property
    def current_enrollment(self):
        return Enrollment.objects.filter(
            course__classroom=self,
            is_active=True
        ).values('student').distinct().count()
    @property
    def utilization_percent(self):
        if self.capacity == 0:
            return 0
        return round((self.current_enrollment / self.capacity) * 100, 1)
    @property
    def utilization_status(self):
        pct = self.utilization_percent
        if pct >= 90:   return 'overcrowded'
        elif pct >= 70: return 'high'
        elif pct >= 40: return 'moderate'
        else:           return 'low'
Every time a template calls {{ room.utilization_percent }}, Django computes it fresh from the database. No scheduled jobs. No stale data. No update hooks to forget.
The utilization_status property returns a string that maps directly to a CSS class name in the template:
<div class="block-util-fill {{ room.utilization_status }}"></div>
This pattern - where a model property returns a CSS-safe string - is something I'll use in every project going forward. The template stays clean and the logic lives where it belongs: in the model.

---

The N+1 Problem and How I Solved It
Once utilization calculations worked, I noticed the campus dashboard was making a suspicious number of database queries. For 10 blocks with 5 classrooms each, the dashboard was hitting the database 51 times (1 for blocks + 10 for classrooms per block + 40 for enrollment per classroom).
The fix is select_related and prefetch_related:
# Without optimisation - 51 queries
blocks = Block.objects.all()
# With prefetch - 2 queries total
blocks = Block.objects.prefetch_related('classrooms').all()
For the faculty workload page, each row needs the faculty's user, department, and courses. Without optimisation that's 3 queries per faculty member - for 20 faculty, that's 60+ queries just to render one page:
# Optimised - loads everything in a handful of queries
all_faculty = Faculty.objects.select_related(
    'user', 'department'
).prefetch_related('resource_courses').all()
select_related follows foreign keys (one-to-one and many-to-one) in a SQL JOIN. prefetch_related handles reverse foreign keys and many-to-many in a separate query then joins in Python. Using both together dropped my dashboard from 50+ queries to 4.

---

Calculating Campus Utilization Correctly
The campus-level utilization number needs careful thought. My first version summed enrolled counts and divided by total capacity:
# Wrong - counts students multiple times if enrolled in multiple courses
total_enr = Enrollment.objects.filter(is_active=True).count()
A student enrolled in 6 courses would be counted 6 times. The correct version counts distinct students:
# Correct - each student counted once regardless of how many courses
total_enr = Enrollment.objects.filter(
    is_active=True
).values('student').distinct().count()
The .values('student') groups by student ID, and .distinct() ensures each student is counted once. This is a common ORM mistake that produces inflated numbers - the kind that would make a utilization dashboard useless.

---

The Reverse Accessor Clash
This one caught me off guard. Both my attendance app and resources app had a model called Course, and both had a ForeignKey pointing at Department:
python manage.py check
ERRORS:
attendance.Course.department: (fields.E304) Reverse accessor 
'Department.course_set' clashes with reverse accessor for 
'resources.Course.department'.
When Django creates a ForeignKey, it automatically creates a reverse accessor on the related model - department.course_set - so you can do some_department.course_set.all(). When two models in different apps both point at Department without a related_name, they both try to create department.course_set, and Django refuses to start.
The fix is one argument on each ForeignKey:
# attendance/models.py
department = models.ForeignKey(Department, related_name='attendance_courses', ...)
# resources/models.py
department = models.ForeignKey(Department, related_name='resource_courses', ...)
Now department.attendance_courses.all() and department.resource_courses.all() are distinct. The error taught me to always set related_name on ForeignKeys the moment I create them - not after hitting the error in production.

---

Workload Distribution - The Algorithm
The workload calculation is the most assignment-relevant piece. I defined two thresholds based on reasonable teaching expectations:
OVERLOAD_THRESHOLD  = 20  # hours/week
UNDERLOAD_THRESHOLD = 6   # hours/week
def calculate_faculty_workload(faculty):
    courses = Course.objects.filter(faculty=faculty, is_active=True)
    total_hours = courses.aggregate(Sum('hours_per_week'))['hours_per_week__sum'] or 0
    if total_hours > OVERLOAD_THRESHOLD:
        status = 'OVERLOADED'
    elif total_hours < UNDERLOAD_THRESHOLD:
        status = 'UNDERLOAD'
    else:
        status = 'NORMAL'
    return status, total_hours
I used aggregate(Sum(...)) from Django's ORM rather than loading all courses into Python and summing them manually. aggregate runs the sum in the database - for a faculty member with 8 courses, that's one database query instead of loading 8 rows into memory.
The threshold values are stored as module-level constants so they can be changed in one place and affect both the calculation logic and the template labels.

---

The Dashboard Chart
For the block utilization bar chart, I needed to pass Python data to a JavaScript Chart.js instance. The bridge is json.dumps() in the view and {{ variable|safe }} in the template:
# views.py
import json
block_labels = [b.code for b in blocks]
block_utils  = [b.utilization_percent for b in blocks]
context = {
    'block_labels': json.dumps(block_labels),
    'block_utils':  json.dumps(block_utils),
}
// template
new Chart(ctx, {
  data: {
    labels:   {{ block_labels|safe }},
    datasets: [{ data: {{ block_utils|safe }} }]
  }
});
The |safe filter tells Django's template engine not to escape the JSON string - without it, the " quotes get converted to &quot; and the JavaScript crashes silently.
The bar colours are dynamic - each bar gets red, orange, gold, or green based on its utilization value:
backgroundColor: data.map(v =>
    v >= 90 ? '#dc2626' :
    v >= 70 ? '#b34a2f' :
    v >= 40 ? '#c9a84c' : '#2d5016'
)

---

Role-Based Views Without Repeating Yourself
The resources module has two very different audiences - administrators and faculty see utilization dashboards and workload reports, while students only see their own timetable. Rather than writing role-checks in every view, the base template handles routing:
{% if user.is_staff or faculty %}
  <a href="{% url 'resources:dashboard' %}">Campus Overview</a>
  <a href="{% url 'resources:faculty_workload' %}">Faculty Workload</a>
{% endif %}
{% if student %}
  <a href="{% url 'resources:my_timetable' %}">My Timetable</a>
{% endif %}
The faculty and student variables come from a context processor that runs on every request - one check, available everywhere, no repetition.

---

What I'd Do Differently
Room booking system. Knowing a room's capacity is step one. The logical next step is letting faculty book rooms for specific time slots and showing live availability on a timetable grid. That's a separate module but a natural extension of this one.
Historical utilization tracking. Right now, utilization is calculated live from current enrollments. Adding a UtilizationSnapshot model that records weekly snapshots would let administrators see trends - "Block 32 has been overcrowded every Monday morning for the past month."
AI-based capacity recommendations. With historical data, a simple linear regression could predict next semester's enrollment for each course based on past years. The system could then recommend which classrooms to assign before timetables are finalized.

---

What I Built
Module 3 delivers a complete campus resource management and parameter estimation system:
Live capacity utilization for every classroom, block, and the campus as a whole
Faculty workload distribution with automatic overload/underload detection
Filterable course list with enrollment percentages
Student timetable with enrolled courses and grades
Chart.js visualizations with dynamically colored bars
All calculations done through Django @property methods and ORM aggregates - nothing stored that could go stale

The module directly addresses what the assignment asked for: data management for blocks, classrooms, courses, faculty, and students - plus system calculations for capacity utilization and workload distribution.
This is Module 3 of my LPU Smart Campus Management System. Module 1 covered AI-powered attendance. Module 2 covered food stall pre-ordering with demand prediction.
Built with Django 5, Bootstrap 5, Chart.js, and a lot of python manage.py check debugging.
Tags: Python Django Web Development University Projects Database
