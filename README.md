# 🏛️ Module 3 — Smart Campus Resource & Parameter Estimation System

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)
![Django](https://img.shields.io/badge/Django-5.x-green?style=flat-square&logo=django)
![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey?style=flat-square)
![Status](https://img.shields.io/badge/Status-Complete-brightgreen?style=flat-square)

> Part of the **LPU Smart Campus Management System** — a multi-module Django project built for university digitization.

---

## 📌 Problem Statement

Large universities like LPU manage hundreds of classrooms, dozens of faculty members, and thousands of students across multiple departments. Without a centralized system, administrators have no way to answer critical questions:

- Which classrooms are overcrowded? Which are sitting empty?
- Which faculty members have too many courses? Who is underutilized?
- How is enrollment distributed across departments?
- What courses is a student enrolled in this semester?

This module solves all of that — a complete **Campus Resource & Parameter Estimation System** that tracks blocks, classrooms, courses, faculty, and students, then calculates and visualizes capacity utilization and workload distribution automatically.

---

## ✨ Features

### 🏛️ Campus Overview Dashboard
- Live campus-wide utilization percentage (enrolled ÷ total capacity)
- Block-by-block utilization bar chart (Chart.js, color-coded by severity)
- Faculty workload summary — normal / overloaded / underloaded counts
- Department-wise enrollment breakdown
- Quick navigation to all sub-reports

### 🏢 Block & Classroom Management
- All campus blocks listed with utilization percentage and color-coded bar
- Drill into any block to see all classrooms, their capacity, current enrollment, and amenities
- Drill into any classroom to see which courses use it and their enrollment status
- Utilization statuses: 🟢 Low / 🟡 Moderate / 🟠 High / 🔴 Overcrowded

### 👨‍🏫 Faculty Workload Distribution
- Calculates contact hours per week for every faculty member automatically
- Flags overloaded faculty (>20 hrs/week) in red, underloaded (<6 hrs/week) in yellow
- Bar chart showing all faculty side by side for quick comparison
- Lists every course assigned to each faculty member with student count
- Sorted by workload status — overloaded first for immediate admin attention

### 📊 Capacity Utilization Report
- Full table of every classroom with enrolled vs capacity
- Categorizes rooms into: Overcrowded (≥90%), High (70–90%), Moderate (40–70%), Low (<40%)
- Summary strip at top for quick count of rooms in each category
- Links to individual classroom details

### 📚 Course Management
- Filterable course list by department and semester
- Each course shows faculty, classroom, enrollment percentage, and credits
- Course detail page with full enrolled students list and individual grades
- Enrollment progress bar showing capacity fill

### 📅 Student Timetable
- Students see all their enrolled courses in one view
- Shows faculty name, classroom location, credit hours, contact hours
- Displays current grade for each course (or "Not Graded" if pending)
- Color-coded course strips for easy visual distinction

---

## 🗂️ Project Structure

```
lpu_cms/
├── resources/
│   ├── models.py           # 5 database models
│   ├── views.py            # 8 views with parameter calculations
│   ├── urls.py             # 8 URL routes
│   └── admin.py            # Admin registration for all models
│
└── templates/resources/
    ├── dashboard.html          # Campus overview + block chart
    ├── block_detail.html       # Rooms inside a block
    ├── classroom_detail.html   # Room info + courses using it
    ├── faculty_workload.html   # Workload distribution + bar chart
    ├── utilization_report.html # All classrooms with status flags
    ├── course_list.html        # Filterable course grid
    ├── course_detail.html      # Course info + enrolled students
    └── my_timetable.html       # Student's enrolled courses
```

---

## 🗄️ Database Models

| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `Block` | Physical campus building | `name`, `code`, `total_floors` |
| `Classroom` | Room inside a block | `block`, `capacity`, `room_type`, amenity flags |
| `Course` | Academic course | `faculty`, `classroom`, `credits`, `hours_per_week`, `max_students` |
| `Enrollment` | Student registered in a course | `student`, `course`, `grade`, `is_active` |
| `WorkloadRecord` | Calculated faculty workload per semester | `total_hours_week`, `total_students`, `status` |

### Key `@property` Methods

```python
# Block — average utilization across all its classrooms
@property
def utilization_percent(self):
    classrooms = self.classrooms.all()
    if not classrooms:
        return 0
    return round(sum(c.utilization_percent for c in classrooms) / classrooms.count(), 1)

# Classroom — live enrollment vs capacity
@property
def utilization_percent(self):
    return round((self.current_enrollment / self.capacity) * 100, 1)

# Classroom — status label based on utilization
@property
def utilization_status(self):
    pct = self.utilization_percent
    if pct >= 90: return 'overcrowded'
    elif pct >= 70: return 'high'
    elif pct >= 40: return 'moderate'
    else: return 'low'
```

---

## 🔗 URL Routes

| URL | View | Who Can Access |
|-----|------|---------------|
| `/resources/` | `dashboard` | Admin, Faculty |
| `/resources/block/<id>/` | `block_detail` | Admin, Faculty |
| `/resources/room/<id>/` | `classroom_detail` | Admin, Faculty |
| `/resources/faculty-workload/` | `faculty_workload` | Admin, Faculty |
| `/resources/utilization/` | `utilization_report` | Admin, Faculty |
| `/resources/courses/` | `course_list` | Admin, Faculty |
| `/resources/courses/<id>/` | `course_detail` | Admin, Faculty |
| `/resources/my-timetable/` | `my_timetable` | Students |

---

## 📐 Parameter Estimation Algorithms

### 1. Capacity Utilization

```
Classroom Utilization % = (Enrolled Students / Room Capacity) × 100

Block Utilization %  = Average of all classroom utilization percentages in the block

Campus Utilization % = (Total Distinct Enrolled Students / Total Seat Capacity) × 100
```

**Example:**
```
Classroom 32-101: Capacity = 60, Enrolled = 48  → 80% (High)
Classroom 32-102: Capacity = 40, Enrolled = 12  → 30% (Low)
Block 32 average: (80 + 30) / 2 = 55% (Moderate)
```

### 2. Faculty Workload Distribution

```
Total Hours/Week = Sum of hours_per_week across all active courses taught

Status:
  Total Hours > 20  →  OVERLOADED  (red)
  Total Hours < 6   →  UNDERLOADED (yellow)
  6 ≤ Hours ≤ 20   →  NORMAL      (green)
```

**Why these thresholds?**

A standard university faculty member is expected to teach 12–16 hours/week of direct contact. 20 hours is the upper bound including tutorials and lab sessions. Below 6 hours suggests either courses haven't been assigned yet or faculty is on administrative duties.

The `calculate_faculty_workload()` function runs on every page load, so it always reflects the latest course assignments — no manual recalculation needed.

### 3. Enrollment Percentage per Course

```
Enrollment % = (Enrolled Students / Max Students) × 100
```

Stored as a `@property` on the Course model so it's always computed fresh and never goes stale in the database.

---

## 👥 User Roles

| Role | Access |
|------|--------|
| **Admin** | Full access to all pages — overview, workload, utilization, courses |
| **Faculty** | Campus overview, workload report, course list, classroom details |
| **Student** | Only My Timetable — sees their own enrolled courses and grades |
| **Stall Owner** | No access — completely separate food module sidebar |

Role detection is handled by the shared **context processor** (`attendance/context_processors.py`) which injects `is_stall_owner`, `faculty`, and `student` into every template.

---

## ⚙️ Setup & Run

```bash
# 1. Activate virtual environment
lpu_env\Scripts\activate          # Windows
source lpu_env/bin/activate       # Mac/Linux

# 2. Apply migrations
python manage.py makemigrations resources
python manage.py migrate

# 3. Start server
python manage.py runserver
```

---

## 🧪 Test Data Setup (Step by Step)

Follow this order — models depend on each other:

```
Step 1 → /admin/resources/block/
         Add: "Block 32", "Block 34", "LH Block"

Step 2 → /admin/resources/classroom/
         Add rooms under each block
         e.g. Block 32 → Room 101 (Lecture, capacity 60)
              Block 32 → Room 201 (Lab, capacity 30)

Step 3 → /admin/attendance/department/
         Verify departments exist: CSE, ECE, MBA, etc.

Step 4 → /admin/attendance/faculty/
         Add faculty members linked to User accounts and departments

Step 5 → /admin/resources/course/
         Add courses:
         - Name: "Data Structures", Code: "CSE301"
         - Assign faculty, classroom, semester, hours_per_week
         - Set max_students

Step 6 → /admin/resources/enrollment/
         Enroll students into courses
         Set is_active = True

Step 7 → Visit /resources/ → you should see live utilization data
```

---

## 🔑 Key Django Concepts Used

| Concept | Where Used |
|---------|-----------|
| `@property` | `utilization_percent`, `utilization_status`, `enrolled_count`, `slots_left` — computed on the fly, never stale |
| `update_or_create` | `calculate_faculty_workload()` — upserts WorkloadRecord safely |
| `aggregate(Sum(...))` | Total hours per faculty, total campus capacity |
| `values('student').distinct().count()` | Count unique enrolled students without duplicates |
| `select_related` | Avoids N+1 queries when loading faculty → user, classroom → block |
| `prefetch_related` | Loads classrooms for blocks in one query |
| `related_name` | `block.classrooms.all()`, `course.enrollments.all()`, `faculty.resource_courses.all()` |
| `unique_together` | One WorkloadRecord per faculty per semester per year; one Enrollment per student per course |
| `GET parameters` | Department and semester filters on course list (`request.GET.get('dept')`) |
| Context processor | `is_stall_owner`, `faculty`, `student` injected globally |
| `json.dumps()` | Serializes Python lists for Chart.js datasets |

---

## ⚠️ Common Fix — Reverse Accessor Clash

Both `attendance.Course` and `resources.Course` have a `ForeignKey` to `Department`. Django requires unique `related_name` values to avoid clashes:

```python
# attendance/models.py
department = models.ForeignKey(Department, ..., related_name='attendance_courses')

# resources/models.py
department = models.ForeignKey(Department, ..., related_name='resource_courses')
```

Without this, `python manage.py check` throws `fields.E304`.

---

## 📁 Related Modules

| Module | Description |
|--------|-------------|
| [Module 1](../attendance/) | Smart Attendance System with AI Face Recognition |
| [Module 2](../food/) | Smart Food Stall Pre-Ordering System |
| Module 3 | **Smart Campus Resource & Parameter Estimation** ← we are here |

---

