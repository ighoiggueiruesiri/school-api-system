from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import Attendance, Student, ClassRoom, Term

User = get_user_model()


class AttendanceViewSetTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.teacher_user = User.objects.create_user(
            email="teacher@example.com", password="Password123", role="teacher"
        )
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password="Password123", role="parent"
        )

        self.term = Term.objects.create(
            name="first", academic_year="2026/2027",
            start_date="2026-09-01", end_date="2026-12-19",
        )
        self.other_term = Term.objects.create(
            name="second", academic_year="2026/2027",
            start_date="2027-01-05", end_date="2027-05-22",
        )

        self.classroom = ClassRoom.objects.create(
            name="Grade 4", level=4, teacher=self.teacher_user
        )
        self.other_classroom = ClassRoom.objects.create(
            name="Grade 5",
            level=5,
            teacher=User.objects.create_user(
                email="other_teacher@example.com", password="Password123", role="teacher"
            ),
        )

        self.student1 = Student.objects.create(
            first_name="Alice", current_class=self.classroom,
            date_of_birth="2016-04-12", admission_number="ADM-0001",
        )
        self.student2 = Student.objects.create(
            first_name="Bob", current_class=self.classroom,
            date_of_birth="2016-08-30", admission_number="ADM-0002",
        )
        self.other_student = Student.objects.create(
            first_name="Carol", current_class=self.other_classroom,
            date_of_birth="2015-11-02", admission_number="ADM-0003",
        )

        # Link parent to student1 only
        self.student1.parents.add(self.parent_user)

        self.attendance_list_url = reverse("attendance-list")
        self.bulk_attendance_url = reverse("attendance-bulk")

    # ------------------------------------------------------------------ #
    #  Authentication guard                                                #
    # ------------------------------------------------------------------ #

    def test_unauthenticated_request_is_rejected(self):
        """Unauthenticated users must not access any attendance data."""
        response = self.client.get(self.attendance_list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_bulk_request_is_rejected(self):
        """Unauthenticated users must not be able to hit the bulk endpoint."""
        data = {
            "date": "2026-06-29",
            "term": self.term.id,
            "records": [{"student_id": self.student1.id, "status": "present"}],
        }
        response = self.client.post(self.bulk_attendance_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ------------------------------------------------------------------ #
    #  get_queryset scoping                                                #
    # ------------------------------------------------------------------ #

    def test_teacher_sees_only_own_class_attendance(self):
        """A pure teacher sees attendance only for students in their class."""
        Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        Attendance.objects.create(
            student=self.other_student, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )

        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.attendance_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(
            response.data["results"][0]["student"], self.student1.id
        )

    def test_parent_sees_only_own_childrens_attendance(self):
        """A parent sees attendance only for their linked children."""
        Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        Attendance.objects.create(
            student=self.student2, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )

        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.attendance_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(
            response.data["results"][0]["student"], self.student1.id
        )

    def test_parent_cannot_retrieve_other_childs_record_by_id(self):
        """A parent must not be able to fetch a non-owned record directly via detail URL."""
        record = Attendance.objects.create(
            student=self.student2, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        self.client.force_authenticate(user=self.parent_user)
        url = reverse("attendance-detail", kwargs={"pk": record.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_sees_all_attendance_records(self):
        """Admins see every attendance record regardless of class."""
        Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        Attendance.objects.create(
            student=self.other_student, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.attendance_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    # ------------------------------------------------------------------ #
    #  Query-parameter filters                                             #
    # ------------------------------------------------------------------ #

    def test_filter_by_term(self):
        """The ?term= parameter narrows results to the given term."""
        Attendance.objects.create(
            student=self.student1, date="2026-06-01",
            term=self.term, recorded_by=self.admin_user,
        )
        Attendance.objects.create(
            student=self.student2, date="2026-06-01",
            term=self.other_term, recorded_by=self.admin_user,
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.attendance_list_url, {"term": self.term.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["term"], self.term.id)

    def test_filter_by_date(self):
        """The ?date= parameter returns only records on that date."""
        Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        Attendance.objects.create(
            student=self.student2, date="2026-06-28",
            term=self.term, recorded_by=self.admin_user,
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.attendance_list_url, {"date": "2026-06-29"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["date"], "2026-06-29")

    def test_filter_by_student(self):
        """The ?student= parameter scopes results to a single student."""
        Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        Attendance.objects.create(
            student=self.student2, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(
            self.attendance_list_url, {"student": self.student1.id}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(
            response.data["results"][0]["student"], self.student1.id
        )

    def test_page_size_query_param_limits_results(self):
        """The ?page_size= parameter overrides the default page size."""
        for i, day in enumerate(["2026-06-01", "2026-06-02", "2026-06-03"]):
            Attendance.objects.create(
                student=self.student1, date=day,
                term=self.term, recorded_by=self.admin_user,
            )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.attendance_list_url, {"page_size": 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["count"], 3)

    def test_search_filter_matches_reason(self):
        """?search= matches against the reason field via SearchFilter."""
        Attendance.objects.create(
            student=self.student1, date="2026-06-29", status="absent",
            reason="Dentist appointment",
            term=self.term, recorded_by=self.admin_user,
        )
        Attendance.objects.create(
            student=self.student2, date="2026-06-29", status="absent",
            reason="Family trip",
            term=self.term, recorded_by=self.admin_user,
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.attendance_list_url, {"search": "Dentist"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["student"], self.student1.id)

    # ------------------------------------------------------------------ #
    #  create — single record                                              #
    # ------------------------------------------------------------------ #

    def test_admin_can_create_single_attendance_record(self):
        """A POST to the list endpoint creates a single attendance record."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "student": self.student1.id,
            "date": "2026-06-29",
            "status": "present",
            "term": self.term.id,
        }
        response = self.client.post(self.attendance_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Attendance.objects.count(), 1)

    def test_recorded_by_is_set_server_side_and_not_overridable(self):
        """recorded_by is read-only and always set from the requesting user,
        even if the client tries to supply a different value."""
        self.client.force_authenticate(user=self.teacher_user)
        data = {
            "student": self.student1.id,
            "date": "2026-06-29",
            "status": "present",
            "term": self.term.id,
            "recorded_by": self.admin_user.id,  # attempt to spoof
        }
        response = self.client.post(self.attendance_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record = Attendance.objects.get(pk=response.data["id"])
        self.assertEqual(record.recorded_by_id, self.teacher_user.id)

    def test_duplicate_record_for_same_student_and_date_is_rejected(self):
        """unique_together on (student, date) should produce a 400, not a 500,
        on direct (non-bulk) create."""
        Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "student": self.student1.id,
            "date": "2026-06-29",
            "status": "absent",
            "term": self.term.id,
        }
        response = self.client.post(self.attendance_list_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Attendance.objects.count(), 1)

    # ------------------------------------------------------------------ #
    #  destroy — admin guard                                               #
    # ------------------------------------------------------------------ #

    def test_admin_can_delete_attendance_record(self):
        """Admins should be able to delete any attendance record."""
        record = Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("attendance-detail", kwargs={"pk": record.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Attendance.objects.filter(pk=record.pk).exists())

    def test_teacher_cannot_delete_attendance_record(self):
        """Non-admin staff must receive a 403 when attempting to delete."""
        record = Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.teacher_user,
        )
        self.client.force_authenticate(user=self.teacher_user)
        url = reverse("attendance-detail", kwargs={"pk": record.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Attendance.objects.filter(pk=record.pk).exists())

    def test_parent_cannot_delete_attendance_record(self):
        """Parents must also receive a 403 when attempting to delete."""
        record = Attendance.objects.create(
            student=self.student1, date="2026-06-29",
            term=self.term, recorded_by=self.admin_user,
        )
        self.client.force_authenticate(user=self.parent_user)
        url = reverse("attendance-detail", kwargs={"pk": record.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Attendance.objects.filter(pk=record.pk).exists())

    # ------------------------------------------------------------------ #
    #  bulk endpoint — happy paths                                         #
    # ------------------------------------------------------------------ #

    def test_staff_bulk_create_attendance(self):
        """Staff can bulk-create attendance records for a whole class."""
        self.client.force_authenticate(user=self.teacher_user)
        data = {
            "date": "2026-06-29",
            "term": self.term.id,
            "records": [
                {"student_id": self.student1.id, "status": "present"},
                {"student_id": self.student2.id, "status": "absent", "reason": "Sick"},
            ],
        }

        response = self.client.post(self.bulk_attendance_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["updated"], 0)
        self.assertEqual(Attendance.objects.count(), 2)

    def test_bulk_attendance_updates_existing_records(self):
        """Bulk attendance uses update_or_create — an existing record is updated, not duplicated."""
        Attendance.objects.create(
            student=self.student1,
            date="2026-06-29",
            status="absent",
            term=self.term,
            recorded_by=self.teacher_user,
        )

        self.client.force_authenticate(user=self.admin_user)
        data = {
            "date": "2026-06-29",
            "term": self.term.id,
            "records": [{"student_id": self.student1.id, "status": "present"}],
        }

        response = self.client.post(self.bulk_attendance_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["updated"], 1)

        self.assertEqual(Attendance.objects.count(), 1)
        record = Attendance.objects.get(student=self.student1, date="2026-06-29")
        self.assertEqual(record.status, "present")

    def test_bulk_attendance_ignores_unknown_students_and_reports_error(self):
        """Unknown student IDs are reported in the errors list and do not abort the transaction."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "date": "2026-06-29",
            "term": self.term.id,
            "records": [
                {"student_id": self.student1.id, "status": "present"},
                {"student_id": 99999, "status": "present"},
            ],
        }

        response = self.client.post(self.bulk_attendance_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(len(response.data["errors"]), 1)
        self.assertIn("99999", response.data["errors"][0])

    def test_bulk_attendance_missing_required_fields_returns_400(self):
        """A bulk request missing date/term/records should fail serializer validation."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(self.bulk_attendance_url, {"records": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_attendance_persists_outlook_field(self):
        """The bulk endpoint should store the optional 'outlook' value per record."""
        self.client.force_authenticate(user=self.admin_user)
        data = {
            "date": "2026-06-29",
            "term": self.term.id,
            "records": [
                {"student_id": self.student1.id, "status": "present", "outlook": "Cheerful"},
            ],
        }
        response = self.client.post(self.bulk_attendance_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        record = Attendance.objects.get(student=self.student1, date="2026-06-29")
        self.assertEqual(record.outlook, "Cheerful")

    # ------------------------------------------------------------------ #
    #  bulk endpoint — permission guard                                    #
    # ------------------------------------------------------------------ #

    def test_parent_cannot_access_bulk_endpoint(self):
        """Non-staff users (e.g. parents) must receive a 403 on the bulk endpoint."""
        self.client.force_authenticate(user=self.parent_user)
        data = {
            "date": "2026-06-29",
            "term": self.term.id,
            "records": [{"student_id": self.student1.id, "status": "present"}],
        }

        response = self.client.post(self.bulk_attendance_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Attendance.objects.count(), 0)

    def test_teacher_bulk_create_is_not_scoped_to_own_class(self):
        """
        KNOWN GAP: the bulk endpoint only checks is_staff(); it does not verify
        that a teacher 'owns' the students being marked. A teacher can currently
        bulk-mark attendance for a student outside their own class. This test
        documents the existing behavior rather than endorsing it — see review notes.
        """
        self.client.force_authenticate(user=self.teacher_user)
        data = {
            "date": "2026-06-29",
            "term": self.term.id,
            "records": [{"student_id": self.other_student.id, "status": "present"}],
        }
        response = self.client.post(self.bulk_attendance_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["created"], 1)
        self.assertTrue(
            Attendance.objects.filter(student=self.other_student, date="2026-06-29").exists()
        )