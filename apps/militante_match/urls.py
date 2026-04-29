from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="militante_match.dashboard"),
    path("lista/", views.index, name="militante_match.index"),
    path("run/", views.run_batch, name="militante_match.run"),
    path("manual/<int:eleitor_id>/", views.manual_match, name="militante_match.manual_match"),
    path("manual/<int:eleitor_id>/link/", views.manual_link, name="militante_match.manual_link"),
    path("<int:match_id>/confirmar/", views.confirm, name="militante_match.confirm"),
    path("<int:match_id>/rejeitar/", views.reject, name="militante_match.reject"),
    path("<int:match_id>/reabrir/", views.reset, name="militante_match.reset"),
    path("api/militantes/", views.militante_search_json, name="militante_match.militante_search_json"),
]
