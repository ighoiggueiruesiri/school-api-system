from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from django.urls import reverse

from school.models import ClassRoom

User = get_user_model()


class ClassRoomViewSetTests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            email="admin@example.com", password="Password123", role="admin"
        )
        self.teacher_user = User.objects.create_user(
            email="teacher@example.com", password="Password123", role="teacher"
        )
        self.other_teacher = User.objects.create_user(
            email="other@example.com", password="Password123", role="teacher"
        )

        # NOTE: `level` is a required, non-nullable field on ClassRoom with no
        # default (and Meta.ordering = ["level"]), so it must be supplied on
        # every create() call or Django raises an IntegrityError at the DB
        # level before any test assertions run.
        self.classroom = ClassRoom.objects.create(name="Grade 1", level=1, teacher=self.teacher_user)
        self.other_classroom = ClassRoom.objects.create(name="Grade 2", level=2, teacher=self.other_teacher)

        self.classroom_list_url = reverse("classrooms-list")

    def detail_url(self, classroom):
        return reverse("classrooms-detail", args=[classroom.id])

    # ---- queryset filtering ----

    def test_teacher_sees_only_own_classrooms(self):
        """A pure teacher's queryset is filtered to their own classes."""
        self.client.force_authenticate(user=self.teacher_user)
        response = self.client.get(self.classroom_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "Grade 1")

    def test_admin_sees_all_classrooms(self):
        """Admins see all classrooms."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.classroom_list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    # ---- create ----

    def test_admin_can_create_classroom(self):
        """An admin can create a classroom.

        NOTE: the serializer uses fields = "__all__" with no explicit
        `teacher_id` field declared, so the FK must be posted under its
        actual model field name, `teacher`, not `teacher_id`. The original
        test posted `teacher_id`, which would fail validation (400) instead
        of succeeding, since DRF would treat `teacher` as a required field
        that was never supplied.
        """
        self.client.force_authenticate(user=self.admin_user)
        data = {"name": "Grade 3", "level": 3, "teacher": self.teacher_user.id}

        response = self.client.post(self.classroom_list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ClassRoom.objects.filter(name="Grade 3").count(), 1)

    def test_teacher_cannot_create_classroom(self):
        """A pure teacher (not admin/editor) is forbidden from creating a classroom."""
        self.client.force_authenticate(user=self.teacher_user)
        data = {"name": "Grade 4", "level": 4, "teacher": self.teacher_user.id}

        response = self.client.post(self.classroom_list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ClassRoom.objects.filter(name="Grade 4").exists())

    # ---- update ----

    def test_admin_can_update_classroom(self):
        """An admin can update a classroom."""
        self.client.force_authenticate(user=self.admin_user)
        url = self.detail_url(self.classroom)
        data = {"name": "Grade 1 Updated", "level": 1, "teacher": self.teacher_user.id}

        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.name, "Grade 1 Updated")

    def test_teacher_cannot_update_classroom(self):
        """A pure teacher is forbidden from updating a classroom, even their own."""
        self.client.force_authenticate(user=self.teacher_user)
        url = self.detail_url(self.classroom)
        data = {"name": "Should Not Update", "level": 1, "teacher": self.teacher_user.id}

        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.name, "Grade 1")

    # ---- destroy ----

    def test_admin_can_delete_classroom(self):
        """Only admins can delete classrooms."""
        self.client.force_authenticate(user=self.admin_user)
        url = self.detail_url(self.classroom)

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ClassRoom.objects.filter(id=self.classroom.id).exists())

    def test_teacher_cannot_delete_classroom(self):
        """A pure teacher cannot delete classrooms, even their own."""
        self.client.force_authenticate(user=self.teacher_user)
        url = self.detail_url(self.classroom)

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ClassRoom.objects.filter(id=self.classroom.id).exists())

    # ---- object-level access via filtered queryset ----

    def test_teacher_cannot_retrieve_other_teachers_classroom(self):
        """A pure teacher's filtered queryset should hide other teachers' classrooms,
        so retrieving one by id should 404 rather than 200/403."""
        self.client.force_authenticate(user=self.teacher_user)
        url = self.detail_url(self.other_classroom)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ---- search ----

    def test_admin_can_search_by_classroom_name(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.classroom_list_url, {"search": "Grade 1"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]
        self.assertIn("Grade 1", names)
        self.assertNotIn("Grade 2", names)

    # ---- serializer fields ----

    def test_classroom_serializer_includes_student_count_and_teacher_name(self):
        self.client.force_authenticate(user=self.admin_user)
        url = self.detail_url(self.classroom)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("student_count", response.data)
        self.assertIn("teacher_name", response.data)
        self.assertEqual(response.data["student_count"], 0)

    # ---- auth required ----

    def test_unauthenticated_user_cannot_list_classrooms(self):
        response = self.client.get(self.classroom_list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)