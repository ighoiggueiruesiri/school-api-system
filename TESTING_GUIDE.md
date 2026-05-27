# Giant Step Academy — Complete API Testing Guide

## Setup (do this once)

```bash
# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac / Linux

# 2. Install packages
pip install -r requirements.txt

# 3. Create the database (in psql / SQL Shell)
CREATE USER gsa_user WITH PASSWORD 'gsa_password_123';
CREATE DATABASE gsa_db OWNER gsa_user;
GRANT ALL PRIVILEGES ON DATABASE gsa_db TO gsa_user;
\q

# 4. Run migrations  ← this now works because there is only ONE app
python manage.py makemigrations school
python manage.py migrate

# 5. Create the super admin
python manage.py createsuperuser
# Email:      admin@gsa.com
# First name: Admin
# Last name:  GSA
# Password:   Admin1234!

# 6. Start the server
python manage.py runserver
gunicorn gsa.wsgi:application #production
waitress-serve --listen=127.0.0.1:8000 gsa.wsgi:application #local
```

Open your browser:
- API docs (Swagger): http://127.0.0.1:8000/api/docs/
- Django admin:       http://127.0.0.1:8000/admin/

---

## Testing Tool: Swagger UI

Go to **http://127.0.0.1:8000/api/docs/**

This is an interactive page listing every endpoint.
To test protected endpoints:
1. Call `POST /api/login/` — copy the `access` token from the response
2. Click the green **Authorize** button (top right)
3. Enter: `Bearer eyJhbGci...` (your token)
4. Click Authorize — every request is now authenticated

If you prefer Postman:
- Add header `Authorization: Bearer <token>` to every request that needs auth

---

## STEP 1 — Log in as admin

**POST** `http://127.0.0.1:8000/api/login/`

```json
{
  "email": "admin@gsa.com",
  "password": "Admin1234!"
}
```

Response:
```json
{
  "access":  "eyJhbGciOiJIUzI1NiIs...",
  "refresh": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "email":     "admin@gsa.com",
    "full_name": "Admin GSA",
    "role":      "admin"
  }
}
```

**Save the `access` token — paste it into every request below as:**
`Authorization: Bearer <paste token here>`

---

## STEP 2 — Create a teacher account

**POST** `http://127.0.0.1:8000/api/users/`

```json
{
  "email":      "teacher.amara@gsa.com",
  "first_name": "Amara",
  "last_name":  "Nwosu",
  "phone":      "+2348012345678",
  "role":       "teacher",
  "password":   "Teacher123!"
}
```

Response:
```json
{
  "id":    "b3c4d5...",
  "email": "teacher.amara@gsa.com",
  "role":  "teacher"
}
```

---

## STEP 3 — Create classrooms

**POST** `http://127.0.0.1:8000/api/classrooms/`

```json
{ "name": "Playgroup", "level": 1, "capacity": 15 }
```

Repeat for each class:
```json
{ "name": "Nursery 1",  "level": 2, "capacity": 20 }
{ "name": "Nursery 2",  "level": 3, "capacity": 20 }
{ "name": "Primary 1",  "level": 4, "capacity": 25 }
```

---

## STEP 4 — Assign the teacher to a classroom

**PATCH** `http://127.0.0.1:8000/api/classrooms/1/`

```json
{ "teacher": "b3c4d5..." }
```
(use the teacher's `id` from step 2)

---

## STEP 5 — Create a term

**POST** `http://127.0.0.1:8000/api/terms/`

```json
{
  "name":          "first",
  "academic_year": "2024/2025",
  "start_date":    "2024-09-09",
  "end_date":      "2024-12-13",
  "is_current":    true
}
```

---

## STEP 6 — A parent registers themselves

No token needed for this one.

**POST** `http://127.0.0.1:8000/api/register/`

```json
{
  "email":      "grace.okafor@gmail.com",
  "password":   "Parent123!",
  "first_name": "Grace",
  "last_name":  "Okafor",
  "phone":      "+2348034567890"
}
```

Response:
```json
{
  "message": "Account created. You can now log in.",
  "email":   "grace.okafor@gmail.com"
}
```

---

## STEP 7 — Admin creates a student and links the parent

**POST** `http://127.0.0.1:8000/api/students/`

First get the parent's user `id` from `GET /api/users/?role=parent`

```json
{
  "first_name":    "Chioma",
  "last_name":     "Okafor",
  "date_of_birth": "2020-04-15",
  "gender":        "female",
  "current_class": 2,
  "parents":       ["<grace's user id>"]
}
```

Response includes the auto-generated `admission_number`:
```json
{
  "id":               "a3f7c8...",
  "admission_number": "GSA-2024-0001",
  "full_name":        "Chioma Okafor",
  "current_class":    2
}
```

---

## STEP 8 — Parent logs in and views their child

**POST** `http://127.0.0.1:8000/api/login/`
```json
{ "email": "grace.okafor@gmail.com", "password": "Parent123!" }
```
(Use the parent's `access` token for steps 8–10)

**GET** `http://127.0.0.1:8000/api/students/mine/`

```json
[{
  "id":                "a3f7c8...",
  "full_name":         "Chioma Okafor",
  "admission_number":  "GSA-2024-0001",
  "current_class_name":"Nursery 1",
  "age":               4
}]
```

---

## STEP 9 — Teacher marks attendance

Log in as the teacher first. Use **teacher's token** below.

**POST** `http://127.0.0.1:8000/api/attendance/bulk/`

```json
{
  "date": "2024-09-16",
  "term": 1,
  "records": [
    { "student_id": "a3f7c8...", "status": "present" },
    { "student_id": "b9c2d1...", "status": "absent", "reason": "sick" },
    { "student_id": "e5f6a7...", "status": "late" }
  ]
}
```

Response:
```json
{
  "created": 3,
  "updated": 0,
  "errors":  [],
  "message": "Attendance saved for 3 students."
}
```

**View a student's attendance summary (parent or admin):**

**GET** `http://127.0.0.1:8000/api/students/a3f7c8.../attendance-summary/?term=1`

```json
{
  "student":            "Chioma Okafor",
  "total_days":         5,
  "present":            4,
  "absent":             1,
  "late":               0,
  "attendance_percent": 80.0
}
```

---

## STEP 10 — Admin creates an invoice and records payment

**POST** `http://127.0.0.1:8000/api/invoices/`

```json
{
  "student":     "a3f7c8...",
  "term":        1,
  "description": "Tuition — First Term 2024/2025",
  "amount":      "150000.00",
  "due_date":    "2024-09-30"
}
```

**POST** `http://127.0.0.1:8000/api/payments/`  — record money received

```json
{
  "invoice":   "<invoice id>",
  "amount":    "100000.00",
  "method":    "bank_transfer",
  "reference": "TRF-2024-001",
  "notes":     "First installment"
}
```

Invoice status updates automatically to `partial`.

**GET** `http://127.0.0.1:8000/api/invoices/summary/?student=a3f7c8...`

```json
{
  "total_billed":  150000.00,
  "total_paid":    100000.00,
  "balance":        50000.00,
  "unpaid_count":  1
}
```

---

## STEP 11 — Post an announcement

**POST** `http://127.0.0.1:8000/api/announcements/`

```json
{
  "title":    "End of Term Concert — Friday 13th December",
  "body":     "Parents are invited to the hall at 10am. Smart casual dress.",
  "audience": "parents"
}
```

Parent sees it on **GET** `http://127.0.0.1:8000/api/announcements/`

---

## STEP 12 — Teacher writes a development report

**POST** `http://127.0.0.1:8000/api/reports/`

```json
{
  "student":           "a3f7c8...",
  "term":              1,
  "comment":           "Chioma has shown excellent growth in language this term.",
  "strengths":         "Strong communicator, loves storytelling.",
  "areas_to_improve":  "Needs to work on number recognition.",
  "confidence":        5,
  "teamwork":          4
}
```

Report is hidden from parents until admin publishes it.

**POST** `http://127.0.0.1:8000/api/reports/<report_id>/publish/`
(use admin token — no body needed)

Parent now sees it on **GET** `http://127.0.0.1:8000/api/reports/`

---

## STEP 13 — Teacher posts an assignment

**POST** `http://127.0.0.1:8000/api/assignments/`

```json
{
  "title":       "Alphabet practice — letters A to E",
  "description": "Trace the letters in your workbook and draw one picture for each.",
  "type":        "homework",
  "classroom":   2,
  "term":        1,
  "due_date":    "2024-09-20"
}
```

Parent sees it on **GET** `http://127.0.0.1:8000/api/assignments/`

---

## STEP 14 — Logout

**POST** `http://127.0.0.1:8000/api/logout/`

```json
{ "refresh": "<your refresh token>" }
```

---

## All endpoints at a glance

| Method | URL | Who | What |
|--------|-----|-----|------|
| POST | /api/login/ | Anyone | Get JWT tokens |
| POST | /api/register/ | Anyone | Parent self-signup |
| POST | /api/logout/ | Auth | Invalidate token |
| GET/PATCH | /api/me/ | Auth | Own profile |
| GET/POST | /api/users/ | Admin | Manage accounts |
| GET/POST | /api/classrooms/ | All/Admin | Classes |
| GET/POST | /api/terms/ | All/Admin | Terms |
| GET | /api/terms/current/ | All | Active term |
| GET/POST | /api/students/ | Role-filtered | Students |
| GET | /api/students/mine/ | Parent | Own children |
| GET | /api/students/<id>/attendance-summary/ | All | Stats |
| GET/POST | /api/attendance/ | Role-filtered | Records |
| POST | /api/attendance/bulk/ | Teacher | Whole class |
| GET/POST | /api/invoices/ | Role-filtered | Fee bills |
| GET | /api/invoices/summary/ | All | Totals |
| GET/POST | /api/payments/ | Admin/Parent | Payments |
| GET/POST | /api/announcements/ | All/Teacher | Notices |
| GET/POST | /api/assignments/ | Role-filtered | Homework |
| GET/POST | /api/reports/ | Role-filtered | Reports |
| POST | /api/reports/<id>/publish/ | Admin | Go live |
| GET | /api/docs/ | Anyone | Swagger docs |
| GET | /admin/ | Admin | Django admin |
