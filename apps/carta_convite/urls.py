from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="carta_convite.index"),
    path("/create", views.create, name="carta_convite.create"),
    path("/update", views.update, name="carta_convite.update"),
    path("/not-publications", views.notPublications, name="carta_convite.notPublications"),
    path("/publications", views.publications, name="carta_convite.publications"),
    
]





