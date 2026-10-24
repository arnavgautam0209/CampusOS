from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from .requests_api import requests
from .views import me

urlpatterns = [
    path("auth/token/", obtain_auth_token, name="auth-token"),
    path("auth/me/", me, name="auth-me"),
    path("requests/", requests, name="requests"),
]
