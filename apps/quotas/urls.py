from django.urls import path

from . import views

urlpatterns = [
    path("/pagamento", views.pagamento, name="quotas.pagamento"),
    path("/pagamento/view", views.get, name="quotas.view_pagamento"),
    path("/export/excel", views.exportExcel, name="quotas.exportExcel"),
    path("/pagamento/createOrUpdate", views.createOrUpdate, name="quotas.fazer_pagamento"),

    # ValorPagamento CRUD
    path("/valor", views.valor_pagamento_index, name="quotas.valor_index"),
    path("/valor/create-ajax", views.valor_pagamento_create_ajax, name="quotas.valor_create_ajax"),
    path("/valor/<int:valor_id>/update-ajax", views.valor_pagamento_update_ajax, name="quotas.valor_update_ajax"),
    path("/valor/<int:valor_id>/delete-ajax", views.valor_pagamento_delete_ajax, name="quotas.valor_delete_ajax"),
]





