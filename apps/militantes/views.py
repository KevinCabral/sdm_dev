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

    query_nome = Q()
    if nome:
        query_nome = Q(nome_completo__icontains=nome) | Q(alcunha__icontains=nome)

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

    from django.db.models import Exists, OuterRef
    user_exists = User.objects.filter(militante_id=OuterRef('pk'))

    militantes = (
        Militantes.objects
        .filter(query_nome, **filtros_outros)
        .prefetch_related('morada_set__geografia')
        .annotate(exist_user=Exists(user_exists))
        .order_by('nome_completo')
        .distinct()
    )
    paginator = Paginator(militantes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    breadcrumbs = [{'title': 'Pagina Inicial', 'url': '/'}, {'title': 'Militantes'}]
    return render(request, "pages/militantes/index.html", {
        "militantes": militantes,
        "page_obj": page_obj,
        "breadcrumbs": breadcrumbs,
        "filters": {
            "estado": estado, "nome": nome, "zona": zona,
            "concelho": concelho, "regiao": regiao, "localidade": localidade,
        },
    })


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

            geografia = Geografia.objects.filter(zona=militantesForm.cleaned_data["zona"]).first()
            morada = Morada(militante=model, morada_atual=militantesForm.cleaned_data["morada_atual"], perto_de=militantesForm.cleaned_data["perto_de"], status='P', geografia=geografia)
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
        geografia = Geografia.objects.filter(zona=morada.geografia.id).first()
        if geografia:
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
            
            geografia = Geografia.objects.filter(zona=militantesForm.cleaned_data["zona"]).first()
            if morada == None:
                morada = Morada(militante=militante, morada_atual=militantesForm.cleaned_data["morada_atual"], perto_de=militantesForm.cleaned_data["perto_de"], status='P', geografia=geografia)
            else:
                morada.morada_atual = militantesForm.cleaned_data["morada_atual"]
                morada.perto_de = militantesForm.cleaned_data["perto_de"]
                morada.geografia = geografia
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
    nome = (request.GET.get("nome") or "").strip()
    filtros_outros = {"estado_militante": 'P'}

    if email_pessoal != "":
        filtros_outros = {"email_pessoal__isnull": True}

    militantes = (
        Militantes.objects
        .filter(**filtros_outros)
        .prefetch_related('morada_set__geografia')
        .order_by('nome_completo')
    )
    if nome:
        militantes = militantes.filter(
            Q(nome_completo__icontains=nome) | Q(alcunha__icontains=nome)
        )
    paginator = Paginator(militantes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "pages/militantes/pedidos.html", {
        "militantes": militantes,
        'page_obj': page_obj,
        'filters': {'nome': nome, 'email_pessoal': email_pessoal},
    })


@login_required
def search(request):
    """Lightweight JSON autocomplete for militantes (Select2 compatible)."""
    q = (request.GET.get("q") or "").strip()
    estado = request.GET.get("estado", "A")
    qs = Militantes.objects.all()
    if estado:
        qs = qs.filter(estado_militante=estado)
    if q:
        qs = qs.filter(Q(nome_completo__icontains=q) | Q(alcunha__icontains=q))
    qs = qs.order_by("nome_completo")[:20]
    results = [{"id": m.pk, "text": m.nome_completo or f"Militante #{m.pk}"} for m in qs]
    return JsonResponse({"results": results})


@login_required
def view(request, id):
    militante = get_object_or_404(
        Militantes.objects.prefetch_related('morada_set__geografia'),
        pk=id,
    )
    morada = militante.morada_set.first()
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Militantes', 'url': '../../'},
        {'title': militante.nome_completo or f'Militante #{militante.pk}'},
    ]
    return render(request, "pages/militantes/view.html", {
        "militante": militante,
        "morada": morada,
        "id": id,
        "breadcrumbs": breadcrumbs,
    })


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
    militantes = (
        Militantes.objects
        .filter(estado_militante='A')
        .prefetch_related('morada_set__geografia')
        .order_by('nome_completo')
    )
    paginator = Paginator(militantes, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, "pages/militantes/aprovados.html", {"militantes": militantes, "page_obj": page_obj})


@login_required
def rejectados(request):
    militantes = (
        Militantes.objects
        .filter(estado_militante='R')
        .prefetch_related('morada_set__geografia')
        .order_by('nome_completo')
    )
    paginator = Paginator(militantes, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, "pages/militantes/rejectados.html", {"militantes": militantes, "page_obj": page_obj})


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
    pais = Geografia.objects.exclude(pais__isnull=True).exclude(pais='').values_list('pais', flat=True).distinct()
    data = [{"id": p, "nome": p} for p in pais]
    return JsonResponse({"data": data})

    
@login_required
def getIlhas(request):
    id_pais = request.GET.get("id_pais", "238")
    ilhas = Geografia.objects.filter(pais=id_pais).exclude(ilha__isnull=True).exclude(ilha='').values_list('ilha', flat=True).distinct()
    data = [{"id": i, "nome": i} for i in ilhas]
    return JsonResponse({"data": data})
    
    
@login_required
def getConcelho(request):
    concelhos = Geografia.objects.filter(ilha=request.GET.get("id_ilha", "")).exclude(concelho__isnull=True).exclude(concelho='').values_list('concelho', flat=True).distinct()
    data = [{"id": c, "nome": c} for c in concelhos]
    return JsonResponse({"data": data})
    
    
@login_required
def getFreguesia(request):
    freguesias = Geografia.objects.filter(concelho=request.GET.get("id_concelho", "")).exclude(freguesia__isnull=True).exclude(freguesia='').values_list('freguesia', flat=True).distinct()
    data = [{"id": f, "nome": f} for f in freguesias]
    return JsonResponse({"data": data})
    
    
@login_required
def getZona(request):
    zonas = Geografia.objects.filter(freguesia=request.GET.get("id_freguesia", "")).exclude(zona__isnull=True).exclude(zona='').values_list('zona', flat=True).distinct()
    data = [{"id": z, "nome": z} for z in zonas]
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
    zonas = Militantes.objects.exclude(morada__geografia__zona__isnull=True).values('morada__geografia__zona').annotate(value=Count('id'))
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
