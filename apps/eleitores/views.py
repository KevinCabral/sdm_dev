import csv
from datetime import date

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db.models import Count
from django.forms.models import model_to_dict
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.militantes.models import Militantes
from .form import EleitoresForm
from .models import Eleitores, Votacao


def _build_filters(request):
    """Filters shared by index() and exportExcel()."""
    nome = request.GET.get("nome", "")
    nr_mesa = request.GET.get("nr_mesa", "")
    nr_eleitor = request.GET.get("nr_eleitor", "")
    militante = request.GET.get("militante", "false")

    # Treat "falecido = True" as soft-deleted; show everyone else.
    filters = {"falecido": False}
    if nome:
        filters['nome__icontains'] = nome
    if nr_mesa:
        filters['nr_mesa'] = nr_mesa
    if nr_eleitor:
        filters['nr_eleitor'] = nr_eleitor
    if militante == "true":
        filters['militante_id__isnull'] = False
    return filters


@login_required
def index(request):
    eleitores = Eleitores.objects.filter(**_build_filters(request))
    paginator = Paginator(eleitores, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Eleitores'},
    ]
    return render(
        request,
        "pages/eleitores/index.html",
        {'page_obj': page_obj, 'breadcrumbs': breadcrumbs},
    )


@login_required
def create(request):
    form = EleitoresForm()
    if request.method == 'POST':
        form = EleitoresForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Eleitor criado')
            return redirect("eleitores.index")
        messages.error(request, 'Erro em criar eleitor')
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Eleitores', 'url': '../eleitores/index'},
        {'title': 'Criar'},
    ]
    return render(request, "pages/eleitores/create.html", {'form': form, 'breadcrumbs': breadcrumbs})


@login_required
def update(request, id):
    eleitor = get_object_or_404(Eleitores, pk=id)
    form = EleitoresForm(instance=eleitor)
    if request.method == 'POST':
        form = EleitoresForm(request.POST, instance=eleitor)
        if form.is_valid():
            form.save()
            messages.success(request, 'Eleitor atualizado')
            return redirect("eleitores.index")
        messages.error(request, 'Erro em atualizar eleitor')
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Eleitores', 'url': '../../eleitores/index'},
        {'title': 'Atualizar'},
    ]
    return render(
        request,
        "pages/eleitores/update.html",
        {'form': form, 'id': id, 'eleitor': eleitor, 'breadcrumbs': breadcrumbs},
    )


@login_required
def view(request, id):
    eleitor = get_object_or_404(Eleitores, pk=id)
    form = EleitoresForm(instance=eleitor)
    breadcrumbs = [
        {'title': 'Pagina Inicial', 'url': '/'},
        {'title': 'Eleitores', 'url': '../../eleitores/index'},
        {'title': eleitor.nome or f'Eleitor #{eleitor.pk}'},
    ]
    return render(
        request,
        "pages/eleitores/view.html",
        {'form': form, 'id': id, 'eleitor': eleitor, 'breadcrumbs': breadcrumbs},
    )


@login_required
def detail_json(request, id):
    eleitor = get_object_or_404(Eleitores, pk=id)
    return JsonResponse({
        'id': eleitor.id,
        'nome': eleitor.nome,
        'nominho': eleitor.nominho,
        'filiacao': eleitor.filiacao,
        'data_nascimento': eleitor.data_nascimento.isoformat() if eleitor.data_nascimento else None,
        'idade_eleitor': eleitor.idade_eleitor,
        'contato': eleitor.contato,
        'nacionalidade': eleitor.nacionalidade,
        'concelho': eleitor.concelho,
        'zona': eleitor.zona,
        'nr_mesa': eleitor.nr_mesa,
        'nr_eleitor': eleitor.nr_eleitor,
        'falecido': bool(eleitor.falecido),
        'ausente': bool(eleitor.ausente),
        'indeciso': bool(eleitor.indeciso),
        'nao_vai_votar': bool(eleitor.nao_vai_votar),
        'mpd': bool(eleitor.mpd),
        'descarga': bool(eleitor.descarga),
        'militante': eleitor.militante_id.nome_completo if eleitor.militante_id_id else None,
    })


@login_required
def remover(request):
    if request.method != "POST":
        raise ObjectDoesNotExist()
    eleitor = Eleitores.objects.filter(pk=request.POST.get("id", "")).first()
    if eleitor:
        eleitor.falecido = True
        eleitor.save(update_fields=['falecido'])
        messages.success(request, 'Eleitor removido')
        return redirect("eleitores.index")
    messages.error(request, 'Erro em remover Eleitor')
    return redirect("eleitores.index")


def exportExcel(request):
    eleitores = Eleitores.objects.filter(**_build_filters(request))
    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="eleitores.csv"'},
    )
    writer = csv.writer(response)
    if eleitores.exists():
        keys = list(model_to_dict(eleitores[0]).keys())
        writer.writerow([k.replace("_", " ") for k in keys])
        for i in eleitores:
            writer.writerow(list(model_to_dict(i).values()))
    return response


@login_required
def uploadExcel(request):
    """Best-effort import. Expected columns (case-sensitive):
    Nome, Nominho, Filiacao, Data Nascimento, Idade, Contato,
    Nacionalidade, Concelho, Zona, Numero Mesa, Numero Eleitor, ID militante.
    Missing columns are simply skipped.
    """
    if request.method != 'POST' or 'arquivo_excel' not in request.FILES:
        messages.error(request, 'Erro em carregar eleitor')
        return redirect("eleitores.index")

    df = pd.read_excel(request.FILES['arquivo_excel'])
    column_map = {
        'Nome': 'nome',
        'Nominho': 'nominho',
        'Filiacao': 'filiacao',
        'Data Nascimento': 'data_nascimento',
        'Idade': 'idade_eleitor',
        'Contato': 'contato',
        'Nacionalidade': 'nacionalidade',
        'Concelho': 'concelho',
        'Zona': 'zona',
        'Numero Mesa': 'nr_mesa',
        'Numero Eleitor': 'nr_eleitor',
    }
    created = 0
    for _, row in df.iterrows():
        kwargs = {
            field: row[col]
            for col, field in column_map.items()
            if col in df.columns and pd.notna(row[col])
        }
        eleitor = Eleitores(**kwargs)
        militante_id = row.get('ID militante') if 'ID militante' in df.columns else None
        if pd.notna(militante_id):
            try:
                eleitor.militante_id = Militantes.objects.get(pk=militante_id)
            except Militantes.DoesNotExist:
                pass
        eleitor.falecido = False
        eleitor.save()
        created += 1
    messages.success(request, f'{created} eleitores carregados com sucesso')
    return redirect("eleitores.index")


@login_required
def dashboard(request):
    totalEleitores = Eleitores.objects.count()
    totalVotaram = Eleitores.objects.filter(
        nr_eleitor__in=Votacao.objects.filter(votou=True).values_list('nr_eleitor', flat=True)
    ).count()
    totalNaoVotaram = totalEleitores - totalVotaram
    return render(
        request,
        "pages/eleitores/dashboard.html",
        {
            "totalEleitores": totalEleitores,
            'totalVotaram': totalVotaram,
            "totalNaoVotaram": totalNaoVotaram,
        },
    )


@login_required
def distribuicaoGenero(request):
    """Legacy DB has no ``genero`` column — distribute by ``concelho`` instead."""
    rows = Eleitores.objects.values('concelho').annotate(values=Count('concelho'))
    total = Eleitores.objects.count() or 1
    data = [
        {'concelho': r['concelho'] or 'N/A',
         'values': r['values'],
         'porcentagem': (r['values'] / total) * 100}
        for r in rows
    ]
    return JsonResponse({"data": data})


def faixa_etaria(data_nascimento):
    idade = date.today().year - data_nascimento.year
    if idade <= 20:
        return 'Jovem'
    if idade <= 50:
        return 'Adulto'
    return 'Idoso'


@login_required
def distribuicaoIdade(request):
    """Group by faixa etaria using ``idade_eleitor`` when available."""
    buckets = {'Jovem': 0, 'Adulto': 0, 'Idoso': 0}
    for idade in Eleitores.objects.values_list('idade_eleitor', flat=True):
        if idade is None:
            continue
        if idade <= 20:
            buckets['Jovem'] += 1
        elif idade <= 50:
            buckets['Adulto'] += 1
        else:
            buckets['Idoso'] += 1
    total = sum(buckets.values()) or 1
    data = [{'idade': k, 'values': (v / total) * 100} for k, v in buckets.items()]
    return JsonResponse({'data': data})


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
    """``code_regiao`` doesn't exist in the legacy table — group by ``concelho``."""
    porRegiao = (
        Eleitores.objects
        .filter(nr_eleitor__in=Votacao.objects.filter(votou=True).values('nr_eleitor'))
        .values('concelho')
        .annotate(total_eleitores=Count('concelho'))
    )
    return JsonResponse(list(porRegiao), safe=False)
