from django.urls import path

from . import views

urlpatterns = [
    path("/index", views.index, name="potenciais_votantes.index"),
    path("/create", views.create, name="potenciais_votantes.create"),
    path("/remover", views.remover, name="potenciais_votantes.remover"),
    path("/<int:id>/detail-json", views.detail_json, name="potenciais_votantes.detail_json"),
    path("/<int:id>/inquerito", views.inquerito, name="potenciais_votantes.inquerito"),
    path("/<int:id>/reject", views.reject_call, name="potenciais_votantes.reject"),
    path("/update/<int:id>", views.update, name="potenciais_votantes.update"),
    path("/<int:id>", views.view, name="potenciais_votantes.view"),
    path("/export/excel", views.exportExcel, name="potenciais_votantes.exportExcel"),
    path("/import/preview", views.import_preview, name="potenciais_votantes.import_preview"),
    path("/import/start", views.import_start, name="potenciais_votantes.import_start"),
    path("/import/<int:job_id>/status", views.import_status, name="potenciais_votantes.import_status"),
]
