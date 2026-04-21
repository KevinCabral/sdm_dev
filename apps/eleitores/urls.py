from django.urls import path

from . import views

urlpatterns = [
    path("/index", views.index, name="eleitores.index"),
    path("/dashboard", views.dashboard, name="eleitores.dashboard"), 
    path("/create", views.create, name="eleitores.create"),
    path("/remover", views.remover, name="eleitores.remover"),
    path("/update/<int:id>", views.update, name="eleitores.update"),
    path("/<int:id>", views.view, name="eleitores.view"), 
    path("/export/excel", views.exportExcel, name="eleitores.exportExcel"),
    path("/upload/excel", views.uploadExcel, name="eleitores.uploadExcel"),
    path("/distribuicao-genero", views.distribuicaoGenero, name="eleitores.distribuicaoGenero"),
    path("/distribuicao-idade", views.distribuicaoIdade, name="eleitores.distribuicaoIdade"),
    path("/distribuicao-mesa", views.distribuicaoNrMesa, name="eleitores.distribuicaoNrMesa"),
    path("/distribuicao-mesa-votacao", views.distribuicaoNrMesaVotacao, name="eleitores.distribuicaoNrMesaVotacao"),
    path("/distribuicao-regiao-votacao", views.distribuicaoNrMesaVotacaoRegiao, name="eleitores.distribuicaoNrMesaVotacaoRegiao"),
    

    
    
]





