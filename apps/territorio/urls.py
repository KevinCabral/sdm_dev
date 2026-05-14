from django.urls import path

from . import views

urlpatterns = [
    path("/import/preview", views.import_preview, name="territorio.import_preview"),
    path("/import/execute", views.import_execute, name="territorio.import_execute"),
    path("/circulos/search", views.search_circulos, name="territorio.search_circulos"),
    path("/concelhos/search", views.search_concelhos, name="territorio.search_concelhos"),
    path("/zonas/search", views.search_zonas, name="territorio.search_zonas"),
]
