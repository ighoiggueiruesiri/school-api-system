from datetime import date

from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import AcademicReport, SubjectScore, Student, Term, ClassRoom

User = get_user_model()


class AcademicReportViewSetTestBase(APITestCase):
    """Shared fixtures for all AcademicReport endpoint tests."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.teacher_user = User.objects.create_user(
            email="teacher@example.com", password="Password123", role="teacher"
        )
        self.other_teacher_user = User.objects.create_user(
            email="other_teacher@example.com", password="Password123", role="teacher"
        )
        self.parent_user = User.objects.create_user(
            email="parent@example.com", password="Password123", role="parent"
        )
        self.other_parent_user = User.objects.create_user(
            email="other_parent@example.com", password="Password123", role="parent"
        )

        self.term = Term.objects.create(
            name="first",
            academic_year="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 15),
        )

        self.classroom = ClassRoom.objects.create(name="Primary 1", level=1, teacher=self.teacher_user)
        self.other_classroom = ClassRoom.objects.create(name="Primary 2", level=2, teacher=self.other_teacher_user)

        self.student = Student.objects.create(
            admission_number="ADM-0001",
            first_name="Child", last_name="One",
            date_of_birth=date(2018, 4, 12), gender="male",
            is_active=True, current_class=self.classroom,
        )
        self.student.parents.add(self.parent_user)

        self.other_student = Student.objects.create(
            admission_number="ADM-0002",
            first_name="Other", last_name="Kid",
            date_of_birth=date(2018, 9, 3), gender="female",
            is_active=True, current_class=self.other_classroom,
        )
        self.other_student.parents.add(self.other_parent_user)

        self.report = AcademicReport.objects.create(
            student=self.student,
            term=self.term,
            written_by=self.admin_user,
            report_type="elementary",
            teacher_comment="Doing well.",
            is_published=False,
        )

        self.other_report = AcademicReport.objects.create(
            student=self.other_student,
            term=self.term,
            written_by=self.admin_user,
            report_type="elementary",
            teacher_comment="Needs improvement.",
            is_published=True,
        )

        self.report_list_url = reverse("reports-list")
        self.report_detail_url = reverse("reports-detail", kwargs={"pk": self.report.id})
        self.report_publish_url = reverse("reports-publish", kwargs={"pk": self.report.id})


class VisibilityTests(AcademicReportViewSetTestBase):
    """Who can see which reports."""

    def test_parent_cannot_see_unpublished_reports(self):
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.report_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_parent_can_see_published_reports(self):
        self.report.is_published = True
        self.report.save()

        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.report_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_parent_cannot_see_other_students_reports(self):
        """A parent should never see a report belonging to a child that isn't theirs,
        even if that report is published."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.get(self.report_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {r["id"] for r in response.data["results"]}
        self.assertNotIn(self.other_report.id, returned_ids)

    def test_teacher_only_sees_their_classroom_students(self):
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.report_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {r["id"] for r in response.data["results"]}
        self.assertIn(self.report.id, returned_ids)
        self.assertNotIn(self.other_report.id, returned_ids)

    def test_admin_sees_all_reports(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_unauthenticated_user_is_rejected(self):
        response = self.client.get(self.report_list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class FilteringTests(AcademicReportViewSetTestBase):
    def test_filter_by_student(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_list_url, {"student": self.student.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {r["id"] for r in response.data["results"]}
        self.assertEqual(ids, {self.report.id})

    def test_filter_by_term(self):
        other_term = Term.objects.create(
            name="second",
            academic_year="2026/2027",
            start_date=date(2027, 1, 5),
            end_date=date(2027, 4, 10),
        )
        AcademicReport.objects.create(
            student=self.student, term=other_term, written_by=self.admin_user,
            report_type="elementary", teacher_comment="x",
        )

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_list_url, {"term": self.term.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for r in response.data["results"]:
            self.assertEqual(r["term"], self.term.id)

    def test_filter_by_is_published(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_list_url, {"is_published": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {r["id"] for r in response.data["results"]}
        self.assertEqual(ids, {self.other_report.id})

    def test_filter_by_classroom(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_list_url, {"classroom": self.classroom.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {r["id"] for r in response.data["results"]}
        self.assertEqual(ids, {self.report.id})

    def test_filter_by_report_type(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_list_url, {"report_type": "elementary"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data["results"]) >= 1)
        for r in response.data["results"]:
            self.assertEqual(r["report_type"], "elementary")

    def test_search_by_teacher_comment(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_list_url, {"search": "improvement"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {r["id"] for r in response.data["results"]}
        self.assertIn(self.other_report.id, ids)


class CreateTests(AcademicReportViewSetTestBase):
    def _payload(self):
        new_term = Term.objects.create(
            name="first",
            academic_year="2027/2028",
            start_date=date(2027, 9, 1),
            end_date=date(2027, 12, 15),
        )
        return {
            "student": self.student.id,
            "term": new_term.id,
            "report_type": "elementary",
            "teacher_comment": "New report comment.",
            "subject_scores": [
                {
                    "subject": "MATH",
                    "cat_score": 30,
                    "exam_score": 60,
                    "wh_behaviour": "MS",
                    "wh_listens": "MS",
                    "wh_completes_work": "LS",
                    "wh_contributes": "LS",
                    "wh_homework": "MS",
                }
            ],
        }

    def test_admin_can_create_report_with_nested_subject_scores(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(self.report_list_url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        created = AcademicReport.objects.get(id=response.data["id"])
        self.assertEqual(created.written_by, self.admin_user)
        self.assertEqual(created.subject_scores.count(), 1)
        score = created.subject_scores.first()
        self.assertEqual(score.total_score, 90)
        self.assertEqual(score.grade, "A")

    def test_parent_cannot_create_report(self):
        """Non-staff create attempts must be rejected with 403, not raise an
        unhandled server error."""
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.post(self.report_list_url, self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_report(self):
        response = self.client.post(self.report_list_url, self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UpdateTests(AcademicReportViewSetTestBase):
    def test_admin_can_update_report(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(
            self.report_detail_url, {"teacher_comment": "Updated comment."}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.report.refresh_from_db()
        self.assertEqual(self.report.teacher_comment, "Updated comment.")

    def test_update_fully_replaces_subject_scores(self):
        SubjectScore.objects.create(
            report=self.report, subject="MATH", cat_score=10, exam_score=10
        )
        self.assertEqual(self.report.subject_scores.count(), 1)

        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "subject_scores": [
                {"subject": "ENGLISH", "cat_score": 40, "exam_score": 50},
            ]
        }
        response = self.client.patch(self.report_detail_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.report.refresh_from_db()
        self.assertEqual(self.report.subject_scores.count(), 1)
        self.assertEqual(self.report.subject_scores.first().subject, "ENGLISH")

    def test_parent_cannot_update_report(self):
        self.report.is_published = True
        self.report.save()

        self.client.force_authenticate(user=self.parent_user)
        response = self.client.patch(
            self.report_detail_url, {"teacher_comment": "Hacked."}, format="json"
        )

        # Parents' queryset is scoped to is_published=True so the object is
        # visible, but they should not be able to modify it.
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )
        self.report.refresh_from_db()
        self.assertNotEqual(self.report.teacher_comment, "Hacked.")


class DeleteTests(AcademicReportViewSetTestBase):
    def test_admin_can_delete_report(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.delete(self.report_detail_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AcademicReport.objects.filter(id=self.report.id).exists())

    def test_non_admin_cannot_delete_report(self):
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.delete(self.report_detail_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(AcademicReport.objects.filter(id=self.report.id).exists())


class PublishActionTests(AcademicReportViewSetTestBase):
    def test_admin_can_publish_report(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(self.report_publish_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.report.refresh_from_db()
        self.assertTrue(self.report.is_published)

    def test_publishing_already_published_report_is_idempotent(self):
        self.report.is_published = True
        self.report.save()

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(self.report_publish_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Already published.")

    def test_parent_cannot_publish_report(self):
        self.client.force_authenticate(user=self.parent_user)
        response = self.client.post(self.report_publish_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_cannot_publish_report(self):
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.post(self.report_publish_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SerializerSelectionTests(AcademicReportViewSetTestBase):
    def test_list_uses_lightweight_serializer(self):
        """List responses should not include heavy preschool/elementary detail fields."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result = response.data["results"][0]
        self.assertNotIn("subject_scores", result)
        self.assertNotIn("lit_speaks_clearly", result)

    def test_retrieve_uses_full_serializer(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.report_detail_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("subject_scores", response.data)
        self.assertIn("lit_speaks_clearly", response.data)