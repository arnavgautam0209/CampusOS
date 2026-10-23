from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class AuthApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            "alice", email="alice@example.edu", password="unused-test-pw",
            first_name="Alice", last_name="Rao",
        )
        self.client = APIClient()

    def test_token_login_returns_token(self):
        response = self.client.post(
            "/api/v1/auth/token/", {"username": "alice", "password": "unused-test-pw"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])

    def test_token_login_rejects_bad_password(self):
        response = self.client.post(
            "/api/v1/auth/token/", {"username": "alice", "password": "wrong"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("non_field_errors", response.json())

    def test_me_requires_authentication(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_me_with_token_matches_ios_shape(self):
        token = self.client.post(
            "/api/v1/auth/token/", {"username": "alice", "password": "unused-test-pw"}, format="json"
        ).json()["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"id": str(self.user.pk), "name": "Alice Rao", "email": "alice@example.edu", "role": "student"},
        )

    def test_invalid_token_is_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_staff_and_superuser_roles(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/v1/auth/me/").json()["role"], "faculty")
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.client.get("/api/v1/auth/me/").json()["role"], "administrator")
