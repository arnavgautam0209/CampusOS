from django.urls import path

from . import views

urlpatterns = [
    path("ai/planner/", views.plan, name="ai-planner"),
]
