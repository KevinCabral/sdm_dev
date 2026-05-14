from django.urls import path

from . import views

urlpatterns = [
    path("/index", views.index, name="eleitores.index"),
    path("/dashboard", views.dashboard, name="eleitores.dashboard"), 
    path("/create", views.create, name="eleitores.create"),
    path("/remover", views.remover, name="eleitores.remover"),
    path("/<int:id>/detail-json", views.detail_json, name="eleitores.detail_json"),
    path("/update/<int:id>", views.update, name="eleitores.update"),
    path("/<int:id>", views.view, name="eleitores.view"), 
    path("/export/excel", views.exportExcel, name="eleitores.exportExcel"),
    path("/upload/excel", views.uploadExcel, name="eleitores.uploadExcel"),
    path("/import/preview", views.import_preview, name="eleitores.import_preview"),
    path("/import/start", views.import_start, name="eleitores.import_start"),
    path("/import/<int:job_id>/status", views.import_status, name="eleitores.import_status"),
    path("/distribuicao-genero", views.distribuicaoGenero, name="eleitores.distribuicaoGenero"),
    path("/distribuicao-idade", views.distribuicaoIdade, name="eleitores.distribuicaoIdade"),
    path("/distribuicao-mesa", views.distribuicaoNrMesa, name="eleitores.distribuicaoNrMesa"),
    path("/distribuicao-mesa-votacao", views.distribuicaoNrMesaVotacao, name="eleitores.distribuicaoNrMesaVotacao"),
    path("/distribuicao-regiao-votacao", views.distribuicaoNrMesaVotacaoRegiao, name="eleitores.distribuicaoNrMesaVotacaoRegiao"),
    path("/top-mesas-comparecimento", views.topMesasComparecimento, name="eleitores.topMesasComparecimento"),
    path("/votacao-horaria", views.votacaoHoraria, name="eleitores.votacaoHoraria"),

    # Caderno Eleitoral 2026
    path("/caderno-2026/import/preview", views.caderno_2026_import_preview, name="eleitores.caderno_2026_import_preview"),
    path("/caderno-2026/import", views.caderno_2026_import, name="eleitores.caderno_2026_import"),
]