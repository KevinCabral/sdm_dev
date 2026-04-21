from django.shortcuts import render, get_object_or_404, redirect
from apps.militantes.models import Militantes, Geografia, Morada
from apps.users.models import SendUsernamePassword
from apps.militantes.forms import MilitantesForm
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
import json
from django.http import HttpResponse
import requests
import os
from django.contrib import messages
import csv
from django.http import JsonResponse
from django.forms.models import model_to_dict
from django.db.models import Q
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models.functions import ExtractYear
from django.utils import timezone
from django.db.models import Case, When, CharField, Count, Value, Sum
from datetime import date, timedelta
from django.contrib.auth.models import User
import random
import string

urlApi = os.getenv('URL_API'   , "")
urlApps = "api/militante"

auth = {"apikey":"e6d2d89c1837c6f03b5c93efe181a5df2466551f27cd1062e08341754f44e5fa997b453691928ddc387ebdf7946bb5e3f78df98781eb524962ce41f28f931a7a18c139d8711749af18d6121325de2ada8f7f132e8ff90f9f5a15a189571cf6948b2b86234a942f310e5f3b60a8a54582b3284c32a189774fdccdfc938d295f3c"}

# Create your views here.


@login_required
def index(request):
    estado = request.GET.get("estado", "A")
    nome = request.GET.get("nome", "")
    zona = request.GET.get("zona", "")
    concelho = request.GET.get("concelho", "")
    regiao = request.GET.get("regiao", "")
    localidade = request.GET.get("localidade", "")
    filtros_nome = []
   
    if nome:
        filtros_nome = [
            Q(nome_completo__icontains=nome),
            Q(alcunha__icontains=nome)
        ]
    query_nome = Q()
    for filtro in filtros_nome:
        query_nome |= filtro

    filtros_outros = {}
    if estado:
        filtros_outros['estado_militante'] = estado

    if regiao:
        filtros_outros['morada__geografia__ilha__icontains'] = regiao

    if concelho:
        filtros_outros['morada__geografia__concelho__icontains'] = concelho

    if localidade:
        filtros_outros['morada__geografia__freguesia__icontains'] = localidade

    if zona:
        filtros_outros['morada__geografia__zona__icontains'] = zona

    militantes = Militantes.objects.filter(query_nome, **filtros_outros)
    paginator = Paginator(militantes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    print(militantes)
    for m in page_obj:
            m.exist_user = User.objects.filter(militante_id=m.id).exists()

    breadcrumbs = [{'title': 'Pagina Inicial', 'url':'/'}, {'title': 'Militantes', }]
    return render(request, "pages/militantes/index.html", {"militantes": militantes, "page_obj":page_obj, 'breadcrumbs': breadcrumbs})


@login_required
def create(request):
    militantesForm = MilitantesForm()
    if request.method == "POST":
        militantesForm = MilitantesForm(request.POST, request.FILES)
        
        if militantesForm.is_valid():
            if militantesForm.cleaned_data["tp_documento"] == "CNI":
                militantesForm.cleaned_data["dt_emissao_doc"] = ""

            if militantesForm.cleaned_data["tp_documento"] == "BI":
                militantesForm.cleaned_data["dt_validade_doc"] = ""
            
            model = militantesForm.save(commit=False)
            model.save()

            geografia = Geografia.objects.get(zona=militantesForm.cleaned_data["zona"], nivel_detalhe=5)
            morada = Morada(militante=model, morada_atual=militantesForm.cleaned_data["morada_atual"], perto_de=militantesForm.cleaned_data["perto_de"], status='P', geografia=geografia.zona)
            morada.save()

            messages.success(request, f'Militante criado com sucesso')
            return redirect("militantes.index")
        else:
            print(militantesForm)
            messages.error(request, f'Erro na criaçaõ de militante')
    breadcrumbs = [{'title': 'Pagina Inicial', 'url':'/'}, {'title': 'Militantes', 'url':'../militantes/'}, {'title': 'Criar', }]    
    return render(request, "pages/militantes/create.html", {"militantesForm": militantesForm, 'breadcrumbs':breadcrumbs})


@login_required
def update(request, id):
    militante = get_object_or_404(Militantes, pk=id)
    militantesForm = MilitantesForm(instance=militante)

    try:
        morada = Morada.objects.get(militante=militante)
        militantesForm.initial['morada_atual'] = morada.morada_atual
        militantesForm.initial['perto_de'] = morada.perto_de
        militantesForm.initial['perto_de'] = morada.perto_de
        geografia = Geografia.objects.get(zona=morada.geografia.id, nivel_detalhe=5)
        militantesForm.initial['pais'] = geografia.pais
        militantesForm.initial['regiao'] = geografia.ilha
        militantesForm.initial['concelho'] = geografia.concelho
        militantesForm.initial['zona'] = geografia.zona
        militantesForm.initial['localidade'] = geografia.freguesia
    except:
        morada = None

    if request.method == "POST":
        militantesForm = MilitantesForm(request.POST, request.FILES, instance=militante)
        if militantesForm.is_valid():
            if militantesForm.cleaned_data["tp_documento"] == "CNI":
                militantesForm.cleaned_data["dt_emissao_doc"] = ""

            if militantesForm.cleaned_data["tp_documento"] == "BI":
                militantesForm.cleaned_data["dt_validade_doc"] = ""

            militantesForm.save()
            
            geografia = Geografia.objects.get(zona=militantesForm.cleaned_data["zona"], nivel_detalhe=5)
            if morada == None:
                morada = Morada(militante=model, morada_atual=militantesForm.cleaned_data["morada_atual"], perto_de=militantesForm.cleaned_data["perto_de"], status='P', geografia=geografia)
            else:
                morada.morada_atual = militantesForm.cleaned_data["morada_atual"]
                morada.perto_de = militantesForm.cleaned_data["perto_de"]
                morada.geografia = geografia.zona
            morada.save()
            messages.success(request, f'Militante atualizado')
            return redirect("militantes.index")
        else:
            messages.error(request, f'Erro na atualização de militante')
    breadcrumbs = [{'title': 'Pagina Inicial', 'url':'/'}, {'title': 'Militantes', 'url':'../../'}, {'title': 'Atualizar', }]
    return render(request, "pages/militantes/update.html", {"militantesForm": militantesForm, "id":id, 'militante':militante, 'breadcrumbs':breadcrumbs})


@login_required
def pedidos(request):
    email_pessoal = request.GET.get("email_pessoal", "")
    filtros_outros = {"estado_militante":'P'}

    if email_pessoal != "": 
        filtros_outros = {"email_pessoal__isnull":True}

    militantes = Militantes.objects.filter(**filtros_outros)
    paginator = Paginator(militantes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "pages/militantes/pedidos.html", {"militantes": militantes, 'page_obj':page_obj})


@login_required
def view(request, id):
    url = urlApi + urlApps + "/" + id
    response = requests.get(url, headers=auth)
    data = response.json()
    if response.status_code == 200:
        
        militante = data["results"]
    else:
        messages.error(request, f'Erro na visualização de militante')
        militante = {}
    return render(request, "pages/militantes/view.html", {"militante":militante})


@login_required
def aprovar(request):
    if request.method == "POST":
        id = request.POST.get("id-militante", "")
        email = request.POST.get("email", "None")
        
        url = urlApi + urlApps + "/aprovar"
        headers = auth
        headers["Content-Type"] = "application/json"
        response = requests.post(url, headers=headers, data=json.dumps({"id":id}))
        data = response.json()
        if response.status_code == 200 and data["info"]["status"] == 200:
            messages.success(request, f'Militante aprovado')
            if email != "None":
                sendEmail = SendUsernamePassword(email=email, username=data["results"]["username"], password=data["results"]["password"], request=request)
                sendEmail.send()
            return redirect("militantes.index")
        else:
            messages.error(request, f'Erro em aprovar este militante, tente mais tarde')
            return HttpResponse("error")


@login_required
def rejectar(request):
    if request.method == "POST":
        id = request.POST.get("id-militante", "")
        reason = request.POST.get("reason", "")
        militante = Militantes.objects.get(pk=id)
        if militante:
            militante.estado_militante = "R"
            militante.motivo_rejeicao = reason
            militante.save()
            messages.success(request, f'Militante rejeitado')
            return redirect("militantes.index")
        else:
            messages.error(request, f'Erro em rejeitar Militante')
            return redirect("militantes.index")
    raise ObjectDoesNotExist()


@login_required
def aprovados(request):
    url = urlApi + urlApps + "?status=A"
    response = requests.get(url, headers=auth)
    data = response.json()
    if response.status_code == 200:
        militantes = data["results"]
    else:
        militantes = []
    return render(request, "pages/militantes/aprovados.html", {"militantes": militantes})


@login_required
def rejectados(request):
    url = urlApi + urlApps + "?status=R"
    response = requests.get(url, headers=auth)
    data = response.json()
    if response.status_code == 200:
        militantes = data["results"]
    else:
        militantes = []
    return render(request, "pages/militantes/rejectados.html", {"militantes": militantes})


@login_required
def defaults(request):
    return render(request, "pages/militantes/default.html")


@login_required
def get(request, id):
    militante = Militantes.objects.values().get(pk=id)
    try:
        morada = Morada.objects.get(militante=id)
        militante["morada_atual"] = morada.morada_atual
        militante["perto_de"] = morada.perto_de
        if morada.geografia:
            militante['pais'] = morada.geografia.pais
            militante['concelho'] = morada.geografia.concelho
            militante['zona'] = morada.geografia.zona
            militante['localidade'] = morada.geografia.freguesia
            militante['regiao'] = morada.geografia.ilha
        else: 
            militante['pais'] = ""
            militante['concelho'] = ""
            militante['zona'] = ""
            militante['localidade'] = ""
            militante['regiao'] = ""
    except Morada.DoesNotExist as e:
        pass
    if not(militante):
        messages.error(request, f'Erro na visualização de militante')
        militante = {}
    return JsonResponse(militante)


@login_required
def delete(request):
    if request.method == "POST":
        id = request.POST.get("id-militante", "")
        militante = Militantes.objects.get(pk=id)
        if militante:
            militante.estado_militante = "D"
            militante.save()
            return redirect("militantes.index")
    raise ObjectDoesNotExist()


@login_required
def exportExcel(request):
    estado = request.GET.get("estado", "A")
    nome = request.GET.get("nome", "")
    zona = request.GET.get("zona", "")
    concelho = request.GET.get("concelho", "")
    regiao = request.GET.get("regiao", "")
    localidade = request.GET.get("localidade", "")
    filtros_nome = []
    if nome:
        filtros_nome = [
            Q(nome_completo__icontains=nome),
            Q(alcunha__icontains=nome)
        ]

    query_nome = Q()
    for filtro in filtros_nome:
        query_nome |= filtro

    filtros_outros = {}
    if estado:
        filtros_outros['estado_militante'] = estado

    if regiao:
        filtros_outros['morada__geografia__ilha__icontains'] = regiao

    if concelho:
        filtros_outros['morada__geografia__concelho__icontains'] = concelho

    if localidade:
        filtros_outros['morada__geografia__freguesia__icontains'] = localidade

    if zona:
        filtros_outros['morada__geografia__zona__icontains'] = zona

    militantes = Militantes.objects.filter(query_nome, **filtros_outros)
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="militantes.csv"'},
    )

    writer = csv.writer(response)
    if len(militantes) > 0:
        keys = list(model_to_dict(militantes[0]).keys())
        header = []
        for k in keys: 
            text = k.replace("_", " ")
            header.append(text)
        writer.writerow(header)
        for i in militantes:
            writer.writerow(list(model_to_dict(i).values()))
    return response


@login_required
def notificacaoPedidos(request):
    params = {
        "status":"P",
    }
    url = urlApi + urlApps
    response = requests.get(url, headers=auth, params=params)
    data = response.json()
    total = 0
    if response.status_code == 200:
        militantes = data["results"]
        total = data["info"]["count"]
        if total == "null":
            total = 0
    else:
        militantes = []
        
    return JsonResponse({"militantes": militantes, "total": total})


@login_required
def getPais(request):
    pais = Geografia.objects.filter(nivel_detalhe=1).all()
    data = []
    for p in pais:
        data.append({"id":p.pais, "nome":p.nome_norm})

    return JsonResponse({"data": data})

    
@login_required
def getIlhas(request):
    id_pais = request.GET.get("id_pais", "238")
    pais = Geografia.objects.filter(pais=id_pais, nivel_detalhe=2).all()
    data = []
    for p in pais:
        data.append({"id":p.ilha, "nome":p.nome_norm})

    return JsonResponse({"data": data})
    
    
@login_required
def getConcelho(request):
    pais = Geografia.objects.filter(ilha=request.GET.get("id_ilha", ""), nivel_detalhe=3).all()
    data = []
    for p in pais:
        data.append({"id":p.concelho, "nome":p.nome_norm})

    return JsonResponse({"data": data})
    
    
@login_required
def getFreguesia(request):
    pais = Geografia.objects.filter(concelho=request.GET.get("id_concelho", ""), nivel_detalhe=4).all()
    data = []
    for p in pais:
        data.append({"id":p.freguesia, "nome":p.nome_norm})

    return JsonResponse({"data": data})
    
    
@login_required
def getZona(request):
    pais = Geografia.objects.filter(freguesia=request.GET.get("id_freguesia", ""), nivel_detalhe=5).all()
    data = []
    for p in pais:
        data.append({"id":p.zona, "nome":p.nome_norm})

    return JsonResponse({"data": data})
   

@login_required
def dashboard(request):
    totalMilitantes = Militantes.objects.count()
    militantesAprovado = Militantes.objects.filter(estado_militante='A').count()
    militantesRejeitado = Militantes.objects.filter(estado_militante='R').count()
    return render(request, "pages/militantes/dashboard.html", {"totalMilitantes":totalMilitantes, "militantesAprovado":militantesAprovado, "militantesRejeitado":militantesRejeitado})


@login_required
def distribuicaoGenero(request):
    generos = Militantes.objects.values('genero').annotate(values=Count('genero'))

    total_itens = Militantes.objects.count()

    for genero in generos:
        genero['porcentagem'] = (genero['values'] / total_itens) * 100
    return JsonResponse({"data": list(generos)})


def faixa_etaria(data_nascimento):
    idade = date.today().year - data_nascimento.year
    if idade <= 20:
        return 'Jovem'
    elif 20 < idade <= 50:
        return 'Adulto'
    else:
        return 'Idoso'


@login_required
def distribuicaoIdade(request):

    idades = Militantes.objects.annotate(
        faixa_etaria=Case(
            When(dt_nascimento__gte=date.today() - timedelta(days=365 * 18), then=Value('Jovem')),
            When(dt_nascimento__gte=date.today() - timedelta(days=365 * 30), then=Value('Adulto')),
            default=Value('Idoso'),
            output_field=CharField(),
        )
    ).values('faixa_etaria').annotate(count=Count('id'))

    # ano_atual = timezone.now().year
    # idades = Militantes.objects.annotate(idade=ano_atual - ExtractYear('dt_nascimento')).values('idade').annotate(values=Count('idade'))
    total_itens = Militantes.objects.count()
    data = []
    for idade in idades:
        porcentagem = (idade['count'] / total_itens) * 100
        data.append({"idade":idade['faixa_etaria'], "values":porcentagem})
    return JsonResponse({'data': data})


@login_required
def distribuicaoZona(request):
    zonas = Militantes.objects.filter(morada__geografia__nivel_detalhe=5).values('morada__geografia__nome_norm').annotate(value=Count('id'))
    total_itens = Militantes.objects.count()
    for zona in zonas:
        zona['porcentagem'] = (zona['value'] / total_itens) * 100
    return JsonResponse({'data': list(zonas)})


@login_required
def distribuicaoQuotas(request):
    top_militantes = Militantes.objects.annotate(
        total_pago=Sum('pagamentoquotas__valor__valor')
    ).order_by('-total_pago')[:10]
   
    data = []
    for militante in top_militantes:
        data.append({
            'nome': militante.nome_completo,
            'total_pago': militante.total_pago
        })

    return JsonResponse(data, safe=False)


@login_required
def checkUsername(request):
    try:
        id = request.GET.get('id')
        militante = Militantes.objects.get(pk=id)
        username = militante.nome_completo.lower().split(" ")

        if len(username) == 1: 
            username = username[0]
        else:
            username = username[0] + "_" + username[len(username) - 1]
        count = User.objects.filter(username__startswith=username).count()
        print(username)
        print(f"quantidade: {count}")
        if count == 0:
            return JsonResponse({"error":False, 'username':f"{username}"})
        else:
            # Se o nome de usuário já existir, adiciona um número ao final
            return JsonResponse({"error":False, 'username':f"{username}_{count + 1}"})
    except:
        return JsonResponse({'error': True, 'message':'Militante nao encontrado'})

        
@login_required
def createUser(request):
  if request.method == 'POST':
    idMilitante = request.POST.get("id-militante")
    username = request.POST.get("username")
    email = request.POST.get("email")
    if username and email and idMilitante:

        letters = string.ascii_letters + string.digits
        password = ''.join(random.choice(letters) for _ in range(12))
        user = User.objects.create(username=username, email=email, password=password, militante_id=idMilitante)
        user.save()
        sendEmail = SendUsernamePassword(email=user.email, username=user.username, password=password, request=request)
        sendEmail.send()
        messages.success(request, f'Utilizadaor criado com sucesso e email foi enviado.')
        return redirect('militantes.index')
  return redirect('militantes.index')
