from django.shortcuts import render
import requests
from django.shortcuts import render, get_object_or_404,redirect
from .models import PagamentoQuotas,SendComprovativo
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import csv
from django.http import JsonResponse
from django.http import HttpResponse
from django.forms.models import model_to_dict
from .form import PagamentoQuotasForm
from django.core.exceptions import ObjectDoesNotExist


@login_required
def createOrUpdate(request):
    form = PagamentoQuotasForm()
    if request.method == 'POST':
        id = request.POST.get("id", "")
        if id != "":
            pagamento = PagamentoQuotas.objects.get(pk=id)
            form = PagamentoQuotasForm(request.POST, request.FILES,instance=pagamento)
        else:
            form = PagamentoQuotasForm(request.POST, request.FILES)
        if form.is_valid():
            pagamento = form.save()
            if id != "":
                messages.success(request, f'Pagamento Atualizado')
            else:
                email = SendComprovativo(request=request,email=pagamento.militante.email_pessoal, nome=pagamento.militante.nome_completo ,text="O seu pagamento foi confirmado, no valor: "+str(pagamento.valor.valor) +".", anexo=pagamento.anexo_id.path,)
                email.send()
                messages.success(request, f'Pagamento feito')
            return redirect("quotas.pagamento")
        else:
            print(form)
            if id != "":
                messages.error(request, f'Erro em atualizar pagamento')
            else:
                messages.error(request, f'Erro em fazer pagamento')
    return redirect("quotas.pagamento")


@login_required
def remover(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        pagamento = PagamentoQuotas.objects.get(pk=id)
        if pagamento:
            pagamento.status = 0
            pagamento.save()
            messages.success(request, f'Pagamento removido')
            return redirect("quotas.pagamento")

        messages.error(request, f'Erro em remover Pagamento')
        return redirect("quotas.pagamento")
    raise ObjectDoesNotExist()

@login_required
def pagamento(request):
    nome = request.GET.get("nome", "")
    data_inicio = request.GET.get("data_inicio", "")
    data_fim = request.GET.get("data_fim", "")
    filtro = {}
    
    if nome:
        filtro['militante__nome_completo__icontains'] = nome

    if data_inicio and data_fim:
        filtro['data_pagamento__range'] = (data_inicio, data_fim)

    pagamento = PagamentoQuotas.objects.filter(**filtro)
    paginator = Paginator(pagamento, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Pagamentos de Quotas'}]
    return render(request, "pages/quotas/pagamento.html", {"page_obj":page_obj,'form':PagamentoQuotasForm,'breadcrumbs':breadcrumbs})


@login_required
def get(request):
    id = request.GET.get("id","")
    if id == "":
        return JsonResponse({})
    
    pagamento = PagamentoQuotas.objects.get(pk=id)
    
    
    if not(pagamento):
        messages.error(request, f'Erro na visualização de Pagamento')
        data = {}
    else:
        data = {
            "militante":model_to_dict(pagamento.militante),
            "valor":model_to_dict(pagamento.valor),
            "data_pagamento":pagamento.data_pagamento
        }

        if  pagamento.anexo_id:
            data["anexo"] = pagamento.anexo_id.url
        else:
            data["anexo"] = ""
    return JsonResponse(data)

@login_required
def exportExcel(request):
    nome = request.GET.get("nome", "")
    data_inicio = request.GET.get("data_inicio", "")
    data_fim = request.GET.get("data_fim", "")
    filtro = {}
    
    if nome:
        filtro['militante__nome_completo__icontains'] = nome

    if data_inicio and data_fim:
        filtro['data__range'] = (data_inicio, data_fim)

    pagamento = PagamentoQuotas.objects(filtro).all()
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pagamento_quotas.csv"'},
    )

    writer = csv.writer(response)
    if len(pagamento) > 0:
        keys = list(model_to_dict(pagamento[0]).keys())
        header = []
        for k in keys: 
            text = k.replace("_", " ")
            header.append(text)
        writer.writerow(header)
        for i in pagamento:
            writer.writerow(list(model_to_dict(i).values()))
    return response
