from django.shortcuts import render,get_object_or_404,redirect
from .models import Eleitores,Votacao
from .form import EleitoresForm
from apps.militantes.models import Militantes
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
import csv
from django.forms.models import model_to_dict
import pandas as pd
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Case, When, CharField, Count,Value,Sum
from datetime import date,timedelta



# Total votos por regiao e

@login_required
def index(request):
    nome = request.GET.get("nome", "")
    nr_mesa = request.GET.get("nr_mesa", "")
    nr_eleitor = request.GET.get("nr_eleitor", "")
    militante = request.GET.get("militante", "false")

    filtros_outros = {"status":1}
    if nome:
        filtros_outros['nome__icontains'] = nome

    if nr_mesa:
        filtros_outros['nr_mesa'] = nr_mesa

    if nr_eleitor:
        filtros_outros['nr_eleitor'] = nr_eleitor

    if militante == "true":
        filtros_outros['militante_id__isnull'] = False


    eleitores = Eleitores.objects.filter(**filtros_outros)
    paginator = Paginator(eleitores, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Eleitores',}]    
    return render(request, "pages/eleitores/index.html",{'page_obj': page_obj,'breadcrumbs':breadcrumbs})


@login_required
def create(request):
    form = EleitoresForm()
    if request.method == 'POST':
        form = EleitoresForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Eleitor criado')
            return redirect("eleitores.index")
        else:
            messages.success(request, f'Erro em criar eleitor')
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Eleitores','url':'../eleitores/index'},{'title': 'Criar',}]
    return render(request, "pages/eleitores/create.html", {'form': form,'breadcrumbs':breadcrumbs})
    
@login_required
def update(request, id):
    eleitor = get_object_or_404(Eleitores, pk=id)
    form = EleitoresForm(instance=eleitor)
    if request.method == 'POST':
        form = EleitoresForm(request.POST,instance=eleitor)
        militante = request.POST.get('militante_id')
        try:
            if militante:
                militante = Militantes.objects.get(id=militante)
                form.instance.militante_id = militante
        except Militantes.DoesNotExist:
            messages.error(request, f'Eleitor selecionado não existe')
            
        if form.is_valid():
            form.save()
            messages.success(request, f'Eleitor atualizado')
            return redirect("eleitores.index")
        else:
            messages.success(request, f'Erro em atualizar eleitor')
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Eleitores','url':'../../eleitores/index'},{'title': 'Atualizar',}]
    return render(request, "pages/eleitores/update.html",{'form': form,'breadcrumbs':breadcrumbs})


@login_required
def view(request, id):
    eleitor = get_object_or_404(Eleitores, pk=id)
    form = EleitoresForm(instance=eleitor)
    breadcrumbs = [{'title': 'Pagina Inicial','url':'/'},{'title': 'Eleitores','url':'../../eleitores/index'},{'title': eleitor.nome,}]
    return render(request, "pages/eleitores/view.html",{'form': form,'id':id,'breadcrumbs':breadcrumbs})


@login_required
def remover(request):
    if request.method == "POST":
        id = request.POST.get("id", "")
        eleitor = Eleitores.objects.get(pk=id)
        if eleitor:
            eleitor.status = 0
            eleitor.save()
            messages.success(request, f'Eleitor removido')
            return redirect("eleitores.index")

        messages.error(request, f'Erro em remover Eleitor')
        return redirect("eleitores.index")
    raise ObjectDoesNotExist()

def exportExcel(request):
    nome = request.GET.get("nome", "")
    nr_mesa = request.GET.get("nr_mesa", "")
    nr_eleitor = request.GET.get("nr_eleitor", "")
    militante = request.GET.get("militante", "false")

    filtros_outros = {"status":1}
    if nome:
        filtros_outros['nome__icontains'] = nome

    if nr_mesa:
        filtros_outros['nr_mesa'] = nr_mesa

    if nr_eleitor:
        filtros_outros['nr_eleitor'] = nr_eleitor
    
    if militante == "true":
        filtros_outros['militante_id__isnull'] = False


    eleitores = Eleitores.objects.filter(**filtros_outros)
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="eleitores.csv"'},
    )

    writer = csv.writer(response)
    if len(eleitores) > 0:
        keys = list(model_to_dict(eleitores[0]).keys())
        header = []
        for k in keys: 
            text = k.replace("_", " ")
            header.append(text)
        writer.writerow(header)
        for i in eleitores:
            writer.writerow(list(model_to_dict(i).values()))
    return response

@login_required
def uploadExcel(request):
    if request.method == 'POST' and request.FILES['arquivo_excel']:
        eleitores = request.FILES['arquivo_excel']
        df = pd.read_excel(eleitores)
        for index, row in df.iterrows():
            eleitor = Eleitores(
             nome=row['Nome'],
             alcunha=row['Alcunha'],
             nr_identificacao=row['Numero Identificação'],
             data_nascimento=row['Data Nascimento'],
             genero = row['Genero'],
             pai=row['Pai'],
             mae=row['Mae'],
             pais=row['Pais'],
             ilha=row['Ilha'],
             conc_pais_res=row['Concelho Pais Residencia'],
             local_cidade_res=row['Local Cidade Residencia'],
             morada=row['Morada'],
             telefone=row['Telefone'],
             telemovel=row['Telemovel'],
             id_obito=row['Id Obito'],
             partido_voto=row['Partido Voto'],
             acompanhamento=row['Pcompanhamento'],
             transporte=row['Transporte'],
             tp_associado=row['Tipo Associado'],
             desloca_outro_concelho=row['Desloca Outro Concelho'],
             desloca_de=row['Desloca De'],
             gv=row['GV'],
             desloca_para=row['Desloca Para'],
             code_regiao=row['Codigo Região'],
             observacoes=row['Observacoes'],
             nr_eleitor=row['Numero Eleitor'],
             nr_mesa=row['Numero Mesa'],
             estado_sensibilidade= row['Estado Sensibilidade']
             )

            if row['ID militante']:
                militante = Militantes.objects.get(pk=row['ID militante'])
                if militante:
                    eleitor.militante_id = militante
            eleitor.status = 1
            eleitor.save()
        messages.success(request, f'Eleitores carregado com sucesso')
        return redirect("eleitores.index")
    else:
        messages.error(request, f'Erro em carregar eleitor')
        return redirect("eleitores.index")


@login_required
def dashboard(request):
    totalEleitores = Eleitores.objects.count()
    totalVotaram = Eleitores.objects.filter(nr_eleitor__in= Votacao.objects.filter(votou=True).values_list('nr_eleitor', flat=True)).count()
    totalNaoVotaram = totalEleitores - totalVotaram

    return render(request, "pages/eleitores/dashboard.html",{"totalEleitores":totalEleitores,'totalVotaram':totalVotaram,"totalNaoVotaram":totalNaoVotaram})

@login_required
def distribuicaoGenero(request):
    generos = Eleitores.objects.values('genero').annotate(values=Count('genero'))

    total_itens = Eleitores.objects.count()

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
    idades = Eleitores.objects.annotate(
        faixa_etaria=Case(
            When(data_nascimento=date.today()-timedelta(days=365*18), then=Value('Jovem')),
            When(data_nascimento=date.today()-timedelta(days=365*30), then=Value('Adulto')),
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
        data.append({"idade":idade['faixa_etaria'],"values":porcentagem})
    return JsonResponse( {'data': data})


@login_required
def distribuicaoNrMesa(request):
    n_mesa = Eleitores.objects.values('nr_mesa').annotate(total_eleitores=Count('nr_mesa'))
    return JsonResponse(list(n_mesa), safe=False)

@login_required
def distribuicaoNrMesaVotacao(request):
    n_mesa = Votacao.objects.values('nr_mesa').annotate(total_votacao=Count('nr_mesa'))
    return JsonResponse(list(n_mesa), safe=False)


@login_required
def distribuicaoNrMesaVotacaoRegiao(request):
    porRegiao = Eleitores.objects.filter(nr_eleitor__in=Votacao.objects.filter(votou=True).values('nr_eleitor')).values('code_regiao').annotate(total_eleitores=Count('code_regiao'))
    return JsonResponse(list(porRegiao), safe=False)
