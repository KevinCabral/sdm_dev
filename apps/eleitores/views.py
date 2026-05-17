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
from .models import CadernoEleitoral2026, CadernoEleitoral2026Import


# ----------------------------------------------------------------------
# Excel column → model field map (shared by preview + import worker)
# ----------------------------------------------------------------------
# Map of NORMALIZED header (lowercased, single-spaced, underscores→space)
# to a tuple (model_field, kind). `kind` drives type coercion.
ELEITOR_FIELD_MAP = {
    'nome':                 ('nome', 'str'),
    'nominho':              ('nominho', 'str'),
    'filiacao':             ('filiacao', 'str'),
    'filiação':             ('filiacao', 'str'),
    'data nascimento':      ('data_nascimento', 'date'),
    'data de nascimento':   ('data_nascimento', 'date'),
    'idade':                ('idade_eleitor', 'int'),
    'idade eleitor':        ('idade_eleitor', 'int'),
    'contato':              ('contato', 'str'),
    'contacto':             ('contato', 'str'),
    'nacionalidade':        ('nacionalidade', 'str'),
    'concelho':             ('concelho', 'str'),
    'zona':                 ('zona', 'str'),
    'numero mesa':          ('nr_mesa', 'str'),
    'nr mesa':              ('nr_mesa', 'str'),
    'numero eleitor':       ('nr_eleitor', 'int'),
    'nr eleitor':           ('nr_eleitor', 'int'),
    'falecido':             ('falecido', 'bool'),
    'ausente':              ('ausente', 'bool'),
    'indeciso':             ('indeciso', 'bool'),
    'nao vai votar':        ('nao_vai_votar', 'bool'),
    'não vai votar':        ('nao_vai_votar', 'bool'),
    'mpd':                  ('mpd', 'bool'),
    'descarga':             ('descarga', 'bool'),
}

# Headers that identify the optional militante FK column.
MILITANTE_ID_HEADERS = {'id militante', 'militante id', 'militante'}


def _norm_header(s):
    """Lowercase, trim, collapse whitespace, treat _ and - as spaces."""
    return ' '.join(
        str(s).strip().lower().replace('_', ' ').replace('-', ' ').split()
    )


def _build_column_map(df_columns):
    """Return {original_col: (model_field, kind)} for matched columns."""
    mapping = {}
    for col in df_columns:
        spec = ELEITOR_FIELD_MAP.get(_norm_header(col))
        if spec:
            mapping[col] = spec
    return mapping


def _find_militante_col(df_columns):
    for col in df_columns:
        if _norm_header(col) in MILITANTE_ID_HEADERS:
            return col
    return None


def _coerce_value(value, kind):
    """Convert a raw cell value to the type required by the model field."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None

    if kind == 'bool':
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in ('true', '1', 'sim', 'yes', 'y', 's', 'verdadeiro'):
            return True
        if s in ('false', '0', 'nao', 'não', 'no', 'n', 'falso', ''):
            return False
        return None

    if kind == 'int':
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    if kind == 'date':
        try:
            d = pd.to_datetime(value, errors='coerce')
        except Exception:
            return None
        if pd.isna(d):
            return None
        return d.date() if hasattr(d, 'date') else d

    s = str(value).strip()
    if not s or s.lower() in ('nan', 'none', 'null'):
        return None
    return s


def _row_to_kwargs(row, col_map):
    """Build model kwargs from a DataFrame row using the prepared col_map."""
    kwargs = {}
    for col, (field, kind) in col_map.items():
        if col not in row.index:
            continue
        coerced = _coerce_value(row[col], kind)
        if coerced is not None:
            kwargs[field] = coerced
    return kwargs


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

    df = _read_excel_safe(request.FILES['arquivo_excel'])
    col_map = _build_column_map(df.columns)
    militante_col = _find_militante_col(df.columns)
    existing_keys = set(
        Eleitores.objects
        .exclude(nr_mesa__isnull=True)
        .exclude(nr_eleitor__isnull=True)
        .values_list('nr_mesa', 'nr_eleitor')
    )
    seen_in_file = set()
    created = 0
    duplicates = 0
    for _, row in df.iterrows():
        kwargs = _row_to_kwargs(row, col_map)
        if not kwargs:
            continue  # skip blank/unmapped rows instead of creating empty eleitores
        nr_mesa = kwargs.get('nr_mesa')
        nr_eleitor = kwargs.get('nr_eleitor')
        if nr_mesa is not None and nr_eleitor is not None:
            key = (nr_mesa, nr_eleitor)
            if key in existing_keys or key in seen_in_file:
                duplicates += 1
                continue
            seen_in_file.add(key)
        eleitor = Eleitores(**kwargs)
        if militante_col is not None:
            mid = _coerce_value(row.get(militante_col), 'int')
            if mid is not None:
                try:
                    eleitor.militante_id = Militantes.objects.get(pk=mid)
                except Militantes.DoesNotExist:
                    pass
        if eleitor.falecido is None:
            eleitor.falecido = False
        eleitor.save()
        created += 1
    messages.success(
        request,
        f'{created} eleitores carregados, {duplicates} duplicados ignorados.',
    )
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
    col_map = _build_column_map(columns)
    detected = list(col_map.keys())
    mapped_fields = {field for field, _ in col_map.values()}
    # Required model fields we expect to see at minimum.
    required_fields = ['nome', 'nr_mesa', 'nr_eleitor']
    missing = [f for f in required_fields if f not in mapped_fields]
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
    overwrite = request.POST.get('overwrite', '').strip().lower() in ('1', 'true', 'on', 'yes')

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

    threading.Thread(
        target=_run_import_job, args=(job.id,), kwargs={'overwrite': overwrite}, daemon=True,
    ).start()
    return JsonResponse({'ok': True, 'job_id': job.id, 'overwrite': overwrite})


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
        'duplicates': job.duplicadas,
        'updated': job.atualizadas,
        'errors': job.erros,
        'percent': job.percent,
        'message': job.mensagem,
        'tipo_eleicao': job.get_tipo_eleicao_display(),
        'mes_ano': job.mes_ano,
    })


def _run_import_job(job_id, overwrite=False):
    """Background worker: stream the file, persist eleitores in chunks.

    Args:
        job_id: PK of the EleicaoImport row to process.
        overwrite: When True, rows whose (nr_mesa, nr_eleitor) already exist
            in the DB are updated in-place instead of being skipped.
    """
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
        updated = 0
        errors = 0
        duplicates = 0
        militante_cache = {}
        col_map = _build_column_map(df.columns)
        militante_col = _find_militante_col(df.columns)

        # Pre-load existing (nr_mesa, nr_eleitor) pairs to detect duplicates
        # against the database. Using a set keeps the per-row check at O(1).
        existing_keys = set(
            Eleitores.objects
            .exclude(nr_mesa__isnull=True)
            .exclude(nr_eleitor__isnull=True)
            .values_list('nr_mesa', 'nr_eleitor')
        )
        # Also dedupe rows that repeat within the same upload file.
        seen_in_file = set()

        for chunk_start in range(0, total, chunk_size):
            chunk = df.iloc[chunk_start:chunk_start + chunk_size]
            inserts = []   # New eleitores to bulk-create
            updates = []   # (key, kwargs, militante) tuples for existing rows
            for _, row in chunk.iterrows():
                try:
                    kwargs = _row_to_kwargs(row, col_map)
                    if not kwargs:
                        # Skip rows that didn't map to any field (blank lines, etc.)
                        continue

                    militante_obj = None
                    if militante_col is not None:
                        mid = _coerce_value(row.get(militante_col), 'int')
                        if mid is not None:
                            if mid not in militante_cache:
                                militante_cache[mid] = Militantes.objects.filter(pk=mid).first()
                            militante_obj = militante_cache[mid]

                    # Duplicate check on the natural key (nr_mesa, nr_eleitor).
                    nr_mesa = kwargs.get('nr_mesa')
                    nr_eleitor = kwargs.get('nr_eleitor')
                    has_key = nr_mesa is not None and nr_eleitor is not None
                    key = (nr_mesa, nr_eleitor) if has_key else None

                    if has_key and key in seen_in_file:
                        # Same row repeated within this very file → always skip.
                        duplicates += 1
                        continue

                    if has_key and key in existing_keys:
                        if overwrite:
                            updates.append((key, kwargs, militante_obj))
                            seen_in_file.add(key)
                        else:
                            duplicates += 1
                        continue

                    if has_key:
                        seen_in_file.add(key)
                    kwargs.setdefault('falecido', False)
                    eleitor = Eleitores(**kwargs)
                    if militante_obj is not None:
                        eleitor.militante_id = militante_obj
                    inserts.append(eleitor)
                except Exception:
                    errors += 1

            if inserts:
                with transaction.atomic():
                    for o in inserts:
                        try:
                            o.save()
                            created += 1
                        except Exception:
                            errors += 1

            if updates:
                with transaction.atomic():
                    for key, kwargs, militante_obj in updates:
                        try:
                            update_fields = dict(kwargs)
                            if militante_obj is not None:
                                update_fields['militante_id'] = militante_obj
                            # Pop natural-key fields; they're the lookup, not values to overwrite.
                            update_fields.pop('nr_mesa', None)
                            update_fields.pop('nr_eleitor', None)
                            n = Eleitores.objects.filter(
                                nr_mesa=key[0], nr_eleitor=key[1],
                            ).update(**update_fields) if update_fields else 0
                            if n:
                                updated += n
                        except Exception:
                            errors += 1

            job.processadas = min(chunk_start + len(chunk), total)
            job.criadas = created
            job.duplicadas = duplicates
            job.atualizadas = updated
            job.erros = errors
            job.save(update_fields=[
                'processadas', 'criadas', 'duplicadas', 'atualizadas',
                'erros', 'atualizado_em',
            ])

        job.status = EleicaoImport.STATUS_DONE
        job.mensagem = (
            f'{created} criados, {updated} atualizados, '
            f'{duplicates} duplicados ignorados, {errors} erros (de {total} linhas).'
        )
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


# --------------------------------------------------------------------------- #
# Caderno Eleitoral 2026 — CSV/XLSX import
# Columns expected (case/accents flexible):
#   ILHA, CRE, POSTO, CONCELHO, MESA  (header metadata; can also be supplied
#                                      as defaults via the import form)
#   Nº (or NUMERO), NOME, FILIAÇÃO, DATA NASC, DESCARGA
# Date format: DD-MM-YYYY (e.g. 11-11-1996). DD/MM/YYYY also accepted.
# --------------------------------------------------------------------------- #

import io as _cad_io
from datetime import datetime as _cad_datetime

CADERNO_COLUMN_ALIASES = {
    "ilha":             "ilha",
    "cre":              "cre",
    "cre de":           "cre",
    "posto":            "posto",
    "concelho":         "concelho",
    "mesa":             "mesa",
    "nr mesa":          "mesa",
    "numero mesa":      "mesa",

    "no":               "numero",
    "nº":               "numero",
    "n":                "numero",
    "n.":               "numero",
    "num":              "numero",
    "numero":           "numero",
    "número":           "numero",

    "nome":             "nome",

    "filiacao":         "filiacao",
    "filiação":         "filiacao",
    "pais":             "filiacao",
    "país":             "filiacao",

    "pai":              "nome_pai",
    "nome pai":         "nome_pai",
    "nome do pai":      "nome_pai",
    "mae":              "nome_mae",
    "mãe":              "nome_mae",
    "nome mae":         "nome_mae",
    "nome da mae":      "nome_mae",
    "nome da mãe":      "nome_mae",

    "data nasc":        "data_nascimento",
    "data nasc.":       "data_nascimento",
    "data nascimento":  "data_nascimento",
    "data de nascimento": "data_nascimento",
    "nascimento":       "data_nascimento",
    "dn":               "data_nascimento",

    "descarga":         "descarga",
}


def _cad_norm(s):
    return ' '.join(str(s).strip().lower().replace('_', ' ').replace('-', ' ').split())


def _cad_clean(value):
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
        text = text[:-2]
    return text


def _cad_parse_int(value):
    text = _cad_clean(value)
    if not text:
        return None
    # accepts "1/384" (take part before '/')
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _cad_parse_bool(value):
    s = _cad_clean(value).lower()
    if not s:
        return False
    return s in ("true", "1", "sim", "yes", "y", "s", "x", "verdadeiro")


def _cad_parse_date(value):
    text = _cad_clean(value)
    if not text:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return _cad_datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _cad_load_dataframe(upload):
    name = (upload.name or "").lower()
    raw = upload.read()
    upload.seek(0)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        readers = [lambda b: pd.read_excel(_cad_io.BytesIO(b), dtype=str, keep_default_na=False)]
    else:
        # CSV — try common separators / encodings
        def _read_csv(b):
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    text = b.decode(enc)
                except Exception:
                    continue
                for sep in (",", ";", "\t", "|"):
                    try:
                        df = pd.read_csv(_cad_io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
                    except Exception:
                        continue
                    if df.shape[1] >= 2:
                        return df
            return None
        readers = [_read_csv, lambda b: pd.read_excel(_cad_io.BytesIO(b), dtype=str, keep_default_na=False)]
    for reader in readers:
        try:
            df = reader(raw)
            if df is not None and not df.empty:
                return df
        except Exception:
            continue
    return None


def _cad_build_colmap(df_columns):
    mapping = {}
    for col in df_columns:
        target = CADERNO_COLUMN_ALIASES.get(_cad_norm(col))
        if target and target not in mapping.values():
            mapping[col] = target
    return mapping


# ---- PDF support (Caderno Eleitoral 2026 official layout) ----

import re as _cad_re

_CAD_DATE_RE = _cad_re.compile(r"\b(\d{2}-\d{2}-\d{4})\b")
_CAD_NUMBER_RE = _cad_re.compile(r"^(\d+)\s*/\s*(\d+)\b")
_CAD_HEADER_RES = {
    "ilha":     _cad_re.compile(r"ILHA\s*:\s*([A-Z0-9ÁÉÍÓÚÂÊÔÃÕÇ \-]+?)(?=\s{2,}|\s+POSTO|\s+CONCELHO|\s+CRE|\s+MESA|$)"),
    "posto":    _cad_re.compile(r"POSTO\s*:\s*([A-Z0-9ÁÉÍÓÚÂÊÔÃÕÇ \-]+?)(?=\s{2,}|\s+ILHA|\s+CONCELHO|\s+CRE|\s+MESA|$)"),
    "concelho": _cad_re.compile(r"CONCELHO\s*:\s*([A-Z0-9ÁÉÍÓÚÂÊÔÃÕÇ \-]+?)(?=\s{2,}|\s+POSTO|\s+ILHA|\s+CRE|\s+MESA|$)"),
    "mesa":     _cad_re.compile(r"MESA\s*:\s*([A-Z0-9\-]+)"),
    "cre":      _cad_re.compile(r"CRE\s+DE\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ \-]+?)(?=\s{2,}|$)"),
}


def _cad_extract_pdf_text_rows(text):
    """Heuristic line-based parser used when extract_tables() fails or returns nothing."""
    out = []
    if not text:
        return out
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Skip page headers/footers
        upper = line.upper()
        if any(tag in upper for tag in (
            "REPÚBLICA DE CABO VERDE", "ELEIÇÃO DOS TITULARES", "CRE DE ",
            "ILHA:", "CONCELHO:", "POSTO:", "MESA:", "NACIONAIS",
            "Nº NOME FILIAÇÃO", "ÚLTIMA ACTUALIZAÇÃO", "PAGE ",
        )):
            # Still allow a row that begins with N/N — handled below
            mnum_inline = _CAD_NUMBER_RE.match(line)
            if not mnum_inline:
                continue
        mnum = _CAD_NUMBER_RE.match(line)
        if mnum:
            if current and current.get("nome"):
                out.append(current)
            rest = line[mnum.end():].strip()
            mdate = _CAD_DATE_RE.search(rest)
            data_nasc = None
            if mdate:
                data_nasc = _cad_parse_date(mdate.group(1))
                rest = (rest[:mdate.start()] + rest[mdate.end():]).strip()
            current = {
                "numero": int(mnum.group(1)),
                "nome": rest,
                "filiacao": "",
                "data_nascimento": data_nasc,
            }
            continue
        if current is not None:
            mdate = _CAD_DATE_RE.search(line)
            if mdate and not current.get("data_nascimento"):
                current["data_nascimento"] = _cad_parse_date(mdate.group(1))
                line = (line[:mdate.start()] + line[mdate.end():]).strip()
                if not line:
                    continue
            if current.get("filiacao"):
                current["filiacao"] += " " + line
            else:
                current["filiacao"] = line
    if current and current.get("nome"):
        out.append(current)
    return out


def _cad_extract_pdf_rows(raw_bytes, defaults):
    """Parse the official Caderno Eleitoral 2026 PDF.

    Strategy: use the visible horizontal rules in the table to find the
    *vertical band* of each record, then crop each of the 5 column areas
    and extract their text independently. This avoids issues with
    pdfplumber's text reading order (which on this PDF returns text
    column-by-column instead of row-by-row).

    Per record:
        Nº | NOME | FILIAÇÃO (line 1=pai, line 2=mae) | DATA NASC. | DESCARGA
    """
    import pdfplumber

    rows = []
    page_meta = {k: v for k, v in (defaults or {}).items() if v}

    with pdfplumber.open(_cad_io.BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            for field, regex in _CAD_HEADER_RES.items():
                if not page_meta.get(field):
                    m = regex.search(page_text)
                    if m:
                        page_meta[field] = m.group(1).strip()

            try:
                words = page.extract_words(
                    keep_blank_chars=False,
                    use_text_flow=False,
                    extra_attrs=["x0", "x1", "top", "bottom"],
                ) or []
            except Exception:
                words = []
            if not words:
                continue

            col_x = _cad_find_columns(words)
            if not col_x:
                for r in _cad_extract_pdf_text_rows(page_text):
                    rows.append(_cad_row_with_meta(r, page_meta))
                continue

            # ---- Detect row boundaries from horizontal rules ----
            try:
                h_lines = [ln for ln in (page.horizontal_edges or [])
                           if ln.get("top") is not None]
            except Exception:
                h_lines = []
            # Fall back to lines attribute when edges is empty.
            if not h_lines:
                try:
                    h_lines = [ln for ln in (page.lines or [])
                               if abs((ln.get("y1") or 0) - (ln.get("y0") or 0)) < 0.5]
                except Exception:
                    h_lines = []

            row_ys = sorted({round(ln["top"], 1) for ln in h_lines
                             if ln["top"] > col_x["header_bottom"] + 1})

            page_rows = []
            if len(row_ys) >= 2:
                # Build row bands from consecutive horizontal lines.
                bands = []
                for i in range(len(row_ys) - 1):
                    top = row_ys[i]
                    bottom = row_ys[i + 1]
                    if bottom - top > 8:  # ignore tiny gaps
                        bands.append((top, bottom))

                for top, bottom in bands:
                    band_words = [w for w in words
                                  if w["top"] >= top - 1 and w["bottom"] <= bottom + 1]
                    if not band_words:
                        continue
                    cells = _cad_assign_columns(
                        sorted(band_words, key=lambda w: w["x0"]), col_x
                    )
                    # Filter out the header band (which has the column titles).
                    upper_join = " ".join(cells.values()).upper()
                    if "FILIAÇÃO" in upper_join or "FILIACAO" in upper_join:
                        continue

                    num_cell = (cells.get("numero") or "").strip()
                    mnum = _CAD_NUMBER_RE.match(num_cell.replace("\n", " "))
                    if not mnum and not (cells.get("nome") or "").strip():
                        continue

                    # Build pai/mae from the FILIAÇÃO column words by y-order.
                    fil_words = [w for w in band_words
                                 if col_x["filiacao"][0] <= w["x0"] < col_x["filiacao"][1]]
                    fil_words.sort(key=lambda w: (round(w["top"], 1), w["x0"]))
                    fil_lines_words = []
                    cur_top = None
                    cur_line = []
                    for w in fil_words:
                        if cur_top is None or abs(w["top"] - cur_top) > 4.0:
                            if cur_line:
                                fil_lines_words.append(cur_line)
                            cur_line = [w["text"]]
                            cur_top = w["top"]
                        else:
                            cur_line.append(w["text"])
                    if cur_line:
                        fil_lines_words.append(cur_line)
                    fil_lines = [" ".join(parts).strip() for parts in fil_lines_words if parts]
                    fil_lines = [ln for ln in fil_lines if ln]

                    # The mother's name often wraps to a 3rd/4th line — group
                    # consecutive lines into pai (first 1-2 lines) vs mae (rest).
                    nome_pai = ""
                    nome_mae = ""
                    if len(fil_lines) == 1:
                        # Some records show only the mother (e.g. row 5).
                        # Heuristic: if there's only one line, treat as mother.
                        nome_mae = fil_lines[0]
                    elif len(fil_lines) >= 2:
                        # Pai is line 1 (+ maybe continuation if no MARIA/ANA/etc.
                        # detected). Simplest: split by half — first half = pai.
                        # Best heuristic: line 1 is pai (with optional continuation
                        # if it looks like the same name continues), and the rest
                        # is mãe. Father names rarely span 2 lines unless very
                        # long; we keep it simple — first line = pai, rest = mãe.
                        nome_pai = fil_lines[0]
                        nome_mae = " ".join(fil_lines[1:])

                    descarga_text = (cells.get("descarga") or "").strip()
                    record = {
                        "numero": int(mnum.group(1)) if mnum else None,
                        "nome": (cells.get("nome") or "").strip(),
                        "filiacao": " ".join(fil_lines),
                        "nome_pai": nome_pai,
                        "nome_mae": nome_mae,
                        "data_nascimento": _cad_parse_date(
                            (cells.get("data_nascimento") or "").strip().replace("\n", " ")
                        ),
                        "descarga": bool(
                            descarga_text and descarga_text not in ("_", "-", "—", "_______")
                        ),
                    }
                    if record["nome"] or record["numero"]:
                        page_rows.append(_cad_row_with_meta(record, page_meta))

            if page_rows:
                rows.extend(page_rows)
            else:
                # Fallback: legacy text-line parser.
                for r in _cad_extract_pdf_text_rows(page_text):
                    rows.append(_cad_row_with_meta(r, page_meta))

    return rows


def _cad_row_with_meta(r, meta):
    return {
        "ilha": meta.get("ilha", ""),
        "cre": meta.get("cre", ""),
        "posto": meta.get("posto", ""),
        "concelho": meta.get("concelho", ""),
        "mesa": meta.get("mesa", ""),
        "numero": r.get("numero"),
        "nome": (r.get("nome") or "").strip(),
        "filiacao": (r.get("filiacao") or "").strip(),
        "nome_pai": (r.get("nome_pai") or "").strip(),
        "nome_mae": (r.get("nome_mae") or "").strip(),
        "data_nascimento": r.get("data_nascimento"),
        "descarga": bool(r.get("descarga", False)),
    }


def _cad_find_columns(words):
    """Find x ranges for each column based on the header row.

    Returns a dict like {"numero":(x0,x1), "nome":(x0,x1), ...,
                         "header_bottom": float}
    or None when header words can't be located.
    """
    # Build a quick index by lowercased text.
    targets = {
        "no":       "numero",  # "Nº" → after stripping non-letters becomes "n"
        "n":        "numero",
        "nome":     "nome",
        "filiacao": "filiacao",
        "filiação": "filiacao",
        "data":     "data_nascimento",  # paired with "nasc."
        "descarga": "descarga",
    }
    found = {}  # field -> word
    for w in words:
        token = (w.get("text") or "").strip().lower().rstrip(".:")
        if token in targets:
            field = targets[token]
            # First occurrence wins (top-most)
            if field not in found:
                found[field] = w

    if "nome" not in found or "filiacao" not in found:
        return None

    # Header words like "FILIAÇÃO" and "DATA NASC." are centered above their
    # column, while the data underneath is left-aligned and starts well to the
    # left of the header word. Using the header word's x0 as the left bound
    # would push the first data words into the previous column. Use the
    # header word *centers* and split columns at the midpoints between
    # consecutive centers so each data word lands in the correct bucket.
    ordered = []
    for field in ("numero", "nome", "filiacao", "data_nascimento", "descarga"):
        if field in found:
            w = found[field]
            center = (w["x0"] + w["x1"]) / 2.0
            ordered.append((field, center))
    if len(ordered) < 3:
        return None
    ordered.sort(key=lambda t: t[1])

    bounds = {}
    for i, (field, _center) in enumerate(ordered):
        if i == 0:
            lo = float("-inf")
        else:
            lo = (ordered[i - 1][1] + ordered[i][1]) / 2.0
        if i + 1 < len(ordered):
            hi = (ordered[i][1] + ordered[i + 1][1]) / 2.0
        else:
            hi = float("inf")
        bounds[field] = (lo, hi)

    # Header bottom = max bottom of header words (so we ignore the header row).
    header_bottom = max(found[f]["bottom"] for f in found)
    bounds["header_bottom"] = header_bottom
    return bounds


def _cad_assign_columns(line_words, col_x):
    """Group words on a single line into column buckets by x0."""
    buckets = {}
    fields = [f for f in ("numero", "nome", "filiacao", "data_nascimento", "descarga") if f in col_x]
    for w in line_words:
        x0 = w["x0"]
        chosen = None
        for field in fields:
            lo, hi = col_x[field]
            if lo <= x0 < hi:
                chosen = field
                break
        if chosen is None:
            continue
        buckets.setdefault(chosen, []).append(w["text"])
    return {k: " ".join(v) for k, v in buckets.items()}



def _cad_row_to_kwargs(row, colmap, defaults):
    kw = dict(defaults)  # ilha/cre/posto/concelho/mesa fallbacks
    for col, target in colmap.items():
        raw = row.get(col)
        if target == "numero":
            v = _cad_parse_int(raw)
            if v is not None:
                kw[target] = v
        elif target == "data_nascimento":
            v = _cad_parse_date(raw)
            if v is not None:
                kw[target] = v
        elif target == "descarga":
            kw[target] = _cad_parse_bool(raw)
        else:
            v = _cad_clean(raw)
            if v:
                kw[target] = v
    return kw


@login_required
def caderno_2026_import_preview(request):
    if request.method != "POST" or "arquivo" not in request.FILES:
        return JsonResponse({"message": "Selecione um ficheiro para pré-visualizar"}, status=400)

    upload = request.FILES["arquivo"]
    defaults = {
        "ilha":     (request.POST.get("ilha") or "").strip(),
        "cre":      (request.POST.get("cre") or "").strip(),
        "posto":    (request.POST.get("posto") or "").strip(),
        "concelho": (request.POST.get("concelho") or "").strip(),
        "mesa":     (request.POST.get("mesa") or "").strip(),
    }
    defaults = {k: v for k, v in defaults.items() if v}

    rows, total_rows, err = _cad_collect_rows(upload, defaults)
    if err:
        return JsonResponse({"message": err}, status=400)

    valid = sum(1 for r in rows if r.get("nome"))
    skipped = total_rows - valid
    preview = []
    for r in rows[:10]:
        preview.append({
            "numero": r.get("numero"),
            "nome": r.get("nome", ""),
            "filiacao": r.get("filiacao", ""),
            "nome_pai": r.get("nome_pai", ""),
            "nome_mae": r.get("nome_mae", ""),
            "data_nascimento": r["data_nascimento"].isoformat() if r.get("data_nascimento") else "",
            "descarga": r.get("descarga", False),
            "ilha": r.get("ilha", ""),
            "cre": r.get("cre", ""),
            "posto": r.get("posto", ""),
            "concelho": r.get("concelho", ""),
            "mesa": r.get("mesa", ""),
        })

    return JsonResponse({
        "filename": upload.name,
        "total_rows": total_rows,
        "valid": valid,
        "skipped": skipped,
        "preview": preview,
    })


@login_required
def caderno_2026_import(request):
    if request.method != "POST" or "arquivo" not in request.FILES:
        messages.error(request, "Selecione um ficheiro para carregar")
        return redirect("eleitores.index")

    upload = request.FILES["arquivo"]
    defaults = {
        "ilha":     (request.POST.get("ilha") or "").strip(),
        "cre":      (request.POST.get("cre") or "").strip(),
        "posto":    (request.POST.get("posto") or "").strip(),
        "concelho": (request.POST.get("concelho") or "").strip(),
        "mesa":     (request.POST.get("mesa") or "").strip(),
    }
    defaults = {k: v for k, v in defaults.items() if v}
    update_existing = (request.POST.get("update_existing") or "").lower() in ("1", "true", "on", "yes")

    rows, total_rows, err = _cad_collect_rows(upload, defaults)
    if err:
        messages.error(request, err)
        return redirect("eleitores.index")

    job = CadernoEleitoral2026Import.objects.create(
        nome_original=upload.name,
        status=CadernoEleitoral2026Import.STATUS_RUNNING,
        total_linhas=total_rows,
    )

    criadas = 0
    atualizadas = 0
    duplicadas = 0
    erros = 0
    processadas = 0
    objs = []

    # Eleitores mirror counters
    el_criadas = 0
    el_atualizadas = 0
    el_duplicadas = 0
    el_erros = 0
    el_objs = []

    def _eleitores_kwargs(kw):
        """Map a CadernoEleitoral2026 kwargs dict to Eleitores fields."""
        return {
            "nome": kw.get("nome") or None,
            "filiacao": kw.get("filiacao") or None,
            "data_nascimento": kw.get("data_nascimento"),
            "concelho": kw.get("concelho") or None,
            "zona": kw.get("posto") or None,
            "nr_mesa": kw.get("mesa") or None,
            "nr_eleitor": kw.get("numero"),
            "descarga": bool(kw.get("descarga")),
        }

    for kw in rows:
        processadas += 1
        try:
            if not kw.get("nome"):
                erros += 1
                continue
            mesa_key = kw.get("mesa") or ""
            numero_key = kw.get("numero")
            existing = None
            if mesa_key and numero_key is not None:
                existing = CadernoEleitoral2026.objects.filter(
                    mesa=mesa_key, numero=numero_key
                ).first()
            if existing:
                if update_existing:
                    for f, v in kw.items():
                        setattr(existing, f, v)
                    existing.ativo = True
                    existing.save()
                    atualizadas += 1
                else:
                    duplicadas += 1
            else:
                objs.append(CadernoEleitoral2026(**kw))
                criadas += 1
                if len(objs) >= 500:
                    CadernoEleitoral2026.objects.bulk_create(objs)
                    objs = []
        except Exception:
            erros += 1
            continue

        # Mirror into legacy Eleitores table
        try:
            el_kw = _eleitores_kwargs(kw)
            el_existing = None
            if el_kw["nr_mesa"] and el_kw["nr_eleitor"] is not None:
                el_existing = Eleitores.objects.filter(
                    nr_mesa=el_kw["nr_mesa"], nr_eleitor=el_kw["nr_eleitor"]
                ).first()
            if el_existing:
                if update_existing:
                    for f, v in el_kw.items():
                        setattr(el_existing, f, v)
                    el_existing.save()
                    el_atualizadas += 1
                else:
                    el_duplicadas += 1
            else:
                el_objs.append(Eleitores(**el_kw))
                el_criadas += 1
                if len(el_objs) >= 500:
                    Eleitores.objects.bulk_create(el_objs)
                    el_objs = []
        except Exception:
            el_erros += 1
            continue

    if objs:
        CadernoEleitoral2026.objects.bulk_create(objs)
    if el_objs:
        Eleitores.objects.bulk_create(el_objs)

    job.processadas = processadas
    job.criadas = criadas
    job.atualizadas = atualizadas
    job.duplicadas = duplicadas
    job.erros = erros
    job.status = CadernoEleitoral2026Import.STATUS_DONE
    job.mensagem = (
        f"Caderno → Criadas: {criadas} · Atualizadas: {atualizadas} · "
        f"Duplicadas: {duplicadas} · Erros: {erros} | "
        f"Eleitores → Criadas: {el_criadas} · Atualizadas: {el_atualizadas} · "
        f"Duplicadas: {el_duplicadas} · Erros: {el_erros}"
    )
    job.save()

    messages.success(
        request,
        f"Caderno 2026 importado. Caderno: criadas {criadas}, atualizadas {atualizadas}, "
        f"duplicadas {duplicadas}, erros {erros}. "
        f"Eleitores: criadas {el_criadas}, atualizadas {el_atualizadas}, "
        f"duplicadas {el_duplicadas}, erros {el_erros} (de {processadas} linhas).",
    )
    return redirect("eleitores.index")


def _cad_collect_rows(upload, defaults):
    """Read upload (CSV/XLS/XLSX/PDF) and return (rows, total_rows, error_msg)."""
    name = (upload.name or "").lower()
    if name.endswith(".pdf"):
        try:
            raw = upload.read()
            upload.seek(0)
            rows = _cad_extract_pdf_rows(raw, defaults)
        except Exception as exc:
            return [], 0, f"Erro ao ler PDF: {exc}"
        return rows, len(rows), None

    df = _cad_load_dataframe(upload)
    if df is None or df.empty:
        return [], 0, "Não foi possível ler o ficheiro. Use CSV, XLS, XLSX ou PDF."
    colmap = _cad_build_colmap(df.columns)
    if "nome" not in colmap.values():
        return [], 0, ("Coluna NOME não encontrada. Cabeçalhos esperados: Nº, NOME, "
                       "FILIAÇÃO, DATA NASC, DESCARGA, ILHA, CRE, POSTO, CONCELHO, MESA")
    rows = []
    for _, row in df.iterrows():
        rows.append(_cad_row_to_kwargs(row, colmap, defaults))
    return rows, int(df.shape[0]), None

