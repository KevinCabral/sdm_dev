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
from django.views.decorators.http import require_POST

from apps.militantes.models import Militantes
from .form import EleitoresForm
from .models import EleicaoImport, Eleitores, Votacao


# ----------------------------------------------------------------------
# Excel column → model field map (shared by preview + import worker)
# ----------------------------------------------------------------------
ELEITOR_COLUMN_MAP = {
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
    """Legacy synchronous import — kept for backwards compatibility.

    The new flow uses /eleitores/import/preview + /import/start + /import/<id>/status.
    """
    if request.method != 'POST' or 'arquivo_excel' not in request.FILES:
        messages.error(request, 'Erro em carregar eleitor')
        return redirect("eleitores.index")

    df = pd.read_excel(request.FILES['arquivo_excel'])
    created = 0
    for _, row in df.iterrows():
        kwargs = {
            field: row[col]
            for col, field in ELEITOR_COLUMN_MAP.items()
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


# ──────────────────────────────────────────────────────────────────────
# New async upload flow: preview → start → poll status
# ──────────────────────────────────────────────────────────────────────

def _read_excel_safe(file_obj):
    """Read an .xlsx/.xls/.csv file into a DataFrame."""
    name = getattr(file_obj, 'name', '') or ''
    if name.lower().endswith('.csv'):
        return pd.read_csv(file_obj)
    return pd.read_excel(file_obj)


@login_required
@require_POST
def import_preview(request):
    """Return the first rows + column metadata for the uploaded file.

    Body: multipart with `arquivo_excel`. No DB writes.
    """
    f = request.FILES.get('arquivo_excel')
    if not f:
        return JsonResponse({'ok': False, 'error': 'Ficheiro não enviado.'}, status=400)
    try:
        df = _read_excel_safe(f)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': f'Não foi possível ler o ficheiro: {exc}'}, status=400)

    columns = list(df.columns)
    detected = [c for c in columns if c in ELEITOR_COLUMN_MAP]
    missing = [c for c in ELEITOR_COLUMN_MAP if c not in columns]
    sample = df.head(20).fillna('').astype(str).to_dict(orient='records')

    return JsonResponse({
        'ok': True,
        'total': int(len(df)),
        'columns': columns,
        'detected': detected,
        'missing': missing,
        'sample': sample,
    })


@login_required
@require_POST
def import_start(request):
    """Save the upload and kick off background processing.

    Body (multipart):
        arquivo_excel: file
        tipo_eleicao: 'L' | 'P' | 'A'
        mes_ano: 'MM/YYYY'
    """
    import re
    import threading

    f = request.FILES.get('arquivo_excel')
    tipo = request.POST.get('tipo_eleicao', '').strip().upper()
    mes_ano = request.POST.get('mes_ano', '').strip()

    if not f:
        return JsonResponse({'ok': False, 'error': 'Ficheiro obrigatório.'}, status=400)
    if tipo not in dict(EleicaoImport.TIPO_CHOICES):
        return JsonResponse({'ok': False, 'error': 'Tipo de eleição inválido.'}, status=400)
    if not re.match(r'^(0[1-9]|1[0-2])/\d{4}$', mes_ano):
        return JsonResponse({'ok': False, 'error': 'Mês/Ano inválido. Formato esperado: MM/YYYY.'}, status=400)

    job = EleicaoImport.objects.create(
        tipo_eleicao=tipo,
        mes_ano=mes_ano,
        arquivo=f,
        nome_original=f.name,
        status=EleicaoImport.STATUS_PENDING,
        criado_por=getattr(request.user, 'id', None),
    )
    job.arquivo.close()

    threading.Thread(target=_run_import_job, args=(job.id,), daemon=True).start()
    return JsonResponse({'ok': True, 'job_id': job.id})


@login_required
def import_status(request, job_id):
    """Poll endpoint for the frontend progress bar."""
    job = get_object_or_404(EleicaoImport, pk=job_id)
    return JsonResponse({
        'ok': True,
        'job_id': job.id,
        'status': job.status,
        'total': job.total_linhas,
        'processed': job.processadas,
        'created': job.criadas,
        'errors': job.erros,
        'percent': job.percent,
        'message': job.mensagem,
        'tipo_eleicao': job.get_tipo_eleicao_display(),
        'mes_ano': job.mes_ano,
    })


def _run_import_job(job_id):
    """Background worker: stream the file, persist eleitores in chunks."""
    from django.db import close_old_connections, transaction

    try:
        job = EleicaoImport.objects.get(pk=job_id)
    except EleicaoImport.DoesNotExist:
        return

    try:
        job.status = EleicaoImport.STATUS_RUNNING
        job.save(update_fields=['status', 'atualizado_em'])

        with job.arquivo.open('rb') as fh:
            df = _read_excel_safe(fh)

        total = len(df)
        job.total_linhas = total
        job.save(update_fields=['total_linhas', 'atualizado_em'])

        chunk_size = 500
        created = 0
        errors = 0
        militante_cache = {}

        for chunk_start in range(0, total, chunk_size):
            chunk = df.iloc[chunk_start:chunk_start + chunk_size]
            objs = []
            for _, row in chunk.iterrows():
                try:
                    kwargs = {
                        field: row[col]
                        for col, field in ELEITOR_COLUMN_MAP.items()
                        if col in df.columns and pd.notna(row[col])
                    }
                    eleitor = Eleitores(**kwargs, falecido=False)
                    militante_id = row.get('ID militante') if 'ID militante' in df.columns else None
                    if pd.notna(militante_id):
                        mid = int(militante_id)
                        if mid not in militante_cache:
                            militante_cache[mid] = Militantes.objects.filter(pk=mid).first()
                        if militante_cache[mid]:
                            eleitor.militante_id = militante_cache[mid]
                    objs.append(eleitor)
                except Exception:
                    errors += 1
            if objs:
                with transaction.atomic():
                    for o in objs:
                        try:
                            o.save()
                            created += 1
                        except Exception:
                            errors += 1

            job.processadas = min(chunk_start + len(chunk), total)
            job.criadas = created
            job.erros = errors
            job.save(update_fields=['processadas', 'criadas', 'erros', 'atualizado_em'])

        job.status = EleicaoImport.STATUS_DONE
        job.mensagem = f'{created} eleitores carregados ({errors} erros).'
        job.save(update_fields=['status', 'mensagem', 'atualizado_em'])
    except Exception as exc:
        job.status = EleicaoImport.STATUS_ERROR
        job.mensagem = str(exc)[:500]
        job.save(update_fields=['status', 'mensagem', 'atualizado_em'])
    finally:
        close_old_connections()


@login_required
def dashboard(request):
    """Aggregate KPIs in a single pass to avoid 7 SELECT count(*)."""
    from django.db.models import Q, Sum, Case, When, IntegerField

    agg = Eleitores.objects.filter(falecido=False).aggregate(
        total=Count('id'),
        mpd=Sum(Case(When(mpd=True, then=1), default=0, output_field=IntegerField())),
        indecisos=Sum(Case(When(indeciso=True, then=1), default=0, output_field=IntegerField())),
        ausentes=Sum(Case(When(ausente=True, then=1), default=0, output_field=IntegerField())),
        nao_vai_votar=Sum(Case(When(nao_vai_votar=True, then=1), default=0, output_field=IntegerField())),
        descarga=Sum(Case(When(descarga=True, then=1), default=0, output_field=IntegerField())),
    )
    total = agg['total'] or 0
    falecidos = Eleitores.objects.filter(falecido=True).count()

    voted_eleitor_ids = (
        Votacao.objects
        .filter(votou=1)
        .exclude(anulado=1)
        .values_list('nr_eleitor', flat=True)
        .distinct()
    )
    total_votaram = (
        Eleitores.objects
        .filter(falecido=False, nr_eleitor__in=voted_eleitor_ids)
        .count()
    )
    total_nao_votaram = max(total - total_votaram, 0)
    total_anuladas = Votacao.objects.filter(anulado=1).count()
    total_votos_validos = Votacao.objects.exclude(anulado=1).filter(votou=1).count()

    def _pct(num, den):
        return round((num / den) * 100, 1) if den else 0.0

    mesas_distintas = (
        Eleitores.objects.filter(falecido=False)
        .exclude(nr_mesa__isnull=True).exclude(nr_mesa__exact='')
        .values('nr_mesa').distinct().count()
    )
    concelhos_distintos = (
        Eleitores.objects.filter(falecido=False)
        .exclude(concelho__isnull=True).exclude(concelho__exact='')
        .values('concelho').distinct().count()
    )

    return render(
        request,
        "pages/eleitores/dashboard.html",
        {
            "totalEleitores": total,
            'totalVotaram': total_votaram,
            "totalNaoVotaram": total_nao_votaram,
            "pctComparecimento": _pct(total_votaram, total),
            "pctAbstencao": _pct(total_nao_votaram, total),
            "totalMpd": agg['mpd'] or 0,
            "pctMpd": _pct(agg['mpd'] or 0, total),
            "totalIndecisos": agg['indecisos'] or 0,
            "totalAusentes": agg['ausentes'] or 0,
            "totalNaoVaiVotar": agg['nao_vai_votar'] or 0,
            "totalDescarga": agg['descarga'] or 0,
            "totalFalecidos": falecidos,
            "totalAnuladas": total_anuladas,
            "totalVotosValidos": total_votos_validos,
            "totalMesas": mesas_distintas,
            "totalConcelhos": concelhos_distintos,
        },
    )


@login_required
def topMesasComparecimento(request):
    """Top mesas by comparecimento %.

    Returns: [{nr_mesa, total, votaram, pct}, ...] ordered by pct desc, then total desc.
    """
    from django.db.models import Q

    voted_ids = (
        Votacao.objects.filter(votou=1).exclude(anulado=1)
        .values_list('nr_eleitor', flat=True)
    )

    rows = (
        Eleitores.objects.filter(falecido=False)
        .exclude(nr_mesa__isnull=True).exclude(nr_mesa__exact='')
        .values('nr_mesa')
        .annotate(
            total=Count('id'),
            votaram=Count('id', filter=Q(nr_eleitor__in=voted_ids)),
        )
    )
    data = []
    for r in rows:
        total = r['total'] or 0
        votaram = r['votaram'] or 0
        pct = round((votaram / total) * 100, 1) if total else 0.0
        data.append({
            'nr_mesa': r['nr_mesa'],
            'total': total,
            'votaram': votaram,
            'pct': pct,
        })
    data.sort(key=lambda r: (-r['pct'], -r['total']))
    limit = int(request.GET.get('limit', '15') or 15)
    return JsonResponse({'data': data[:limit]})


@login_required
def votacaoHoraria(request):
    """Votação distribution by hour of day for the most recent day with votes.

    Useful to spot peak hours during election day.
    """
    from django.db.models.functions import ExtractHour
    from django.db.models import Min, Max

    bounds = Votacao.objects.exclude(anulado=1).filter(votou=1).aggregate(
        last=Max('datetime')
    )
    last = bounds.get('last')
    if not last:
        return JsonResponse({'data': [], 'date': None})

    day_qs = (
        Votacao.objects
        .exclude(anulado=1).filter(votou=1, datetime__date=last.date())
        .annotate(hour=ExtractHour('datetime'))
        .values('hour')
        .annotate(total=Count('id'))
        .order_by('hour')
    )
    counts = {int(r['hour']): r['total'] for r in day_qs}
    data = [{'hour': h, 'total': counts.get(h, 0)} for h in range(24)]
    return JsonResponse({'data': data, 'date': last.date().isoformat()})


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
