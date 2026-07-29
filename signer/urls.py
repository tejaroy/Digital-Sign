from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("positions/", views.positions, name="positions"),
    path("reset/", views.reset_job, name="reset"),
]
