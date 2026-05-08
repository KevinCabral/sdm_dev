from django.urls import path

from . import views

urlpatterns = [
    path("/index", views.index, name="potenciais_militantes.index"),
    path("/<int:id>/inquerito", views.inquerito, name="potenciais_militantes.inquerito"),
    path("/<int:id>/reject", views.reject_call, name="potenciais_militantes.reject"),
]
