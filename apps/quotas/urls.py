from django.urls import path

from . import views

urlpatterns = [
    path("/pagamento", views.pagamento, name="quotas.pagamento"),
    path("/pagamento/view", views.get, name="quotas.view_pagamento"),
    path("/export/excel", views.exportExcel, name="quotas.exportExcel"),
    path("/pagamento/createOrUpdate", views.createOrUpdate, name="quotas.fazer_pagamento"),
    
]





